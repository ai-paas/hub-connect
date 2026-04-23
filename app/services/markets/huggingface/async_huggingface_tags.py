import asyncio
import functools
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

import httpx
from huggingface_hub import HfApi

from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure timeout for HuggingFace API calls
HF_API_TIMEOUT = 30  # 30 seconds for tags API
HTTP_TIMEOUT = 20    # 20 seconds for HTTP requests

class AsyncHuggingFaceTagsService:
    def __init__(self):
        self.hf_api = HfApi(token=settings.HF_API_TOKEN)
        self._http_client = None
        
    @asynccontextmanager
    async def get_http_client(self):
        """Get or create HTTP client with connection pooling"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(HTTP_TIMEOUT),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=50)
            )
        
        try:
            yield self._http_client
        finally:
            # Client stays alive for reuse
            pass
    
    async def close_http_client(self):
        """Close HTTP client when service is shut down"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _async_hf_api_call(self, func, *args, **kwargs):
        """Wrapper for HuggingFace API calls with timeout and thread pool"""
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(
                None,
                functools.partial(func, *args, **kwargs)
            ),
            timeout=HF_API_TIMEOUT
        )

    async def get_tags(self) -> Dict[str, Any]:
        """Get HuggingFace tags using async API call"""
        try:
            tags_data = await self._async_hf_api_call(
                self.hf_api.get_model_tags
            )
            logger.debug(f"HuggingFace tags data fetched: {tags_data}")
            return tags_data
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching HuggingFace tags after {HF_API_TIMEOUT} seconds")
            return {}
        except Exception as e:
            logger.error(f"Error fetching HuggingFace tags: {str(e)}")
            return {}

# Global async service instance
async_huggingface_tags_service = AsyncHuggingFaceTagsService()

async def get_async_huggingface_tags() -> Dict[str, Any]:
    """Get HuggingFace tags using async implementation"""
    return await async_huggingface_tags_service.get_tags()

# Context manager for proper resource cleanup
@asynccontextmanager
async def get_async_huggingface_tags_service():
    """Context manager for AsyncHuggingFaceTagsService with proper cleanup"""
    try:
        yield async_huggingface_tags_service
    finally:
        await async_huggingface_tags_service.close_http_client()