from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional, List
from enum import Enum

from app.core.auth import get_current_user
from app.services.markets.async_common import get_async_market_service
from app.schemas.dataset import (
    DatasetSearchResponse,
    DatasetInfoResponse,
    DatasetFileTreeResponse,
)

router = APIRouter()


class DatasetSort(str, Enum):
    likes = "likes"
    trending = "trending"
    downloads = "downloads"
    created = "created"
    modified = "modified"
    most_rows = "most_rows"
    least_rows = "least_rows"


@router.get("/",
            response_model=DatasetSearchResponse,
            summary="Search for datasets",
            description="Search for datasets with various sorting and filtering options.")
async def search_datasets(
        market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
        sort: DatasetSort = Query(DatasetSort.likes, description="Sort order for datasets"),
        page: int = Query(1, description="Page number for pagination"),
        limit: int = Query(10, description="Number of results per page"),
        current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.search_datasets(sort=sort.value, page=page, page_size=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching datasets: {str(e)}")


@router.get("/{repo_id:path}/info",
            response_model=DatasetInfoResponse,
            summary="Get dataset repository information",
            description="Get detailed information about a dataset repository.")
async def get_dataset_info(
        repo_id: str = Path(..., description="The ID of the dataset repository"),
        market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
        current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_dataset_info(repo_id=repo_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Dataset not found or error occurred: {str(e)}")


@router.get("/{repo_id:path}/files",
            response_model=DatasetFileTreeResponse,
            summary="Get dataset repository file tree",
            description="Get the file tree of a dataset repository.")
async def get_dataset_files(
        repo_id: str = Path(..., description="The ID of the dataset repository"),
        market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
        current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_dataset_files(repo_id=repo_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to fetch dataset files: {str(e)}")


@router.get("/{repo_id:path}/download/{filename:path}",
            summary="Download a file from a dataset repository",
            description="Download a single file from a dataset repository.")
async def download_dataset_file(
        repo_id: str = Path(..., description="The ID of the dataset repository"),
        filename: str = Path(..., description="The name of the file to download"),
        market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
        revision: Optional[str] = Query(None, description="The revision of the file to download"),
        download_dir: Optional[str] = Query(None, description="Custom download directory path"),
        current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.download_file(repo_id=repo_id, filename=filename, revision=revision, download_dir=download_dir)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to download dataset file: {str(e)}")


@router.get("/{repo_id:path}/download",
            summary="Download all files from a dataset repository",
            description="Download all files from a dataset repository as a snapshot.")
async def download_dataset_snapshot(
        repo_id: str = Path(..., description="The ID of the dataset repository"),
        market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
        revision: Optional[str] = Query(None, description="The revision of the repository to download"),
        allow_patterns: Optional[List[str]] = Query(None, description="Patterns to allow for snapshot download"),
        ignore_patterns: Optional[List[str]] = Query(None, description="Patterns to ignore for snapshot download"),
        download_dir: Optional[str] = Query(None, description="Custom download directory path"),
        current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.download_snapshot(
            repo_id=repo_id,
            revision=revision,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
            download_dir=download_dir
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to download dataset snapshot: {str(e)}")
