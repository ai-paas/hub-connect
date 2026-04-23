import asyncio
import fnmatch
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional

import markdown2
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging import logger
from app.services.markets.kaggle.handle import (
    format_dataset_id,
    format_model_id,
    parse_dataset_handle,
    parse_model_handle,
)
from app.services.markets.kaggle.kaggle_client import get_kaggle_client
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
            raise HTTPException(status_code=status, detail=str(exc)) from exc

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
    def _call_sdk(api: Any, candidates: List[str], *args, **kwargs) -> Any:
        """Invoke the first method on `api` whose name appears in `candidates`.

        Kaggle's Python SDK has shifted naming between versions
        (``models_list`` vs ``model_list``, ``dataset_view`` vs ``dataset_get``,
        etc.) so we probe a short list of known aliases rather than hard-coding
        a single name.
        """
        for name in candidates:
            method = getattr(api, name, None)
            if callable(method):
                return method(*args, **kwargs)
        raise AttributeError(
            f"None of {candidates!r} are available on the installed Kaggle SDK"
        )

    @staticmethod
    def _paginated_total(page: int, page_size: int, returned: int) -> Dict[str, Any]:
        """Return best-effort pagination metadata.

        Kaggle's list endpoints do not surface an upstream total, so we report a
        lower bound (``(page-1)*page_size + len(items)``) and a ``has_more``
        hint that's ``True`` whenever we got a full page back. Clients should
        treat ``total`` as "at least this many" rather than an authoritative
        count.
        """
        effective_page = max(1, page)
        effective_page_size = max(1, page_size)
        seen_so_far = (effective_page - 1) * effective_page_size + returned
        has_more = returned >= effective_page_size
        return {
            "total": seen_so_far,
            "total_is_exact": not has_more,
            "has_more": has_more,
        }

    # =============================================================================
    # Models
    # =============================================================================

    def _model_list_sync(self, *, search: str, sort_by: str, page_size: int, page: int, owner: Optional[str] = None) -> List[Any]:
        api = get_kaggle_client()
        kwargs: Dict[str, Any] = {
            "sort_by": sort_by,
            "page_size": page_size,
            "search": search or "",
        }
        if owner:
            kwargs["owner"] = owner
        try:
            return self._call_sdk(
                api,
                ["model_list", "models_list"],
                **kwargs,
                page_token=str(page) if page > 1 else None,
            )
        except TypeError:
            # Older SDKs don't accept page_token; fall back without it.
            return self._call_sdk(api, ["model_list", "models_list"], **kwargs)

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
        raw_items = await self._call(
            self._model_list_sync,
            search=query or "",
            sort_by=sort_by,
            page_size=effective_limit,
            page=max(1, page),
        )
        items = list(raw_items or [])
        models = [to_model_item(item) for item in items]
        return {
            "models": models,
            **self._paginated_total(page, effective_limit, len(models)),
        }

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
    ) -> Dict[str, Any]:
        return await self._list_models(query=query, sort="hotness", page=page, limit=30)

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
                instance = self._call_sdk(
                    api,
                    ["model_instance_get", "models_instance_get"],
                    handle.owner,
                    handle.model,
                    handle.framework,
                    handle.variation,
                )
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
            if hasattr(result, "files"):
                return list(result.files or [])
            if isinstance(result, dict) and "files" in result:
                return list(result["files"] or [])
            if isinstance(result, list):
                return result
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
        handle_str = f"{handle.owner}/{handle.model}/{handle.framework}/{handle.variation}"
        if hasattr(api, "model_instance_version_download"):
            api.model_instance_version_download(
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

            return FileResponse(
                source_path,
                media_type="application/octet-stream",
                filename=os.path.basename(source_path),
            )
        finally:
            if download_dir:
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
        }

    # =============================================================================
    # Datasets
    # =============================================================================

    def _datasets_list_sync(self, *, search: str, sort_by: str, page: int) -> List[Any]:
        api = get_kaggle_client()
        return self._call_sdk(
            api,
            ["dataset_list", "datasets_list"],
            search=search or "",
            sort_by=sort_by,
            page=max(1, page),
        )

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
        return self._call_sdk(
            api,
            ["dataset_view", "datasets_view", "dataset_get", "datasets_get"],
            format_dataset_id(handle),
        )

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
            return self._call_sdk(
                api,
                ["dataset_list_files", "datasets_list_files"],
                format_dataset_id(handle),
            )
        except AttributeError as err:
            logger.warning("Kaggle dataset_list_files not available: %s", err)
            return None

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
        files = []
        if hasattr(raw, "files"):
            files = list(raw.files or [])
        elif isinstance(raw, dict) and "datasetFiles" in raw:
            files = list(raw.get("datasetFiles") or [])
        elif isinstance(raw, dict) and "files" in raw:
            files = list(raw.get("files") or [])
        elif isinstance(raw, list):
            files = raw
        return [to_file_tree_item(f) for f in files]

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

            return FileResponse(
                source_path,
                media_type="application/octet-stream",
                filename=os.path.basename(source_path),
            )
        finally:
            if download_dir:
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
        raw = item.get("totalBytes") or item.get("size")
    else:
        raw = getattr(item, "totalBytes", None) or getattr(item, "size", None)
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
