import asyncio
import logging

from huggingface_hub import HfApi

from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure timeout for HuggingFace API calls
HF_API_TIMEOUT = 30  # 30 seconds for tags API

hf_api = HfApi(token=settings.HF_API_TOKEN)

async def get_huggingface_tags():
    try:
        # Run HuggingFace API call with timeout in thread pool
        loop = asyncio.get_event_loop()
        tags_data = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                hf_api.get_model_tags
            ),
            timeout=HF_API_TIMEOUT
        )
        logger.debug(f"HuggingFace tags data fetched: {tags_data}")
        return tags_data
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching HuggingFace tags after {HF_API_TIMEOUT} seconds")
        return {}
    except Exception as e:
        logger.error(f"Error fetching HuggingFace tags: {str(e)}")
        return {}
