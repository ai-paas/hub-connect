from typing import Dict, Any, List
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
import markdown2
from fastapi.responses import FileResponse
from huggingface_hub import HfApi, ModelCard, hf_hub_download
import asyncio
import functools

from app.core.config import settings
from app.core.logging import logger, log_external_api_call
from app.utils.helpers import format_size

# Configure timeouts
REQUESTS_TIMEOUT = 30  # 30 seconds for HTTP requests
HF_API_TIMEOUT = 60    # 60 seconds for HuggingFace API calls
FILE_DOWNLOAD_TIMEOUT = 300  # 5 minutes for file downloads

hf_api = HfApi(token=settings.HF_API_TOKEN)
async_client = httpx.AsyncClient(timeout=REQUESTS_TIMEOUT)

HUGGINGFACE_MODELS_JSON_URL = "https://huggingface.co/models-json"

class HuggingFaceService:
    async def get_trending_models(self, page: int, query: str = None) -> Dict[str, Any]:
        params = {
            "sort": "trending",
            "p": page - 1 if page > 1 else None,
        }
        if query:
            params["search"] = query
        try:
            log_external_api_call(HUGGINGFACE_MODELS_JSON_URL, "GET", params=params)
            response = await async_client.get(HUGGINGFACE_MODELS_JSON_URL, params=params)
            response.raise_for_status()
            data = response.json()
            models = [model for model in data['models'] if model['repoType'] == 'model']
            return {"models": models, "total": data['numTotalItems']}
        except httpx.HTTPStatusError as e:
            logger.error(f"Error in get_trending_models: {str(e)}")
            raise

    async def search_models(self, query: str, sort: str, page: int, limit: int) -> Dict[str, Any]:
        """Search models using models-json API"""
        params = {
            "sort": sort,
            "withCount": True
        }

        # Add search query if provided
        if query:
            params["search"] = query

        # Add pagination (models-json uses p parameter, 0-indexed)
        # Note: models-json returns 30 items per page by default
        if page > 1:
            params["p"] = page - 1

        try:
            log_external_api_call(HUGGINGFACE_MODELS_JSON_URL, "GET", params=params)
            response = await async_client.get(HUGGINGFACE_MODELS_JSON_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Filter only models (exclude spaces)
            models = [model for model in data['models'] if model['repoType'] == 'model']

            return {"models": models, "total": data['numTotalItems']}
        except httpx.HTTPStatusError as e:
            logger.error(f"Error in search_models: {str(e)}")
            raise

    async def get_model_files(self, model_id: str) -> Dict[str, Any]:
        try:
            # Run HuggingFace API call with timeout in thread pool
            loop = asyncio.get_event_loop()
            repo_info = await asyncio.wait_for(
                loop.run_in_executor(
                    None, 
                    functools.partial(
                        hf_api.repo_info, 
                        repo_id=model_id, 
                        repo_type="model", 
                        files_metadata=True
                    )
                ), 
                timeout=HF_API_TIMEOUT
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
        try:
            # Run file download with timeout in thread pool
            loop = asyncio.get_event_loop()
            local_path = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    functools.partial(
                        hf_hub_download,
                        repo_id=model_id,
                        filename=filename,
                        token=settings.HF_API_TOKEN
                    )
                ),
                timeout=FILE_DOWNLOAD_TIMEOUT
            )
            file_name = os.path.basename(local_path)
            return FileResponse(local_path, media_type='application/octet-stream', filename=file_name)
        except Exception as e:
            logger.error(f"Error in download_model_file: {str(e)}")
            raise

    async def get_model_detail(self, model_id: str) -> Dict[str, Any]:
        async def fetch_model_info():
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    functools.partial(hf_api.model_info, model_id)
                ),
                timeout=HF_API_TIMEOUT
            )

        async def fetch_model_card():
            loop = asyncio.get_event_loop()
            card = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    functools.partial(
                        ModelCard.load,
                        model_id,
                        token=settings.HF_API_TOKEN
                    )
                ),
                timeout=HF_API_TIMEOUT
            )
            return card.data.to_dict(), card.text

        try:
            # Run both API calls concurrently with timeout
            model_info_task = asyncio.create_task(fetch_model_info())
            model_card_task = asyncio.create_task(fetch_model_card())
            
            model_info, (model_data, model_text) = await asyncio.gather(
                model_info_task,
                model_card_task,
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(model_info, Exception):
                logger.warning(f"Failed to fetch model info: {model_info}")
                model_info = None
            if isinstance(model_data, Exception):
                logger.warning(f"Failed to fetch model card: {model_data}")
                model_data, model_text = {}, ""

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
        """Get HuggingFace tags"""
        from app.services.markets.huggingface.huggingface_tags import get_huggingface_tags
        return await get_huggingface_tags()

huggingface_service = HuggingFaceService()