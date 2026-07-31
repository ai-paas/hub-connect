import re
from typing import Any, Dict, List

from app.services.markets.kaggle.handle import (
    KaggleDatasetHandle,
    KaggleModelHandle,
    format_dataset_id,
    format_model_id,
)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Fetch an attribute or dict key in a shape-agnostic way.

    The kaggle package returns rich model objects for some calls and plain
    dicts for others. This helper lets mappers stay consistent across both.
    """
    if obj is None:
        return default
    snake_key = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
    if isinstance(obj, dict):
        return obj.get(key, obj.get(snake_key, default))
    return getattr(obj, key, getattr(obj, snake_key, default))


def _framework_slug(value: Any) -> str:
    """Convert Kaggle SDK framework enums to public handle segments."""
    if value is None:
        return "default"
    name = getattr(value, "name", None) or str(value)
    name = name.rsplit(".", 1)[-1]
    prefix = "MODEL_FRAMEWORK_"
    if not name.startswith(prefix):
        return str(value)
    parts = name[len(prefix):].lower().split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def _tag_label(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    label = _get(value, "ref") or _get(value, "name") or _get(value, "label")
    return str(label) if label else None


def _iso(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def _segments_from_ref(ref: Any) -> List[str]:
    if not ref:
        return []
    return [s for s in str(ref).strip("/").split("/") if s]


def to_model_item(raw: Any) -> Dict[str, Any]:
    owner = _get(raw, "ownerSlug") or _get(raw, "owner") or _get(raw, "author") or ""
    model = _get(raw, "modelSlug") or _get(raw, "slug") or _get(raw, "name") or ""
    instances = list(_get(raw, "instances") or [])
    instance = instances[0] if instances else None
    framework = _framework_slug(_get(raw, "framework") or _get(instance, "framework"))
    variation = (
        _get(raw, "variationSlug")
        or _get(raw, "variation")
        or _get(instance, "slug")
        or "default"
    )

    ref = _get(raw, "ref")
    if ref:
        segs = _segments_from_ref(ref)
        if len(segs) >= 2:
            owner = segs[0]
            model = segs[1]
        if len(segs) >= 3:
            framework = segs[2]
        if len(segs) >= 4:
            variation = segs[3]

    handle = KaggleModelHandle(owner=owner, model=model, framework=framework, variation=variation)

    keywords = _get(raw, "keywords") or _get(raw, "tags") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    task = _get(raw, "task")
    tags: List[str] = []
    for tag in [*keywords, framework, task]:
        label = _tag_label(tag)
        if label and label not in tags:
            tags.append(label)

    return {
        "id": format_model_id(handle),
        "modelId": format_model_id(handle),
        "author": owner,
        "downloads": _get(raw, "downloadCount", 0) or 0,
        "likes": _get(raw, "voteCount", 0) or 0,
        "lastModified": _iso(
            _get(raw, "lastUpdateTime")
            or _get(raw, "updateTime")
            or _get(raw, "lastVersionPublishTime")
            or _get(raw, "publishTime")
        ),
        "pipeline_tag": task,
        "tags": tags,
        "gated": False,
        "private": bool(_get(raw, "isPrivate", False)),
        "isLikedByUser": False,
        "parameterDisplay": None,
        "parameterRange": None,
        "repoType": "model",
    }


def to_model_detail(raw: Any, card_html: str = "") -> Dict[str, Any]:
    item = to_model_item(raw)
    item["description"] = _get(raw, "description") or ""
    item["subtitle"] = _get(raw, "subtitle") or ""
    item["license"] = _get(raw, "licenseName") or _get(raw, "license")
    item["card_html"] = card_html
    return item


def to_dataset_item(raw: Any) -> Dict[str, Any]:
    ref = _get(raw, "ref")
    segs = _segments_from_ref(ref)
    owner = (
        segs[0]
        if segs
        else _get(raw, "ownerSlug")
        or _get(raw, "ownerName")
        or _get(raw, "creatorName")
        or ""
    )
    slug = segs[1] if len(segs) >= 2 else _get(raw, "urlSlug") or ""
    handle = KaggleDatasetHandle(owner=owner or "", slug=slug or "")

    return {
        "id": format_dataset_id(handle) if owner and slug else (ref or ""),
        "author": owner or "",
        "downloads": _get(raw, "downloadCount", 0) or 0,
        "gated": False,
        "isBenchmark": False,
        "isLikedByUser": False,
        "isTraces": False,
        "lastModified": _iso(_get(raw, "lastUpdated")) or "",
        "likes": _get(raw, "voteCount", 0) or 0,
        "private": bool(_get(raw, "isPrivate", False)),
        "repoType": "dataset",
        "datasetsServerInfo": None,
    }


def to_dataset_info_response(raw: Any, tags: List[Any] | None = None) -> Dict[str, Any]:
    tag_refs: List[str] = []
    for tag in tags or []:
        ref = _get(tag, "ref") or _get(tag, "name")
        if ref:
            tag_refs.append(str(ref))

    card_data = {
        "description": (_get(raw, "subtitle") or "") + (
            "\n\n" + _get(raw, "description") if _get(raw, "description") else ""
        ),
        "license": _get(raw, "licenseName") or _get(raw, "license"),
        "tags": tag_refs,
        "size_bytes": _get(raw, "totalBytes"),
        "usability_rating": _get(raw, "usabilityRating"),
        "last_updated": _iso(_get(raw, "lastUpdated")),
    }

    return {
        "dataset_info": {},
        "pending": [],
        "failed": [],
        "partial": True,
        "cardData": card_data,
    }


def to_file_tree_item(raw: Any) -> Dict[str, Any]:
    name = _get(raw, "name") or _get(raw, "ref") or ""
    total_bytes = _get(raw, "totalBytes") or _get(raw, "size") or 0
    try:
        size_int = int(total_bytes)
    except (TypeError, ValueError):
        size_int = 0
    return {
        "path": name,
        "type": "file",
        "size": size_int,
        "blob_id": None,
        "lfs": None,
    }
