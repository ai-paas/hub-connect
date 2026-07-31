import asyncio
from typing import Optional, List

import httpx
import yaml
from aiocache import cached
from fastapi import HTTPException
from fastapi.responses import FileResponse
from huggingface_hub import hf_hub_download, snapshot_download, HfFileSystem, HfApi
from huggingface_hub.utils import HfHubHTTPError

from app.core.config import settings
from app.core.logging import logger


class HuggingFaceDatasetService:
    def __init__(self):
        # Public API calls don't need authentication
        self.http_client = httpx.AsyncClient()
        # File system and API operations may need token for private repos
        self.fs = HfFileSystem(token=settings.HF_API_TOKEN)
        self.api = HfApi(token=settings.HF_API_TOKEN)

    @cached(ttl=3600)
    async def search_datasets(self, query: str = "", sort: str = "likes", page: int = 1, page_size: int = 10):
        try:
            params = {"sort": sort, "withCount": "true"}
            if query:
                params["search"] = query
            url = "https://huggingface.co/datasets-json"
            effective_page = max(1, page)
            effective_page_size = max(1, min(page_size, 100))
            upstream_page_size = 30
            start = (effective_page - 1) * effective_page_size
            end = start + effective_page_size
            first_upstream_page = start // upstream_page_size
            last_upstream_page = (end - 1) // upstream_page_size
            datasets = []
            total = 0
            for upstream_page in range(first_upstream_page, last_upstream_page + 1):
                page_params = dict(params)
                if upstream_page:
                    page_params["p"] = upstream_page
                response = await self.http_client.get(url, params=page_params)
                response.raise_for_status()
                data = response.json()
                total = int(data.get("numTotalItems", total) or 0)
                datasets.extend(data.get("datasets", []))

            offset = start - first_upstream_page * upstream_page_size
            paginated_datasets = datasets[offset:offset + effective_page_size]

            return {
                "datasets": paginated_datasets,
                "total": total,
                "page": effective_page,
                "page_size": effective_page_size,
                "has_more": start + len(paginated_datasets) < total,
                "total_is_exact": True,
            }
        except httpx.HTTPStatusError as e:
            logger.warning("Hugging Face dataset search failed: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail="Error searching for datasets")

    @cached(ttl=3600)
    async def get_dataset_card(self, repo_id: str, revision: str = "main"):
        try:
            # Try to download README.md without token first (for public repos)
            try:
                readme_path = await asyncio.to_thread(
                    hf_hub_download,
                    repo_id=repo_id,
                    filename="README.md",
                    revision=revision,
                    repo_type="dataset"
                )
            except HfHubHTTPError:
                # If fails, try with token (for private repos)
                readme_path = await asyncio.to_thread(
                    hf_hub_download,
                    repo_id=repo_id,
                    filename="README.md",
                    revision=revision,
                    repo_type="dataset",
                    token=settings.HF_API_TOKEN
                )
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Extract YAML front matter
            parts = content.split("---")
            if len(parts) > 2:
                yaml_content = parts[1]
                card_data = yaml.safe_load(yaml_content)
                return card_data
            return None
        except HfHubHTTPError as e:
            if e.response.status_code == 404:
                return None # README.md not found, which is fine
            logger.warning("Hugging Face dataset card failed: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail="Error getting dataset card")
        except Exception:
            return None

    @cached(ttl=3600)
    async def get_dataset_info(self, repo_id: str):
        try:
            url = f"https://datasets-server.huggingface.co/info?dataset={repo_id}"
            response = await self.http_client.get(url)
            response.raise_for_status()
            info = response.json()
            card_data = await self.get_dataset_card(repo_id)
            if card_data:
                info["cardData"] = card_data
            return info
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Dataset not found: {repo_id}")
            logger.warning("Hugging Face dataset info failed: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail="Error getting dataset info")

    @cached(ttl=3600)
    async def get_dataset_files(self, repo_id: str):
        try:
            # Use HuggingFace API endpoint for file listing
            url = f"https://huggingface.co/api/datasets/{repo_id}/revision/main?expand[]=siblings"
            response = await self.http_client.get(url)
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
                raise HTTPException(status_code=404, detail=f"Dataset not found: {repo_id}")
            logger.warning("Hugging Face dataset file tree failed: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail="Error getting dataset file tree")
        except Exception:
            logger.exception("Hugging Face dataset file tree failed")
            raise HTTPException(status_code=500, detail="Error getting dataset file tree")

    async def download_file(self, repo_id: str, filename: str, revision: Optional[str] = None, download_dir: Optional[str] = None):
        import os
        import shutil
        
        try:
            # Try without token first (for public repos)
            try:
                cached_path = await asyncio.to_thread(
                    hf_hub_download,
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    repo_type="dataset"
                )
            except HfHubHTTPError:
                # If fails, try with token (for private repos)
                cached_path = await asyncio.to_thread(
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
                raise HTTPException(status_code=404, detail=f"File not found in dataset: {filename}")
            logger.warning("Hugging Face dataset file download failed: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail="Error downloading file")
        except Exception:
            logger.exception("Hugging Face dataset file download failed")
            raise HTTPException(status_code=500, detail="Error downloading file")

    async def download_snapshot(self, repo_id: str, revision: Optional[str] = None, allow_patterns: Optional[List[str]] = None, ignore_patterns: Optional[List[str]] = None, download_dir: Optional[str] = None):
        import os
        
        try:
            # If custom download directory specified, download directly there
            if download_dir:
                target_dir = os.path.expanduser(download_dir)
                
                # Try without token first (for public repos)
                try:
                    local_path = await asyncio.to_thread(
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
                    local_path = await asyncio.to_thread(
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
            
            # Default: Download to cache and return cached path (for potential zip/tar response later)
            try:
                cached_path = await asyncio.to_thread(
                    snapshot_download,
                    repo_id=repo_id,
                    revision=revision,
                    allow_patterns=allow_patterns,
                    ignore_patterns=ignore_patterns,
                    repo_type="dataset"
                )
            except HfHubHTTPError:
                cached_path = await asyncio.to_thread(
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
                raise HTTPException(status_code=404, detail=f"Dataset not found: {repo_id}")
            logger.warning("Hugging Face dataset snapshot download failed: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail="Error downloading snapshot")
        except Exception:
            logger.exception("Hugging Face dataset snapshot download failed")
            raise HTTPException(status_code=500, detail="Error downloading snapshot")
