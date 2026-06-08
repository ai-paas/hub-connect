"""Best-effort client for Kaggle's internal ``ModelService.ListModels`` endpoint.

The public kaggle SDK (``ModelApiService.ListModels``) caps ``total_results`` at
10000 and exposes no model-instance count. Kaggle's web UI instead calls the
*internal* ``models.ModelService/ListModels`` endpoint (``/api/i/...``), which
returns the accurate ``totalResults`` (e.g. 546 organization models) and
``totalModelInstances`` (e.g. 3499 variations) shown on kaggle.com/models.

This module replicates that call with a self-built, XSRF-warmed ``requests``
session authenticated by the same ``(username, key)`` Basic credentials the SDK
uses. It is intentionally fail-soft: every error path returns ``None`` so the
caller can fall back to the public SDK total. This is an *undocumented* endpoint
and may change without notice; treat it as a best-effort enhancement, not a
contract.
"""
import threading
from typing import Dict, Optional

import requests

from app.core.config import settings
from app.core.logging import logger

_LIST_MODELS_URL = "https://www.kaggle.com/api/i/models.ModelService/ListModels"
_WARM_URL = "https://www.kaggle.com/models"
_XSRF_COOKIE_NAMES = ("XSRF-TOKEN", "CSRF-TOKEN")
_XSRF_HEADER = "X-XSRF-TOKEN"

# Kaggle caps ``totalResults`` at this value on BOTH the public and internal
# endpoints; a value at the cap means "at least this many", not an exact count.
KAGGLE_TOTAL_CAP = 10000

# The web Models page lists organization-owned (published) models by default;
# this filter reproduces the count it shows (e.g. 546 / 3499 variations).
DEFAULT_OWNER_TYPE = "MODEL_OWNER_TYPE_ORGANIZATION"

_session_lock = threading.Lock()
_session: Optional[requests.Session] = None
_xsrf_token: Optional[str] = None


def _build_session():
    """Create an authenticated session and warm up an XSRF token via a GET."""
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": "hub-connect/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    sess.auth = (settings.KAGGLE_USERNAME, settings.KAGGLE_KEY)
    resp = sess.get(_WARM_URL, timeout=settings.KAGGLE_TIMEOUT)
    resp.raise_for_status()
    token = None
    for name in _XSRF_COOKIE_NAMES:
        if name in sess.cookies:
            token = sess.cookies.get(name)
            break
    return sess, token


def _get_session(force: bool = False):
    global _session, _xsrf_token
    with _session_lock:
        if force or _session is None:
            _session, _xsrf_token = _build_session()
        return _session, _xsrf_token


def reset_internal_session() -> None:
    """Drop the cached session/XSRF token. Recovery + test helper."""
    global _session, _xsrf_token
    with _session_lock:
        _session = None
        _xsrf_token = None


def _build_body(search: str, owner_type: str) -> dict:
    """Minimal-cost ListModels body: 1 item, smallest read mask, count only.

    ``totalResults``/``totalModelInstances`` do not depend on ``pageSize`` or
    ``orderBy``, so we ask for a single id-only record to keep the payload tiny.
    """
    return {
        "filter": {
            "id": [],
            "tagIds": [],
            "framework": "MODEL_FRAMEWORK_UNSPECIFIED",
            "searchQuery": search or "",
            "license": "UNSPECIFIED",
            "minUsabilityRating": 0,
            "datasetIds": [],
            "ownerType": owner_type,
        },
        "orderBy": "LIST_MODELS_ORDER_BY_HOTNESS",
        "pageSize": 1,
        "pageToken": "",
        "skip": 0,
        "readMask": "id",
        "privacyFilter": "PUBLIC",
    }


def fetch_model_totals(
    search: str = "", *, owner_type: str = DEFAULT_OWNER_TYPE
) -> Optional[Dict[str, int]]:
    """Return ``{'total_results', 'total_model_instances'}`` or ``None`` on failure.

    Never raises — callers treat ``None`` as "use the public SDK total instead".
    Retries once with a fresh session in case a cached XSRF token went stale
    (which surfaces as 400/401/403).
    """
    if not settings.KAGGLE_USERNAME or not settings.KAGGLE_KEY:
        return None
    body = _build_body(search, owner_type)
    for attempt in (1, 2):
        try:
            sess, xsrf = _get_session(force=(attempt == 2))
            headers = {_XSRF_HEADER: xsrf} if xsrf else {}
            resp = sess.post(
                _LIST_MODELS_URL, json=body, headers=headers, timeout=settings.KAGGLE_TIMEOUT
            )
            if resp.status_code in (400, 401, 403) and attempt == 1:
                # Likely a stale XSRF token / expired session — rebuild and retry.
                reset_internal_session()
                continue
            resp.raise_for_status()
            data = resp.json()
            total_results = data.get("totalResults")
            if total_results is None:
                return None
            return {
                "total_results": int(total_results),
                "total_model_instances": int(data.get("totalModelInstances") or 0),
            }
        except Exception as exc:  # network/parse/etc. — fail soft to the caller
            logger.warning("Kaggle internal model totals failed (attempt %s): %s", attempt, exc)
            if attempt == 1:
                reset_internal_session()
                continue
            return None
    return None
