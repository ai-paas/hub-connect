from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from starlette.responses import Response
import gzip

from app.core.logging import logger
from app.services.markets.common import get_market_service

router = APIRouter(tags=["models"])

@router.get("/")
async def api_models(market: str, query: str = "", sort: str = "downloads", page: int = Query(1, ge=1), limit: int = 30):
    try:
        market_service = get_market_service(market)
        if sort == "trending":
            data = await market_service.get_trending_models(page, query)
        else:
            data = await market_service.search_models(query, sort, page, limit)

        json_compatible_data = JSONResponse(content=data).body
        gzip_body = gzip.compress(json_compatible_data)

        return Response(
            content=gzip_body,
            media_type="application/json",
            headers={"Content-Encoding": "gzip"}
        )
    except Exception as e:
        logger.error(f"Error in api_models: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{model_id:path}/files")
async def api_model_files(market: str, model_id: str) -> Dict[str, Any]:
    try:
        market_service = get_market_service(market)
        return await market_service.get_model_files(model_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to fetch model files: {str(e)}")

@router.get("/{model_id:path}/download")
async def download_model(market: str, model_id: str, filename: str) -> FileResponse:
    try:
        market_service = get_market_service(market)
        return await market_service.download_model_file(model_id, filename)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to download model file: {str(e)}")

@router.get("/{model_id:path}")
async def api_model_detail(market: str, model_id: str) -> Dict[str, Any]:
    try:
        market_service = get_market_service(market)
        return await market_service.get_model_detail(model_id)
    except Exception as e:
        logger.error(f"Error in api_model_detail: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Model not found or error occurred: {str(e)}")
