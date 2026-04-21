from fastapi import APIRouter, HTTPException, Query, Path, Depends

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.logging import logger
from app.services.caching import cache_data, get_cached_data
from app.services.markets.async_common import get_async_market_service

router = APIRouter(tags=["tags"])

INTERNAL_SERVER_ERROR_MESSAGE = "Internal Server Error"

@router.get(
    "/",
    summary="전체 태그 그룹 조회",
    description=(
        "선택한 마켓의 전체 태그 그룹 데이터를 조회합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| region | 지역 태그 목록입니다. |\n"
        "| other | 기타 태그 목록입니다. |\n"
        "| library | 라이브러리 태그 목록입니다. |\n"
        "| license | 라이선스 태그 목록입니다. |\n"
        "| language | 언어 태그 목록입니다. |\n"
        "| dataset | 데이터셋 관련 태그 목록입니다. |\n"
        "| pipeline_tag | 파이프라인 태그 목록입니다. |"
    ),
    responses={
        200: {
            "description": "전체 태그 그룹을 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "region": [],
                        "other": [],
                        "library": [{"id": "transformers", "label": "Transformers"}],
                        "license": [{"id": "apache-2.0", "label": "Apache 2.0"}],
                        "language": [{"id": "en", "label": "English"}],
                        "dataset": [],
                        "pipeline_tag": [{"id": "text-generation", "label": "Text Generation"}],
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "태그 그룹 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "Internal Server Error"}}},
        },
    },
)
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

@router.get(
    "/{group}",
    summary="특정 태그 그룹 조회",
    description=(
        "특정 태그 그룹의 값을 조회합니다. 일부 그룹은 설정된 개수만큼만 반환하며 나머지 개수는 `remaining_count`로 제공합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| group | path | Y | 태그 그룹 이름입니다. | library |\n"
        "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| data | 태그 데이터 목록 또는 매핑입니다. |\n"
        "| remaining_count | 제한 조회 후 남은 개수입니다. |"
    ),
    responses={
        200: {
            "description": "태그 그룹을 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "data": [
                            {"id": "transformers", "label": "Transformers"},
                            {"id": "peft", "label": "PEFT"},
                        ],
                        "remaining_count": 12,
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        404: {
            "description": "지원하지 않는 태그 그룹입니다.",
            "content": {"application/json": {"example": {"detail": "Group not found"}}},
        },
        500: {
            "description": "태그 그룹 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "Internal Server Error"}}},
        },
    },
)
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

@router.get(
    "/{group}/all",
    summary="특정 태그 그룹 전체 조회",
    description=(
        "특정 태그 그룹의 전체 데이터를 제한 없이 조회합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| group | path | Y | 태그 그룹 이름입니다. | language |\n"
        "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| data | 태그 데이터 전체 목록 또는 매핑입니다. |"
    ),
    responses={
        200: {
            "description": "태그 그룹 전체 데이터를 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "data": [
                            {"id": "en", "label": "English"},
                            {"id": "ko", "label": "Korean"},
                        ]
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        404: {
            "description": "지원하지 않는 태그 그룹입니다.",
            "content": {"application/json": {"example": {"detail": "Group not found"}}},
        },
        500: {
            "description": "태그 그룹 전체 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "Internal Server Error"}}},
        },
    },
)
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
