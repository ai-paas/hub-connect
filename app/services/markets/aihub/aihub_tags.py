from app.core.logging import logger
from app.services.markets.aihub.aihub_models import AihubService

# Global service instance
aihub_service = AihubService()

async def get_aihub_tags():
    """
    Fetch AIHub tags using the service instance.
    
    Returns:
        Dict containing AIHub tag categories (currently empty placeholder)
    """
    try:
        tags_data = await aihub_service.get_tags()
        logger.debug("AIHub tags data fetched successfully")
        return tags_data
    except Exception as e:
        logger.error(f"Error fetching AIHub tags: {str(e)}")
        return {}
