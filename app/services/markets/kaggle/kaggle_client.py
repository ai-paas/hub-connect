import os
import threading
from typing import Optional

from fastapi import HTTPException

from app.core.config import settings
from app.core.logging import logger

_client_lock = threading.Lock()
_kaggle_api_singleton = None


def _require_credentials() -> None:
    if not settings.KAGGLE_USERNAME or not settings.KAGGLE_KEY:
        raise HTTPException(
            status_code=503,
            detail="Kaggle credentials not configured",
        )


def get_kaggle_client():
    """Return an authenticated KaggleApi singleton.

    Credentials are injected via environment variables rather than writing a
    kaggle.json file, so the container filesystem stays read-only friendly.
    The kaggle package import is deferred until first call so that projects
    without the optional dependency can still boot for HuggingFace-only use.
    """
    global _kaggle_api_singleton
    if _kaggle_api_singleton is not None:
        return _kaggle_api_singleton

    _require_credentials()

    with _client_lock:
        if _kaggle_api_singleton is not None:
            return _kaggle_api_singleton

        os.environ["KAGGLE_USERNAME"] = settings.KAGGLE_USERNAME
        os.environ["KAGGLE_KEY"] = settings.KAGGLE_KEY

        try:
            from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore
        except ImportError as exc:
            logger.error("kaggle package is not installed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Kaggle client library is not installed",
            ) from exc

        api = KaggleApi()
        try:
            api.authenticate()
        except Exception as exc:  # pragma: no cover - network/auth edge
            logger.error("Kaggle authentication failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Kaggle authentication failed",
            ) from exc

        _kaggle_api_singleton = api
        logger.info("Kaggle API client authenticated as %s", settings.KAGGLE_USERNAME)
        return _kaggle_api_singleton


def reset_kaggle_client_for_testing(api: Optional[object] = None) -> None:
    """Replace or clear the cached KaggleApi singleton. Test-only helper."""
    global _kaggle_api_singleton
    _kaggle_api_singleton = api
