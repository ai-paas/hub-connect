from app.services.markets.huggingface.huggingface_models import HuggingFaceService
import logging
from app.core.config import settings
from huggingface_hub import HfApi

huggingface_service = HuggingFaceService()
logger = logging.getLogger(__name__)

hf_api = HfApi(token=settings.HF_API_TOKEN)

def get_huggingface_tags():
    try:
        tags_data = hf_api.get_model_tags()
        logger.debug(f"HuggingFace tags data fetched: {tags_data}")
        return tags_data
    except Exception as e:
        logger.error(f"Error fetching HuggingFace tags: {str(e)}")
        return {}
