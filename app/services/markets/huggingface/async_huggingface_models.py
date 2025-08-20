from typing import Dict, Any, List
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
import markdown2
from fastapi.responses import FileResponse
from huggingface_hub import HfApi, ModelCard, hf_hub_download
import asyncio
import functools
import aiofiles
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import logger, log_external_api_call
from app.utils.helpers import format_size

# Configure timeouts
REQUESTS_TIMEOUT = 30  # 30 seconds for HTTP requests
HF_API_TIMEOUT = 60    # 60 seconds for HuggingFace API calls
FILE_DOWNLOAD_TIMEOUT = 300  # 5 minutes for file downloads

HUGGINGFACE_MODELS_JSON_URL = "https://huggingface.co/models-json"
HUGGINGFACE_API_MODELS_URL = "https://huggingface.co/api/models"

class AsyncHuggingFaceService:
    def __init__(self):
        self.hf_api = HfApi(token=settings.HF_API_TOKEN)
        self._http_client = None
        
    @asynccontextmanager
    async def get_http_client(self):
        """Get or create HTTP client with connection pooling"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUESTS_TIMEOUT),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
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

    async def get_trending_models(self, page: int, query: str = None) -> Dict[str, Any]:
        """Get trending models using fully async HTTP client"""
        params = {
            "sort": "trending",
            "p": page - 1 if page > 1 else None,
        }
        if query:
            params["search"] = query
        
        try:
            log_external_api_call(HUGGINGFACE_MODELS_JSON_URL, "GET", params=params)
            
            async with self.get_http_client() as client:
                response = await client.get(HUGGINGFACE_MODELS_JSON_URL, params=params)
                response.raise_for_status()
                data = response.json()
                
            models = [model for model in data['models'] if model['repoType'] == 'model']
            return {"models": models, "total": data['numTotalItems']}
        except httpx.HTTPStatusError as e:
            logger.error(f"Error in get_trending_models: {str(e)}")
            raise

    async def search_models(self, query: str, sort: str, page: int, limit: int) -> Dict[str, Any]:
        """Search models using fully async HTTP client"""
        params = {
            "sort": sort,
            "search": query,
            "limit": limit,
            "full": "true",
            "direction": -1,
            "offset": (page - 1) * limit
        }
        
        try:
            log_external_api_call(HUGGINGFACE_API_MODELS_URL, "GET", params=params)
            
            async with self.get_http_client() as client:
                response = await client.get(HUGGINGFACE_API_MODELS_URL, params=params)
                response.raise_for_status()
                data = response.json()

            for model in data:
                model.pop('siblings', None)

            return {"models": data, "total": len(data)}
        except httpx.HTTPStatusError as e:
            logger.error(f"Error in search_models: {str(e)}")
            raise

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

    async def get_model_files(self, model_id: str) -> Dict[str, Any]:
        """Get model files with async HuggingFace API calls"""
        try:
            repo_info = await self._async_hf_api_call(
                self.hf_api.repo_info,
                repo_id=model_id,
                repo_type="model",
                files_metadata=True
            )

            if not hasattr(repo_info, 'siblings') or repo_info.siblings is None:
                return {"files": []}

            files_info = [
                {
                    "name": file.rfilename,
                    "size": format_size(file.size if hasattr(file, 'size') else None),
                    "blob_id": file.blob_id if hasattr(file, 'blob_id') else None
                } for file in repo_info.siblings
            ]

            return {"files": files_info}
        except Exception as e:
            logger.error(f"Error in get_model_files: {str(e)}")
            raise

    async def download_model_file(self, model_id: str, filename: str) -> FileResponse:
        """Download model file with async timeout"""
        try:
            local_path = await self._async_hf_api_call(
                hf_hub_download,
                repo_id=model_id,
                filename=filename,
                token=settings.HF_API_TOKEN
            )
            
            file_name = os.path.basename(local_path)
            return FileResponse(local_path, media_type='application/octet-stream', filename=file_name)
        except Exception as e:
            logger.error(f"Error in download_model_file: {str(e)}")
            raise

    async def get_model_detail(self, model_id: str) -> Dict[str, Any]:
        """Get model details with concurrent async API calls"""
        async def fetch_model_info():
            return await self._async_hf_api_call(
                self.hf_api.model_info,
                model_id
            )

        async def fetch_model_card():
            card = await self._async_hf_api_call(
                ModelCard.load,
                model_id,
                token=settings.HF_API_TOKEN
            )
            return card.data.to_dict(), card.text

        try:
            # Run both API calls concurrently
            results = await asyncio.gather(
                fetch_model_info(),
                fetch_model_card(),
                return_exceptions=True
            )
            
            model_info, model_card_result = results
            
            # Handle exceptions
            if isinstance(model_info, Exception):
                logger.warning(f"Failed to fetch model info: {model_info}")
                model_info = None
                
            if isinstance(model_card_result, Exception):
                logger.warning(f"Failed to fetch model card: {model_card_result}")
                model_data, model_text = {}, ""
            else:
                model_data, model_text = model_card_result

            model_html = markdown2.markdown(model_text, extras=["fenced-code-blocks", "tables"])

            combined_info = {
                "id": model_info.id if model_info else model_id,
                "downloads": model_info.downloads if model_info else None,
                "likes": model_info.likes if model_info else None,
                "lastModified": model_info.lastModified if model_info else None,
                "pipeline_tag": model_info.pipeline_tag if model_info else None,
                "tags": model_info.tags if model_info else [],
                **model_data,
                "card_html": model_html
            }

            return combined_info
        except Exception as e:
            logger.error(f"Error in get_model_detail: {str(e)}")
            raise

    async def get_tags(self) -> Dict[str, Any]:
        """Get HuggingFace tags using async implementation"""
        from app.services.markets.huggingface.async_huggingface_tags import get_async_huggingface_tags
        return await get_async_huggingface_tags()

# Global async service instance
async_huggingface_service = AsyncHuggingFaceService()

# Context manager for proper resource cleanup
@asynccontextmanager
async def get_async_huggingface_service():
    """Context manager for AsyncHuggingFaceService with proper cleanup"""
    try:
        yield async_huggingface_service
    finally:
        await async_huggingface_service.close_http_client()