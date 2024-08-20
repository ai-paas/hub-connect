from app.services.markets.aihub.aihub_models import AihubService
import logging

aihub_service = AihubService()
logger = logging.getLogger(__name__)

def get_aihub_tags():
    try:
        tags_data = "empty"
        logger.debug(f"AIHub tags data fetched: {tags_data}")
        return tags_data
    except Exception as e:
        logger.error(f"Error fetching AIHub tags: {str(e)}")
        return {}
