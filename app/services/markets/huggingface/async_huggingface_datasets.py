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
            response = await self.http_client.get(url, params=params)
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
                "page_size": page_size,
                "has_more": end < len(datasets),
                "total_is_exact": True,
            }
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Error searching for datasets: {e}")

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
            raise HTTPException(status_code=e.response.status_code, detail=f"Error getting dataset card: {e}")
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
            raise HTTPException(status_code=e.response.status_code, detail=f"Error getting dataset info: {e}")

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
            raise HTTPException(status_code=e.response.status_code, detail=f"Error getting dataset file tree: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
            raise HTTPException(status_code=e.response.status_code, detail=f"Error downloading file: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
            raise HTTPException(status_code=e.response.status_code, detail=f"Error downloading snapshot: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
