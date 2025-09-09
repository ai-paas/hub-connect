from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse, FileResponse
from starlette.responses import Response


from app.core.logging import logger
from app.services.markets.async_common import get_async_market_service
from app.core.auth import get_current_user

router = APIRouter(tags=["models"])

@router.get("/")
async def api_models(
    market: str = Query(..., description="Market name (e.g., huggingface, aihub)"), 
    query: str = "", 
    sort: str = "downloads", 
    page: int = Query(1, ge=1), 
    limit: int = 30,
    num_parameters_min: Optional[str] = Query(None, description="Minimum parameters (e.g., '3B', '7B', '24B')"),
    num_parameters_max: Optional[str] = Query(None, description="Maximum parameters (e.g., '128B', '256B')"),
    include_parameters: bool = Query(True, description="Include parameter count in response"),
    current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        if sort == "trending":
            data = await market_service.get_trending_models(
                page, 
                query, 
                num_parameters_min, 
                num_parameters_max
            )
        else:
            data = await market_service.search_models(
                query, 
                sort, 
                page, 
                limit,
                num_parameters_min,
                num_parameters_max
            )

        return data
    except Exception as e:
        logger.error(f"Error in api_models: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{model_id:path}/files")
async def api_model_files(model_id: str, market: str = Query(..., description="Market name"), current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_model_files(model_id)
    except Exception as e:
        logger.error(f"Error in api_model_files: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch model files")

@router.get("/{model_id:path}/download")
async def download_model(model_id: str, filename: str, market: str = Query(..., description="Market name"), download_dir: Optional[str] = Query(None, description="Custom download directory path"), current_user: dict = Depends(get_current_user)):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.download_model_file(model_id, filename, download_dir)
    except Exception as e:
        logger.error(f"Error in download_model: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download model file")

@router.get("/{model_id:path}")
async def api_model_detail(model_id: str, market: str = Query(..., description="Market name"), current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_model_detail(model_id)
    except Exception as e:
        logger.error(f"Error in api_model_detail: {str(e)}")
        raise HTTPException(status_code=404, detail="Model not found")
