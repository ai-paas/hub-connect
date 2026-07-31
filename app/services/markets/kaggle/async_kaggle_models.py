import asyncio
import fnmatch
import inspect
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional

import markdown2
from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.config import settings
from app.core.logging import logger
from app.services.markets.kaggle.handle import (
    format_dataset_id,
    format_model_id,
    parse_dataset_handle,
    parse_model_handle,
)
from app.services.markets.kaggle.kaggle_client import get_kaggle_client
from app.services.markets.kaggle.internal_client import (
    KAGGLE_TOTAL_CAP,
    fetch_model_downloads,
    fetch_model_totals,
)
from app.services.markets.kaggle.mappers import (
    to_dataset_info_response,
    to_dataset_item,
    to_file_tree_item,
    to_model_detail,
    to_model_item,
)


_MODEL_SORT_MAP = {
    "downloads": "downloadCount",
    "likes": "voteCount",
    "updated": "createTime",
    "trending": "hotness",
    "hotness": "hotness",
    "downloadCount": "downloadCount",
    "voteCount": "voteCount",
    "notebookCount": "notebookCount",
    "createTime": "createTime",
}

_DATASET_SORT_MAP = {
    "likes": "votes",
    "votes": "votes",
    "downloads": "hottest",
    "trending": "hottest",
    "hottest": "hottest",
    "updated": "updated",
    "modified": "updated",
    "created": "active",
    "active": "active",
    "most_rows": "hottest",
    "least_rows": "hottest",
}

_MODEL_FRAMEWORK_TAGS = [
    {"id": "tensorFlow1", "label": "TensorFlow 1"},
    {"id": "tensorFlow2", "label": "TensorFlow 2"},
    {"id": "pyTorch", "label": "PyTorch"},
    {"id": "jax", "label": "JAX"},
    {"id": "keras", "label": "Keras"},
    {"id": "transformers", "label": "Transformers"},
    {"id": "scikitLearn", "label": "scikit-learn"},
]


def _response_files(response: Any) -> List[Any]:
    if hasattr(response, "files"):
        return list(response.files or [])
    if isinstance(response, dict):
        return list(response.get("files") or response.get("datasetFiles") or [])
    if isinstance(response, list):
        return response
    return []


def _response_next_page_token(response: Any) -> Optional[str]:
    if isinstance(response, dict):
        return response.get("nextPageToken") or response.get("next_page_token")
    return getattr(response, "nextPageToken", None) or getattr(
        response,
        "next_page_token",
        None,
    )


class AsyncKaggleService:
    """Kaggle marketplace adapter matching the HuggingFace async service surface."""

    def __init__(self) -> None:
        self._timeout = settings.KAGGLE_TIMEOUT
        self._download_timeout = settings.KAGGLE_DOWNLOAD_TIMEOUT

    async def _call(self, func, /, *args, timeout: Optional[int] = None, **kwargs) -> Any:
        """Run a blocking kaggle call in a worker thread with a timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args, **kwargs),
                timeout=timeout or self._timeout,
            )
        except asyncio.TimeoutError as exc:
            logger.error("Kaggle call %s timed out", getattr(func, "__name__", "?"))
            raise HTTPException(status_code=504, detail="Kaggle request timed out") from exc
        except HTTPException:
            raise
        except Exception as exc:
            status = self._map_kaggle_status(exc)
            logger.error(
                "Kaggle call %s failed (status=%s): %s",
                getattr(func, "__name__", "?"),
                status,
                exc,
            )
            detail = {
                401: "Kaggle authentication failed",
                404: "Kaggle resource not found",
            }.get(status, "Kaggle upstream request failed")
            raise HTTPException(status_code=status, detail=detail) from exc

    @staticmethod
    def _map_kaggle_status(exc: Exception) -> int:
        status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
        try:
            status_int = int(status) if status is not None else None
        except (TypeError, ValueError):
            status_int = None
        if status_int in (401, 403):
            return 401
        if status_int == 404:
            return 404
        return 502

    @staticmethod
    def _sdk_method(api: Any, candidates: List[str]):
        """Return the first callable SDK alias."""
        for name in candidates:
            method = getattr(api, name, None)
            if callable(method):
                return method
        raise AttributeError(
            f"None of {candidates!r} are available on the installed Kaggle SDK"
        )

    @staticmethod
    def _call_sdk(api: Any, candidates: List[str], *args, **kwargs) -> Any:
        """Invoke the first method on `api` whose name appears in `candidates`.

        Kaggle's Python SDK has shifted naming between versions
        (``models_list`` vs ``model_list``, ``dataset_view`` vs ``dataset_get``,
        etc.) so we probe a short list of known aliases rather than hard-coding
        a single name.
        """
        return AsyncKaggleService._sdk_method(api, candidates)(*args, **kwargs)

    @staticmethod
    def _model_instance_get_from_api(api: Any, handle) -> Any:
        """Call the Kaggle 2.x string API with a 1.x positional fallback."""
        method = AsyncKaggleService._sdk_method(
            api,
            ["model_instance_get", "models_instance_get"],
        )
        handle_str = format_model_id(handle)
        try:
            parameters = list(inspect.signature(method).parameters.values())
        except (TypeError, ValueError):
            parameters = []
        positional = [
            parameter
            for parameter in parameters
            if parameter.kind
            in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(
            parameter.kind == parameter.VAR_POSITIONAL for parameter in parameters
        )
        if not has_varargs and len(positional) >= 4:
            return method(
                handle.owner,
                handle.model,
                handle.framework,
                handle.variation,
            )
        if has_varargs:
            try:
                return method(handle_str)
            except TypeError:
                return method(
                    handle.owner,
                    handle.model,
                    handle.framework,
                    handle.variation,
                )
        return method(handle_str)

    @staticmethod
    def _paginated_total(
        page: int,
        page_size: int,
        returned: int,
        exact_total: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return pagination metadata, preferring an upstream exact total.

        ``exact_total`` is the count from Kaggle (internal ``ModelService`` first,
        public ``ModelApiService`` as fallback). Three cases:

        * ``exact_total`` below the cap -> trusted exact count
          (``total_is_exact=True``).
        * ``exact_total`` at/above ``KAGGLE_TOTAL_CAP`` (10000) -> Kaggle caps the
          count there, so it's a lower bound (``total_is_exact=False``,
          ``has_more=True``).
        * ``exact_total`` is ``None`` (datasets, or no count available) -> derive
          a lower bound from the page position
          (``(page-1)*page_size + len(items)``).
        """
        effective_page = max(1, page)
        effective_page_size = max(1, page_size)
        seen_so_far = (effective_page - 1) * effective_page_size + returned

        if exact_total is not None:
            total = int(exact_total)
            if total < seen_so_far:
                # Upstream total trails the items we've already paged through
                # (e.g. an org-filtered count against an all-owners item list);
                # report a lower bound rather than a number smaller than shown.
                return {
                    "total": seen_so_far,
                    "total_is_exact": False,
                    "has_more": returned >= effective_page_size,
                }
            if total >= KAGGLE_TOTAL_CAP:
                # Kaggle ceilings the count at the cap; real total is higher.
                return {"total": total, "total_is_exact": False, "has_more": True}
            return {
                "total": total,
                "total_is_exact": True,
                "has_more": seen_so_far < total,
            }

        has_more = returned >= effective_page_size
        return {
            "total": seen_so_far,
            "total_is_exact": not has_more,
            "has_more": has_more,
        }

    # =============================================================================
    # Models
    # =============================================================================

    def _model_list_sync(self, *, search: str, sort_by: str, page_size: int, page: int, owner: Optional[str] = None) -> Dict[str, Any]:
        """List one page of models as ``{"items": [...], "total": Optional[int]}``.

        ``total`` is Kaggle's authoritative ``total_results`` count when the
        installed SDK exposes the low-level client (so pagination can report an
        exact total). It is ``None`` when only the high-level ``model_list``
        helper is reachable, because that helper discards the upstream count;
        the caller then derives a best-effort lower bound.
        """
        api = get_kaggle_client()

        low_level = self._model_list_lowlevel(
            api,
            search=search,
            sort_by=sort_by,
            page_size=page_size,
            page=page,
            owner=owner,
        )
        if low_level is not None:
            return low_level

        kwargs: Dict[str, Any] = {
            "sort_by": sort_by,
            "page_size": page_size * max(1, page),
            "search": search or "",
        }
        if owner:
            kwargs["owner"] = owner
        items = self._call_sdk(api, ["model_list", "models_list"], **kwargs)
        start = (max(1, page) - 1) * page_size
        all_items = list(items or [])
        page_items = (
            all_items[start:start + page_size]
            if len(all_items) > page_size
            else all_items[:page_size]
        )
        return {"items": page_items, "total": None}

    def _model_list_lowlevel(
        self,
        api: Any,
        *,
        search: str,
        sort_by: str,
        page_size: int,
        page: int,
        owner: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Fetch a models page via the low-level kagglesdk client to read ``total_results``.

        The high-level ``KaggleApi.model_list`` helper returns only the page
        items and throws away the ``total_results`` count that the underlying
        ``ListModels`` RPC returns. We replicate its request setup against the
        low-level client so we can surface that exact total.

        Returns ``{"items": [...], "total": int}`` on success, or ``None`` when
        the installed SDK lacks the low-level surface (the caller then falls
        back to the high-level helper). Genuine upstream errors (auth, network,
        5xx) propagate so the router can map them to the right status code.
        """
        build_client = getattr(api, "build_kaggle_client", None)
        if not callable(build_client):
            return None
        try:
            from kagglesdk.models.types.model_api_service import ApiListModelsRequest
            from kagglesdk.models.types.model_enums import ListModelsOrderBy
        except ImportError:
            return None

        order_by = ListModelsOrderBy.LIST_MODELS_ORDER_BY_HOTNESS
        valid = getattr(api, "valid_model_sort_bys", None)
        if sort_by and (valid is None or sort_by in valid):
            try:
                order_by = api.lookup_enum(ListModelsOrderBy, order_by, sort_by)
            except Exception:  # unknown sort key -> keep the hotness default
                order_by = ListModelsOrderBy.LIST_MODELS_ORDER_BY_HOTNESS

        request = ApiListModelsRequest()
        request.sort_by = order_by
        request.search = search or ""
        request.owner = owner or ""
        request.page_size = page_size

        with build_client() as kaggle:
            client = getattr(getattr(kaggle, "models", None), "model_api_client", None)
            list_models = getattr(client, "list_models", None)
            if not callable(list_models):
                return None
            response = None
            page_token = None
            for current_page in range(1, max(1, page) + 1):
                request.page_token = page_token
                response = list_models(request)
                if current_page == max(1, page):
                    break
                page_token = getattr(response, "next_page_token", None)
                if not page_token:
                    return {
                        "items": [],
                        "total": int(getattr(response, "total_results", 0) or 0),
                    }

        if response is None or not hasattr(response, "total_results"):
            return None
        items = list(getattr(response, "models", None) or [])
        return {"items": items, "total": int(getattr(response, "total_results", 0) or 0)}

    async def _list_models(
        self,
        *,
        query: Optional[str],
        sort: str,
        page: int,
        limit: int,
    ) -> Dict[str, Any]:
        sort_by = _MODEL_SORT_MAP.get(sort, "hotness")
        effective_limit = max(1, min(limit, 100))
        raw = await self._call(
            self._model_list_sync,
            search=query or "",
            sort_by=sort_by,
            page_size=effective_limit,
            page=max(1, page),
        )
        items = list(raw.get("items") or [])
        models = [to_model_item(item) for item in items]

        # Kaggle's public ListModels JSON no longer carries a per-model
        # downloadCount, so mapped ``downloads`` come out 0. Recover the real
        # counts (the ones kaggle.com shows) from the internal ModelService by
        # model id; on any failure the zeros simply remain.
        pending_ids = [
            self._raw_model_id(item)
            for item, model in zip(items, models)
            if not model.get("downloads")
        ]
        pending_ids = [model_id for model_id in pending_ids if model_id is not None]

        # Primary count source: Kaggle's internal ModelService (accurate
        # totalResults + variation count, matching kaggle.com/models). Falls
        # back to the public SDK total_results (capped at 10000) when the
        # internal call fails for any reason.
        internal, downloads = await asyncio.gather(
            self._fetch_internal_total(query or ""),
            self._fetch_internal_downloads(pending_ids),
        )
        if downloads:
            for item, model in zip(items, models):
                model_id = self._raw_model_id(item)
                if not model.get("downloads") and model_id in downloads:
                    model["downloads"] = downloads[model_id]
        if internal is not None:
            exact_total: Optional[int] = internal["total_results"]
            total_instances: Optional[int] = internal["total_model_instances"]
        else:
            exact_total = raw.get("total")
            total_instances = None

        result: Dict[str, Any] = {
            "models": models,
            **self._paginated_total(
                page, effective_limit, len(models), exact_total=exact_total
            ),
        }
        if total_instances is not None:
            result["total_model_instances"] = total_instances
        return result

    async def _fetch_internal_total(self, search: str) -> Optional[Dict[str, int]]:
        """Best-effort fetch of accurate model totals from Kaggle's internal API.

        Returns ``None`` (so the caller falls back to the public total) on any
        failure or timeout; ``fetch_model_totals`` itself never raises.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fetch_model_totals, search),
                timeout=self._timeout,
            )
        except Exception as exc:
            logger.warning("Internal Kaggle total fetch failed: %s", exc)
            return None

    @staticmethod
    def _raw_model_id(item: Any) -> Optional[int]:
        """Numeric Kaggle model id from a raw list/detail payload, else ``None``."""
        raw = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    async def _fetch_internal_downloads(
        self, model_ids: List[int]
    ) -> Optional[Dict[int, int]]:
        """Best-effort per-model download counts from Kaggle's internal API.

        Returns ``None`` (callers keep the mapped zeros) when there is nothing
        to look up or on any failure; ``fetch_model_downloads`` never raises.
        """
        if not model_ids:
            return None
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fetch_model_downloads, model_ids),
                timeout=self._timeout,
            )
        except Exception as exc:
            logger.warning("Internal Kaggle downloads fetch failed: %s", exc)
            return None

    async def get_trending_models(
        self,
        page: int,
        query: Optional[str] = None,
        num_parameters_min: Optional[str] = None,
        num_parameters_max: Optional[str] = None,
        pipeline_tag: Optional[str] = None,
        library: Optional[List[str]] = None,
        language: Optional[List[str]] = None,
        license: Optional[str] = None,
        apps: Optional[List[str]] = None,
        inference_provider: Optional[List[str]] = None,
        other: Optional[List[str]] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        return await self._list_models(
            query=query,
            sort="hotness",
            page=page,
            limit=limit,
        )

    async def search_models(
        self,
        query: str,
        sort: str,
        page: int,
        limit: int,
        num_parameters_min: Optional[str] = None,
        num_parameters_max: Optional[str] = None,
        pipeline_tag: Optional[str] = None,
        library: Optional[List[str]] = None,
        language: Optional[List[str]] = None,
        license: Optional[str] = None,
        apps: Optional[List[str]] = None,
        inference_provider: Optional[List[str]] = None,
        other: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await self._list_models(query=query, sort=sort, page=page, limit=limit)

    def _model_detail_sync(self, handle) -> Dict[str, Any]:
        """Fetch model metadata, preferring variation-specific instance data.

        For a 4-segment handle we call ``model_instance_get`` so the response
        reflects the specific framework+variation the caller asked for.
        Model-level data from ``model_get`` is also fetched and merged for
        description/license fields that only exist at the model level.
        """
        api = get_kaggle_client()
        model_level = self._call_sdk(
            api,
            ["model_get", "models_get"],
            f"{handle.owner}/{handle.model}",
        )

        instance: Any = None
        if handle.framework and handle.variation and handle.variation != "default":
            try:
                instance = self._model_instance_get_from_api(api, handle)
            except Exception as err:  # variation missing -> fall back to model-level
                logger.warning(
                    "model_instance_get failed for %s/%s/%s/%s: %s",
                    handle.owner,
                    handle.model,
                    handle.framework,
                    handle.variation,
                    err,
                )

        return {"model": model_level, "instance": instance}

    def _model_instance_files_sync(self, handle) -> List[Any]:
        api = get_kaggle_client()
        handle_str = format_model_id(handle)
        try:
            method = self._sdk_method(
                api,
                ["model_instance_files", "models_instance_files"],
            )
        except AttributeError:
            method = None
        if method is not None:
            files: List[Any] = []
            page_token = None
            seen_tokens = set()
            while True:
                result = (
                    method(handle_str)
                    if page_token is None
                    else method(
                        handle_str,
                        page_token=page_token,
                        page_size=100,
                    )
                )
                files.extend(_response_files(result))
                next_page_token = _response_next_page_token(result)
                if not next_page_token or next_page_token in seen_tokens:
                    return files
                seen_tokens.add(next_page_token)
                page_token = next_page_token

        candidates = [
            (
                ["model_instance_version_list_files", "models_instance_version_list_files"],
                (handle.owner, handle.model, handle.framework, handle.variation),
            ),
            (
                ["model_list_files", "models_list_files"],
                (f"{handle.owner}/{handle.model}/{handle.framework}/{handle.variation}",),
            ),
        ]
        last_err: Optional[Exception] = None
        for names, args in candidates:
            try:
                result = self._call_sdk(api, names, *args)
            except AttributeError:
                continue
            except Exception as err:
                last_err = err
                continue
            if hasattr(result, "files") or isinstance(result, (dict, list)):
                return _response_files(result)
        if last_err is not None:
            raise last_err
        raise RuntimeError("No compatible Kaggle model files API found")

    async def get_model_files(self, model_id: str) -> Dict[str, Any]:
        handle = parse_model_handle(model_id)
        raw_files = await self._call(self._model_instance_files_sync, handle)
        files = [
            {
                "name": item.get("name") if isinstance(item, dict) else getattr(item, "name", ""),
                "size": _size_to_human(item),
                "blob_id": None,
            }
            for item in (raw_files or [])
        ]
        return {"files": files}

    def _download_model_files_sync(self, handle, target_dir: str) -> None:
        api = get_kaggle_client()
        handle_str = format_model_id(handle)
        if hasattr(api, "model_instance_version_download"):
            method = api.model_instance_version_download
            try:
                parameter_names = set(inspect.signature(method).parameters)
            except (TypeError, ValueError):
                parameter_names = set()
            if "owner_slug" in parameter_names:
                method(
                    owner_slug=handle.owner,
                    model_slug=handle.model,
                    framework=handle.framework,
                    instance_slug=handle.variation,
                    version_number=None,
                    path=target_dir,
                    force=False,
                    quiet=True,
                    untar=False,
                )
                return

            instance = self._model_instance_get_from_api(api, handle)
            version_number = (
                instance.get("versionNumber") or instance.get("version_number")
                if isinstance(instance, dict)
                else getattr(instance, "version_number", None)
                or getattr(instance, "versionNumber", None)
            )
            if not version_number:
                raise RuntimeError("Kaggle model instance version is unavailable")
            method(
                f"{handle_str}/{version_number}",
                path=target_dir,
                force=False,
                quiet=True,
                untar=False,
            )
        else:
            self._call_sdk(
                api,
                ["model_download_files", "models_download_files"],
                handle_str,
                path=target_dir,
                force=False,
                quiet=True,
                untar=False,
            )

    async def download_model_file(
        self,
        model_id: str,
        filename: str,
        download_dir: Optional[str] = None,
    ):
        handle = parse_model_handle(model_id)
        tmp_dir = tempfile.mkdtemp(prefix="kaggle_model_")
        cleanup_in_finally = True
        try:
            await self._call(
                self._download_model_files_sync,
                handle,
                tmp_dir,
                timeout=self._download_timeout,
            )
            source_path = _resolve_downloaded_file(tmp_dir, filename)
            if source_path is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"File not found in Kaggle model: {filename}",
                )

            if download_dir:
                target_dir = os.path.expanduser(download_dir)
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, os.path.basename(source_path))
                await asyncio.to_thread(shutil.copy2, source_path, target_path)
                return {
                    "download_type": "custom_path",
                    "file_path": target_path,
                    "file_size": os.path.getsize(target_path),
                    "filename": os.path.basename(target_path),
                    "model_id": format_model_id(handle),
                }

            response = FileResponse(
                source_path,
                media_type="application/octet-stream",
                filename=os.path.basename(source_path),
                background=BackgroundTask(
                    shutil.rmtree,
                    tmp_dir,
                    ignore_errors=True,
                ),
            )
            cleanup_in_finally = False
            return response
        finally:
            if cleanup_in_finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    async def get_model_detail(self, model_id: str) -> Dict[str, Any]:
        handle = parse_model_handle(model_id)
        raw = await self._call(self._model_detail_sync, handle)

        model_level = raw.get("model") if isinstance(raw, dict) else None
        instance = raw.get("instance") if isinstance(raw, dict) else None
        # Instance (variation) data, when available, wins for per-variation
        # metadata; otherwise fall back to model-level data.
        primary = instance or model_level

        def _field(key: str, default: Any = None) -> Any:
            for source in (instance, model_level):
                if source is None:
                    continue
                value = (
                    source.get(key)
                    if isinstance(source, dict)
                    else getattr(source, key, None)
                )
                if value:
                    return value
            return default

        description = _field("description") or ""
        card_html = markdown2.markdown(
            description, extras=["fenced-code-blocks", "tables"]
        ) if description else ""
        detail = to_model_detail(primary, card_html=card_html)
        detail["id"] = format_model_id(handle)
        detail["modelId"] = detail["id"]
        # Expose whether we resolved a variation-specific payload so clients can
        # tell apart partial (model-level only) responses from exact matches.
        detail["variation_resolved"] = instance is not None
        if not detail.get("downloads"):
            model_id = self._raw_model_id(model_level)
            downloads = await self._fetch_internal_downloads(
                [model_id] if model_id is not None else []
            )
            if downloads and model_id in downloads:
                detail["downloads"] = downloads[model_id]
        return detail

    # =============================================================================
    # Tags
    # =============================================================================

    def _datasets_list_tags_sync(self) -> List[Any]:
        api = get_kaggle_client()
        try:
            return list(
                self._call_sdk(api, ["datasets_list_tags", "dataset_list_tags"]) or []
            )
        except AttributeError as err:
            logger.warning("Kaggle dataset list tags method not available: %s", err)
            return []

    async def get_tags(self) -> Dict[str, Any]:
        raw_tags = await self._call(self._datasets_list_tags_sync)
        dataset_tags: List[Dict[str, str]] = []
        for tag in raw_tags or []:
            tag_id = getattr(tag, "ref", None) or (tag.get("ref") if isinstance(tag, dict) else None)
            label = getattr(tag, "name", None) or (tag.get("name") if isinstance(tag, dict) else None) or tag_id
            if tag_id:
                dataset_tags.append({"id": str(tag_id), "label": str(label or tag_id)})
        return {
            "region": [],
            "other": [],
            "library": list(_MODEL_FRAMEWORK_TAGS),
            "license": [],
            "language": [],
            "dataset": dataset_tags,
            "pipeline_tag": [],
            "deploy": [],
        }

    # =============================================================================
    # Datasets
    # =============================================================================

    def _datasets_list_sync(
        self,
        *,
        search: str,
        sort_by: str,
        page: int,
        page_size: int,
    ) -> List[Any]:
        api = get_kaggle_client()
        upstream_page_size = 20
        effective_page = max(1, page)
        effective_page_size = max(1, page_size)
        start = (effective_page - 1) * effective_page_size
        end = start + effective_page_size
        first_upstream_page = start // upstream_page_size + 1
        last_upstream_page = (end - 1) // upstream_page_size + 1
        items: List[Any] = []
        for upstream_page in range(first_upstream_page, last_upstream_page + 1):
            page_items = self._call_sdk(
                api,
                ["dataset_list", "datasets_list"],
                search=search or "",
                sort_by=sort_by,
                page=upstream_page,
            )
            items.extend(page_items or [])
        offset = start - (first_upstream_page - 1) * upstream_page_size
        return items[offset:offset + effective_page_size]

    async def search_datasets(
        self,
        query: str = "",
        sort: str = "likes",
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        sort_by = _DATASET_SORT_MAP.get(sort, "hottest")
        raw_items = await self._call(
            self._datasets_list_sync,
            search=query,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )
        items = list(raw_items or [])
        effective_page_size = page_size if page_size and page_size > 0 else len(items)
        trimmed = items[:effective_page_size]
        datasets = [to_dataset_item(item) for item in trimmed]
        pagination = self._paginated_total(page, effective_page_size, len(trimmed))
        return {
            "datasets": datasets,
            "page": page,
            "page_size": page_size,
            **pagination,
        }

    def _dataset_view_sync(self, handle) -> Any:
        api = get_kaggle_client()
        try:
            return self._call_sdk(
                api,
                ["dataset_view", "datasets_view", "dataset_get", "datasets_get"],
                format_dataset_id(handle),
            )
        except AttributeError:
            build_client = getattr(api, "build_kaggle_client", None)
            if not callable(build_client):
                raise
            from kagglesdk.datasets.types.dataset_api_service import ApiGetDatasetRequest

            request = ApiGetDatasetRequest()
            request.owner_slug = handle.owner
            request.dataset_slug = handle.slug
            with build_client() as kaggle:
                return kaggle.datasets.dataset_api_client.get_dataset(request)

    def _dataset_list_files_sync(self, handle) -> Any:
        """Look up a dataset's files, returning ``None`` ONLY when no SDK alias exists.

        Real upstream errors (401/403/404/5xx) propagate through ``_call`` so
        the router can surface the correct status code. Only a missing SDK
        method (AttributeError from our alias probe) degrades to ``None``,
        which callers treat as "file listing unavailable" rather than "empty
        dataset".
        """
        api = get_kaggle_client()
        try:
            method = self._sdk_method(
                api,
                ["dataset_list_files", "datasets_list_files"],
            )
        except AttributeError as err:
            logger.warning("Kaggle dataset_list_files not available: %s", err)
            return None
        files: List[Any] = []
        page_token = None
        seen_tokens = set()
        while True:
            response = (
                method(format_dataset_id(handle))
                if page_token is None
                else method(
                    format_dataset_id(handle),
                    page_token=page_token,
                    page_size=100,
                )
            )
            files.extend(_response_files(response))
            next_page_token = _response_next_page_token(response)
            if not next_page_token or next_page_token in seen_tokens:
                return files
            seen_tokens.add(next_page_token)
            page_token = next_page_token

    async def get_dataset_info(self, repo_id: str) -> Dict[str, Any]:
        handle = parse_dataset_handle(repo_id)
        view = await self._call(self._dataset_view_sync, handle)
        tags = getattr(view, "tags", None) or (
            view.get("tags") if isinstance(view, dict) else None
        ) or []
        return to_dataset_info_response(view, tags=list(tags))

    async def get_dataset_files(self, repo_id: str):
        handle = parse_dataset_handle(repo_id)
        raw = await self._call(self._dataset_list_files_sync, handle)
        if raw is None:
            return []
        return [to_file_tree_item(f) for f in _response_files(raw)]

    def _dataset_download_file_sync(self, handle, filename: str, target_dir: str) -> None:
        api = get_kaggle_client()
        self._call_sdk(
            api,
            ["dataset_download_file", "datasets_download_file"],
            format_dataset_id(handle),
            file_name=filename,
            path=target_dir,
            force=False,
            quiet=True,
        )

    def _dataset_download_files_sync(self, handle, target_dir: str) -> None:
        api = get_kaggle_client()
        self._call_sdk(
            api,
            ["dataset_download_files", "datasets_download_files"],
            format_dataset_id(handle),
            path=target_dir,
            force=False,
            quiet=True,
            unzip=True,
        )

    async def download_file(
        self,
        repo_id: str,
        filename: str,
        revision: Optional[str] = None,
        download_dir: Optional[str] = None,
    ):
        handle = parse_dataset_handle(repo_id)
        tmp_dir = tempfile.mkdtemp(prefix="kaggle_dataset_")
        cleanup_in_finally = True
        try:
            await self._call(
                self._dataset_download_file_sync,
                handle,
                filename,
                tmp_dir,
                timeout=self._download_timeout,
            )
            source_path = _resolve_downloaded_file(tmp_dir, filename)
            if source_path is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"File not found in Kaggle dataset: {filename}",
                )

            if download_dir:
                target_dir = os.path.expanduser(download_dir)
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, os.path.basename(source_path))
                await asyncio.to_thread(shutil.copy2, source_path, target_path)
                return {
                    "download_type": "custom_path",
                    "file_path": target_path,
                    "file_size": os.path.getsize(target_path),
                    "filename": os.path.basename(target_path),
                    "repo_id": format_dataset_id(handle),
                }

            response = FileResponse(
                source_path,
                media_type="application/octet-stream",
                filename=os.path.basename(source_path),
                background=BackgroundTask(
                    shutil.rmtree,
                    tmp_dir,
                    ignore_errors=True,
                ),
            )
            cleanup_in_finally = False
            return response
        finally:
            if cleanup_in_finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    async def download_snapshot(
        self,
        repo_id: str,
        revision: Optional[str] = None,
        allow_patterns: Optional[List[str]] = None,
        ignore_patterns: Optional[List[str]] = None,
        download_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        handle = parse_dataset_handle(repo_id)
        target_dir = (
            os.path.expanduser(download_dir)
            if download_dir
            else tempfile.mkdtemp(prefix="kaggle_snapshot_")
        )
        os.makedirs(target_dir, exist_ok=True)

        if allow_patterns or ignore_patterns:
            # Pattern filtering isn't supported by Kaggle's bulk download, so
            # we list files first and pull each matching one individually.
            selected_files = await self._select_dataset_files(
                handle, allow_patterns, ignore_patterns
            )
            if selected_files is None:
                # The installed Kaggle SDK doesn't expose a file-listing
                # method, so we can't honor allow/ignore patterns at all.
                # Surface that as 501 rather than a misleading 404.
                raise HTTPException(
                    status_code=501,
                    detail=(
                        "Filtered snapshot download is not supported: the "
                        "installed Kaggle SDK does not expose a file-listing "
                        "method. Upgrade the kaggle package or omit "
                        "allow_patterns/ignore_patterns."
                    ),
                )
            if not selected_files:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "No files match the requested allow/ignore patterns "
                        "for this Kaggle dataset"
                    ),
                )
            for name in selected_files:
                await self._call(
                    self._dataset_download_file_sync,
                    handle,
                    name,
                    target_dir,
                    timeout=self._download_timeout,
                )
        else:
            await self._call(
                self._dataset_download_files_sync,
                handle,
                target_dir,
                timeout=self._download_timeout,
            )

        total = 0
        for _root, _dirs, files in os.walk(target_dir):
            total += len(files)
        return {
            "download_type": "custom_snapshot" if download_dir else "cached_snapshot",
            "snapshot_path": target_dir,
            "repo_id": format_dataset_id(handle),
            "total_files": total,
            "filters_applied": bool(allow_patterns or ignore_patterns),
        }

    async def _select_dataset_files(
        self,
        handle,
        allow_patterns: Optional[List[str]],
        ignore_patterns: Optional[List[str]],
    ) -> Optional[List[str]]:
        """Filter the dataset's file list by the given patterns.

        Returns:
            ``None`` if file listing is unavailable on this SDK (the only
            cause: no ``*_list_files`` alias exists). Callers should treat
            this as a capability gap (501 Not Implemented), not as "no
            matches".
            ``[]`` if listing works but zero files match the filters.
            Otherwise, the list of matching filenames.
        """
        raw = await self._call(self._dataset_list_files_sync, handle)
        if raw is None:
            return None
        if hasattr(raw, "files"):
            entries = list(raw.files or [])
        elif isinstance(raw, dict) and "datasetFiles" in raw:
            entries = list(raw.get("datasetFiles") or [])
        elif isinstance(raw, dict) and "files" in raw:
            entries = list(raw.get("files") or [])
        elif isinstance(raw, list):
            entries = raw
        else:
            entries = []

        names: List[str] = []
        for entry in entries:
            name = (
                entry.get("name") if isinstance(entry, dict)
                else getattr(entry, "name", None)
            )
            if name:
                names.append(str(name))

        def _matches_any(name: str, patterns: List[str]) -> bool:
            return any(fnmatch.fnmatch(name, p) for p in patterns)

        result: List[str] = []
        for name in names:
            if allow_patterns and not _matches_any(name, allow_patterns):
                continue
            if ignore_patterns and _matches_any(name, ignore_patterns):
                continue
            result.append(name)
        return result


def _size_to_human(item: Any) -> str:
    raw = None
    if isinstance(item, dict):
        raw = item.get("totalBytes") or item.get("total_bytes") or item.get("size")
    else:
        raw = (
            getattr(item, "totalBytes", None)
            or getattr(item, "total_bytes", None)
            or getattr(item, "size", None)
        )
    if raw is None:
        return "Unknown"
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    from app.utils.helpers import format_size
    return format_size(size)


def _resolve_downloaded_file(tmp_dir: str, filename: str) -> Optional[str]:
    """Pick the downloaded file matching filename, or the sole file if unambiguous."""
    if not os.path.isdir(tmp_dir):
        return None
    target_basename = os.path.basename(filename)
    exact = os.path.join(tmp_dir, target_basename)
    if os.path.isfile(exact):
        return exact
    zipped = exact + ".zip"
    if os.path.isfile(zipped):
        return zipped
    candidates: List[str] = []
    for root, _dirs, files in os.walk(tmp_dir):
        for name in files:
            if name == target_basename or name == target_basename + ".zip":
                return os.path.join(root, name)
            candidates.append(os.path.join(root, name))
    if len(candidates) == 1:
        return candidates[0]
    return None
