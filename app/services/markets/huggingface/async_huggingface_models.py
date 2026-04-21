import asyncio
import functools
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

import httpx
import markdown2
from fastapi.responses import FileResponse
from huggingface_hub import HfApi, ModelCard, hf_hub_download, snapshot_download, HfFileSystem
from huggingface_hub.utils import HfHubHTTPError

from app.core.config import settings
from app.core.logging import logger, log_external_api_call
from app.utils.helpers import format_size
from app.utils.parameter_utils import (
    build_huggingface_parameter_filter,
    format_parameter_display,
    categorize_parameter_range
)

# Configure timeouts
REQUESTS_TIMEOUT = 30  # 30 seconds for HTTP requests
HF_API_TIMEOUT = 60    # 60 seconds for HuggingFace API calls
FILE_DOWNLOAD_TIMEOUT = 300  # 5 minutes for file downloads

HUGGINGFACE_MODELS_JSON_URL = "https://huggingface.co/models-json"

class AsyncHuggingFaceService:
    def __init__(self):
        self.hf_api = HfApi(token=settings.HF_API_TOKEN)
        self._http_client = None
        # Dataset-specific setup
        self.fs = HfFileSystem(token=settings.HF_API_TOKEN)
        
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

    async def get_trending_models(
        self,
        page: int,
        query: str = None,
        num_parameters_min: str = None,
        num_parameters_max: str = None,
        pipeline_tag: Optional[str] = None,
        library: Optional[List[str]] = None,
        language: Optional[List[str]] = None,
        license: Optional[str] = None,
        apps: Optional[List[str]] = None,
        inference_provider: Optional[List[str]] = None,
        other: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get trending models using fully async HTTP client with parameter filtering"""
        params = {
            "sort": "trending",
            "p": page - 1 if page > 1 else None,
            "withCount": True
        }
        if query:
            params["search"] = query

        # Add parameter filter if specified
        param_filter = build_huggingface_parameter_filter(num_parameters_min, num_parameters_max)
        if param_filter:
            params["num_parameters"] = param_filter

        # Add tag/attribute filters
        if pipeline_tag:
            params["pipeline_tag"] = pipeline_tag

        # Multi-select filters (join with comma)
        if library:
            params["library"] = ",".join(library)

        if language:
            params["language"] = ",".join(language)

        if license:
            params["license"] = license

        if apps:
            params["apps"] = ",".join(apps)

        if inference_provider:
            params["inference_provider"] = ",".join(inference_provider)

        if other:
            params["other"] = ",".join(other)

        try:
            log_external_api_call(HUGGINGFACE_MODELS_JSON_URL, "GET", params=params)

            async with self.get_http_client() as client:
                response = await client.get(HUGGINGFACE_MODELS_JSON_URL, params=params)
                response.raise_for_status()
                data = response.json()

            models = [model for model in data['models'] if model['repoType'] == 'model']

            # Enhance models with parameter display information
            for model in models:
                if 'numParameters' in model and model['numParameters']:
                    model['parameterDisplay'] = format_parameter_display(model['numParameters'])
                    model['parameterRange'] = categorize_parameter_range(model['numParameters'])

            result = {"models": models, "total": data['numTotalItems']}

            # Include applied filters in response
            applied_filters = {}
            if param_filter:
                if num_parameters_min:
                    applied_filters['num_parameters_min'] = num_parameters_min
                if num_parameters_max:
                    applied_filters['num_parameters_max'] = num_parameters_max

            if pipeline_tag:
                applied_filters['pipeline_tag'] = pipeline_tag
            if library:
                applied_filters['library'] = library
            if language:
                applied_filters['language'] = language
            if license:
                applied_filters['license'] = license
            if apps:
                applied_filters['apps'] = apps
            if inference_provider:
                applied_filters['inference_provider'] = inference_provider
            if other:
                applied_filters['other'] = other

            if applied_filters:
                result['applied_filters'] = applied_filters

            return result
        except httpx.HTTPStatusError as e:
            logger.error(f"Error in get_trending_models: {str(e)}")
            raise

    async def search_models(
        self,
        query: str,
        sort: str,
        page: int,
        limit: int,
        num_parameters_min: str = None,
        num_parameters_max: str = None,
        pipeline_tag: Optional[str] = None,
        library: Optional[List[str]] = None,
        language: Optional[List[str]] = None,
        license: Optional[str] = None,
        apps: Optional[List[str]] = None,
        inference_provider: Optional[List[str]] = None,
        other: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search models using models-json API with parameter filtering"""
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

        # Add parameter filter if specified
        param_filter = build_huggingface_parameter_filter(num_parameters_min, num_parameters_max)
        if param_filter:
            params["num_parameters"] = param_filter

        # Add tag/attribute filters
        if pipeline_tag:
            params["pipeline_tag"] = pipeline_tag

        # Multi-select filters (join with comma)
        if library:
            params["library"] = ",".join(library)

        if language:
            params["language"] = ",".join(language)

        if license:
            params["license"] = license

        if apps:
            params["apps"] = ",".join(apps)

        if inference_provider:
            params["inference_provider"] = ",".join(inference_provider)

        if other:
            params["other"] = ",".join(other)

        try:
            log_external_api_call(HUGGINGFACE_MODELS_JSON_URL, "GET", params=params)

            async with self.get_http_client() as client:
                response = await client.get(HUGGINGFACE_MODELS_JSON_URL, params=params)
                response.raise_for_status()
                data = response.json()

            # Filter only models (exclude spaces)
            models = [model for model in data['models'] if model['repoType'] == 'model']

            # Enhance models with parameter display information
            for model in models:
                if 'numParameters' in model and model['numParameters']:
                    model['parameterDisplay'] = format_parameter_display(model['numParameters'])
                    model['parameterRange'] = categorize_parameter_range(model['numParameters'])

            result = {"models": models, "total": data['numTotalItems']}

            # Include applied filters in response
            applied_filters = {}
            if param_filter:
                if num_parameters_min:
                    applied_filters['num_parameters_min'] = num_parameters_min
                if num_parameters_max:
                    applied_filters['num_parameters_max'] = num_parameters_max

            if pipeline_tag:
                applied_filters['pipeline_tag'] = pipeline_tag
            if library:
                applied_filters['library'] = library
            if language:
                applied_filters['language'] = language
            if license:
                applied_filters['license'] = license
            if apps:
                applied_filters['apps'] = apps
            if inference_provider:
                applied_filters['inference_provider'] = inference_provider
            if other:
                applied_filters['other'] = other

            if applied_filters:
                result['applied_filters'] = applied_filters

            return result
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

    async def download_model_file(self, model_id: str, filename: str, download_dir: Optional[str] = None):
        """Download model file with optional custom path"""
        import shutil
        
        try:
            # Download to cache first
            cached_path = await self._async_hf_api_call(
                hf_hub_download,
                repo_id=model_id,
                filename=filename,
                token=settings.HF_API_TOKEN
            )
            
            # If custom download directory specified, copy file there and return path info
            if download_dir:
                target_dir = os.path.expanduser(download_dir)  # Support ~ expansion
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, filename)
                await asyncio.to_thread(shutil.copy2, cached_path, target_path)
                
                # Return JSON with custom path info
                return {
                    "download_type": "custom_path",
                    "file_path": target_path,
                    "file_size": os.path.getsize(target_path),
                    "filename": filename,
                    "model_id": model_id
                }
            
            # Default: Return FileResponse for direct download
            file_name = os.path.basename(cached_path)
            return FileResponse(cached_path, media_type='application/octet-stream', filename=file_name)
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

    # =============================================================================
    # Dataset Methods
    # =============================================================================

    async def search_datasets(self, sort: str = "likes", page: int = 1, page_size: int = 10):
        """Search datasets from HuggingFace"""
        try:
            url = f"https://huggingface.co/datasets-json?sort={sort}&withCount=true"
            async with self.get_http_client() as http_client:
                response = await http_client.get(url, timeout=REQUESTS_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                
                datasets = data.get("datasets", [])
                start = (page - 1) * page_size
                end = start + page_size
                paginated_datasets = datasets[start:end]
                
                return {
                    "datasets": paginated_datasets,
                    "total": len(datasets),
                    "page": page,
                    "page_size": page_size
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Error searching datasets: {e}")
            raise Exception(f"Error searching for datasets: {e}")

    async def get_dataset_info(self, repo_id: str):
        """Get dataset info from datasets-server API"""
        try:
            url = f"https://datasets-server.huggingface.co/info?dataset={repo_id}"
            async with self.get_http_client() as http_client:
                response = await http_client.get(url, timeout=REQUESTS_TIMEOUT)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise Exception(f"Dataset not found: {repo_id}")
            logger.error(f"Error getting dataset info: {e}")
            raise Exception(f"Error getting dataset info: {e}")

    async def get_dataset_files(self, repo_id: str):
        """Get dataset file tree"""
        try:
            # Use HuggingFace API endpoint for file listing
            url = f"https://huggingface.co/api/datasets/{repo_id}/revision/main?expand[]=siblings"
            async with self.get_http_client() as http_client:
                response = await http_client.get(url, timeout=REQUESTS_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                
                # Convert to expected format
                result = []
                siblings = data.get("siblings", [])
                for sibling in siblings:
                    result.append({
                        "path": sibling["rfilename"],
                        "type": "file",
                        "size": 0,  # Size not provided in this API
                        "blob_id": None,
                        "lfs": None
                    })
                
                return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise Exception(f"Dataset not found: {repo_id}")
            logger.error(f"Error getting dataset files: {e}")
            raise Exception(f"Error getting dataset file tree: {e}")

    async def download_file(self, repo_id: str, filename: str, revision: Optional[str] = None, download_dir: Optional[str] = None):
        """Download dataset file with optional custom path"""
        import shutil
        
        try:
            # Try without token first (for public repos)
            try:
                cached_path = await self._async_hf_api_call(
                    hf_hub_download,
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    repo_type="dataset"
                )
            except HfHubHTTPError:
                # If fails, try with token (for private repos)
                cached_path = await self._async_hf_api_call(
                    hf_hub_download,
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    repo_type="dataset",
                    token=settings.HF_API_TOKEN
                )
            
            # If custom download directory specified, copy file there and return path info
            if download_dir:
                target_dir = os.path.expanduser(download_dir)  # Support ~ expansion
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, filename)
                await asyncio.to_thread(shutil.copy2, cached_path, target_path)
                
                # Return JSON with custom path info
                return {
                    "download_type": "custom_path",
                    "file_path": target_path,
                    "file_size": os.path.getsize(target_path),
                    "filename": filename,
                    "repo_id": repo_id
                }
            
            # Default: Return FileResponse for direct download
            file_name = os.path.basename(cached_path)
            return FileResponse(cached_path, media_type='application/octet-stream', filename=file_name)
        except HfHubHTTPError as e:
            if e.response.status_code == 404:
                raise Exception(f"File not found in dataset: {filename}")
            logger.error(f"Error downloading dataset file: {e}")
            raise Exception(f"Error downloading file: {e}")

    async def download_snapshot(self, repo_id: str, revision: Optional[str] = None, allow_patterns: Optional[List[str]] = None, ignore_patterns: Optional[List[str]] = None, download_dir: Optional[str] = None):
        """Download dataset snapshot with optional custom path"""
        try:
            # If custom download directory specified, download directly there
            if download_dir:
                target_dir = os.path.expanduser(download_dir)
                
                # Try without token first (for public repos)
                try:
                    local_path = await self._async_hf_api_call(
                        snapshot_download,
                        repo_id=repo_id,
                        revision=revision,
                        allow_patterns=allow_patterns,
                        ignore_patterns=ignore_patterns,
                        repo_type="dataset",
                        local_dir=target_dir
                    )
                except HfHubHTTPError:
                    # If fails, try with token (for private repos)
                    local_path = await self._async_hf_api_call(
                        snapshot_download,
                        repo_id=repo_id,
                        revision=revision,
                        allow_patterns=allow_patterns,
                        ignore_patterns=ignore_patterns,
                        repo_type="dataset",
                        token=settings.HF_API_TOKEN,
                        local_dir=target_dir
                    )
                
                # Return JSON with download info
                return {
                    "download_type": "custom_snapshot",
                    "snapshot_path": local_path,
                    "repo_id": repo_id,
                    "total_files": len([f for f in os.listdir(local_path) if os.path.isfile(os.path.join(local_path, f))]) if os.path.exists(local_path) else 0
                }
            
            # Default: Download to cache and return cached path info
            try:
                cached_path = await self._async_hf_api_call(
                    snapshot_download,
                    repo_id=repo_id,
                    revision=revision,
                    allow_patterns=allow_patterns,
                    ignore_patterns=ignore_patterns,
                    repo_type="dataset"
                )
            except HfHubHTTPError:
                cached_path = await self._async_hf_api_call(
                    snapshot_download,
                    repo_id=repo_id,
                    revision=revision,
                    allow_patterns=allow_patterns,
                    ignore_patterns=ignore_patterns,
                    repo_type="dataset",
                    token=settings.HF_API_TOKEN
                )
            
            # Return JSON with cache path info for default behavior
            return {
                "download_type": "cached_snapshot",
                "snapshot_path": cached_path,
                "repo_id": repo_id,
                "message": "Files downloaded to HuggingFace cache. Access via snapshot_path."
            }
        except HfHubHTTPError as e:
            if e.response.status_code == 404:
                raise Exception(f"Dataset not found: {repo_id}")
            logger.error(f"Error downloading dataset snapshot: {e}")
            raise Exception(f"Error downloading snapshot: {e}")

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