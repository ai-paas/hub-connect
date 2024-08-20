from fastapi import APIRouter, HTTPException, Query
from app.services.caching import cache_data, get_cached_data
from app.core.config import settings
from app.services.markets.common import get_market_service
import logging

router = APIRouter(tags=["tags"])
logger = logging.getLogger(__name__)

INTERNAL_SERVER_ERROR_MESSAGE = "Internal Server Error"

@router.get("/")
async def api_tags(market: str = Query(..., description="The market to fetch tags for")):
    try:
        cache_key = f"{market}_tag_cache"
        data, _ = await get_cached_data(cache_key)
        if not data:
            market_service = get_market_service(market)
            data = market_service.get_tags()
            if not data:
                raise HTTPException(status_code=500, detail="Failed to retrieve tags")
            await cache_data(cache_key, data)
        return data
    except Exception as e:
        logger.error(f"Error in api_tags: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)

@router.get("/{group}")
async def api_tags_group(market: str, group: str):
    if group not in settings.GROUPS:
        raise HTTPException(status_code=404, detail="Group not found")

    try:
        cache_key = f"{market}_{group}_data"
        data, _ = await get_cached_data(cache_key)
        if not data:
            market_service = get_market_service(market)
            all_tags = market_service.get_tags()
            data = all_tags.get(group, [])
            await cache_data(cache_key, data)

        if group in settings.LIMITED_GROUPS:
            limited_data = data[:settings.LIMIT] if isinstance(data, list) else list(data.items())[:settings.LIMIT]
            remaining_count = len(data) - settings.LIMIT if len(data) > settings.LIMIT else 0
            return {"data": limited_data, "remaining_count": remaining_count}
        return {"data": data, "remaining_count": 0}
    except Exception as e:
        logger.error(f"Error in api_tags_group: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)

@router.get("/{group}/all")
async def api_tags_group_all(market: str, group: str):
    if group not in settings.GROUPS:
        raise HTTPException(status_code=404, detail="Group not found")

    try:
        cache_key = f"{market}_{group}_data"
        data, _ = await get_cached_data(cache_key)
        if not data:
            market_service = get_market_service(market)
            all_tags = market_service.get_tags()
            data = all_tags.get(group, [])
            await cache_data(cache_key, data)

        return {"data": data}
    except Exception as e:
        logger.error(f"Error in api_tags_group_all: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)
