from fastapi import APIRouter, HTTPException, Query, Path, Depends
from app.services.caching import cache_data, get_cached_data
from app.core.config import settings
from app.services.markets.async_common import get_async_market_service
from app.core.auth import get_current_user
from app.core.logging import logger

router = APIRouter(tags=["tags"])

INTERNAL_SERVER_ERROR_MESSAGE = "Internal Server Error"

@router.get("/", summary="Get all tag groups")
async def api_tags(
    market: str = Query(
        ..., 
        description="AI model marketplace (huggingface, aihub)", 
        examples=["huggingface"]
    ), 
    current_user: dict = Depends(get_current_user)
):
    try:
        cache_key = f"{market}_tag_cache"
        logger.debug(f"Checking cache for key: {cache_key}")
        data, data_hash = await get_cached_data(cache_key)
        
        if data:
            logger.info(f"Cache HIT for {market} tags - returning cached data")
            return data
        else:
            logger.info(f"Cache MISS for {market} tags - fetching from external API")
            market_service = await get_async_market_service(market)
            data = await market_service.get_tags()
            if not data:
                raise HTTPException(status_code=500, detail="Failed to retrieve tags")
            await cache_data(cache_key, data)
            logger.info(f"Cached fresh data for {market} tags")
            return data
    except Exception as e:
        logger.error(f"Error in api_tags: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)

@router.get("/{group}", summary="Get tags for a specific group (limited)")
async def api_tags_group(
    group: str = Path(
        ..., 
        description="Tag group name (region, other, library, license, language, dataset, pipeline_tag)",
        examples=["library"]
    ), 
    market: str = Query(
        ..., 
        description="AI model marketplace (huggingface, aihub)", 
        examples=["huggingface"]
    ), 
    current_user: dict = Depends(get_current_user)
):
    if group not in settings.GROUPS:
        raise HTTPException(status_code=404, detail="Group not found")

    try:
        cache_key = f"{market}_{group}_data"
        data, _ = await get_cached_data(cache_key)
        if not data:
            market_service = await get_async_market_service(market)
            all_tags = await market_service.get_tags()
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

@router.get("/{group}/all", summary="Get all tags for a specific group (unlimited)")
async def api_tags_group_all(
    group: str = Path(
        ..., 
        description="Tag group name (region, other, library, license, language, dataset, pipeline_tag)",
        examples=["language"]
    ), 
    market: str = Query(
        ..., 
        description="AI model marketplace (huggingface, aihub)", 
        examples=["huggingface"]
    ), 
    current_user: dict = Depends(get_current_user)
):
    if group not in settings.GROUPS:
        raise HTTPException(status_code=404, detail="Group not found")

    try:
        cache_key = f"{market}_{group}_data"
        data, _ = await get_cached_data(cache_key)
        if not data:
            market_service = await get_async_market_service(market)
            all_tags = await market_service.get_tags()
            data = all_tags.get(group, [])
            await cache_data(cache_key, data)

        return {"data": data}
    except Exception as e:
        logger.error(f"Error in api_tags_group_all: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)
