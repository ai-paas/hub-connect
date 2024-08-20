from typing import Dict, Any, List
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import markdown2
from fastapi.responses import FileResponse
from huggingface_hub import HfApi, ModelCard, hf_hub_download

from app.core.config import settings
from app.core.logging import logger, log_external_api_call
from app.utils.helpers import format_size

hf_api = HfApi(token=settings.HF_API_TOKEN)

HUGGINGFACE_MODELS_JSON_URL = "https://huggingface.co/models-json"
HUGGINGFACE_API_MODELS_URL = "https://huggingface.co/api/models"

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
            response = requests.get(HUGGINGFACE_MODELS_JSON_URL, params=params)
            response.raise_for_status()
            data = response.json()
            models = [model for model in data['models'] if model['repoType'] == 'model']
            return {"models": models, "total": data['numTotalItems']}
        except requests.RequestException as e:
            logger.error(f"Error in get_trending_models: {str(e)}")
            raise

    async def search_models(self, query: str, sort: str, page: int, limit: int) -> Dict[str, Any]:
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
            response = requests.get(HUGGINGFACE_API_MODELS_URL, params=params)
            response.raise_for_status()
            data = response.json()

            for model in data:
                model.pop('siblings', None)

            return {"models": data, "total": len(data)}
        except requests.RequestException as e:
            logger.error(f"Error in search_models: {str(e)}")
            raise

    async def get_model_files(self, model_id: str) -> Dict[str, Any]:
        try:
            repo_info = hf_api.repo_info(repo_id=model_id, repo_type="model", files_metadata=True)

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
            local_path = hf_hub_download(repo_id=model_id, filename=filename, token=settings.HF_API_TOKEN)
            file_name = os.path.basename(local_path)
            return FileResponse(local_path, media_type='application/octet-stream', filename=file_name)
        except Exception as e:
            logger.error(f"Error in download_model_file: {str(e)}")
            raise

    async def get_model_detail(self, model_id: str) -> Dict[str, Any]:
        def fetch_model_info():
            return hf_api.model_info(model_id)

        def fetch_model_card():
            card = ModelCard.load(model_id, token=settings.HF_API_TOKEN)
            return card.data.to_dict(), card.text

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_model_info = executor.submit(fetch_model_info)
                future_model_card = executor.submit(fetch_model_card)

                for future in as_completed([future_model_info, future_model_card]):
                    if future == future_model_info:
                        model_info = future.result()
                    elif future == future_model_card:
                        model_data, model_text = future.result()

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

huggingface_service = HuggingFaceService()