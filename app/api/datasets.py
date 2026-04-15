from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional, List
from enum import Enum

from app.core.auth import get_current_user
from app.core.logging import logger
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
            summary="데이터셋 목록 조회",
            description=(
                "데이터셋 목록을 조회합니다.\n\n"
                "### 입력 필드\n"
                "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n"
                "| sort | query | N | 정렬 기준입니다. | likes |\n"
                "| page | query | N | 페이지 번호입니다. | 1 |\n"
                "| limit | query | N | 페이지당 조회 개수입니다. | 10 |\n\n"
                "### 응답 필드\n"
                "| 필드 | 설명 |\n"
                "| --- | --- |\n"
                "| datasets | 데이터셋 목록입니다. |\n"
                "| total | 전체 데이터셋 수입니다. |\n"
                "| page | 현재 페이지 번호입니다. |\n"
                "| page_size | 페이지당 반환 개수입니다. |\n\n"
                "datasets 내부 공통 필드:\n"
                "| 필드 | 설명 |\n"
                "| --- | --- |\n"
                "| id | 데이터셋 식별자입니다. |\n"
                "| author | 작성자입니다. |\n"
                "| downloads | 다운로드 수입니다. |\n"
                "| likes | 좋아요 수입니다. |\n"
                "| lastModified | 마지막 수정 시각입니다. |\n"
                "| gated | 접근 제한 여부입니다. |\n"
                "| private | 비공개 여부입니다. |\n"
                "| repoType | 저장소 타입입니다. |"
            ),
            responses={
                200: {
                    "description": "데이터셋 목록을 정상 조회했습니다.",
                    "content": {
                        "application/json": {
                            "example": {
                                "datasets": [
                                    {
                                        "id": "google/fleurs",
                                        "author": "google",
                                        "downloads": 1200,
                                        "gated": False,
                                        "lastModified": "2026-04-10T12:00:00Z",
                                        "likes": 230,
                                        "private": False,
                                        "repoType": "dataset",
                                    }
                                ],
                                "total": 120,
                                "page": 1,
                                "page_size": 10,
                            }
                        }
                    },
                },
                401: {
                    "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
                    "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
                },
                500: {
                    "description": "데이터셋 목록 조회에 실패했습니다.",
                    "content": {"application/json": {"example": {"detail": "Error searching datasets"}}},
                },
            })
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
        logger.error(f"Error searching datasets: {str(e)}")
        raise HTTPException(status_code=500, detail="Error searching datasets")


@router.get("/{repo_id:path}/info",
            response_model=DatasetInfoResponse,
            summary="데이터셋 상세 조회",
            description=(
                "데이터셋 저장소의 상세 정보를 조회합니다.\n\n"
                "### 입력 필드\n"
                "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| repo_id | path | Y | 데이터셋 저장소 ID입니다. | google/fleurs |\n"
                "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n\n"
                "### 응답 필드\n"
                "| 필드 | 설명 |\n"
                "| --- | --- |\n"
                "| dataset_info | 설정별 데이터셋 상세 정보입니다. |\n"
                "| pending | 아직 준비 중인 항목 목록입니다. |\n"
                "| failed | 조회 실패 항목 목록입니다. |\n"
                "| partial | 일부만 조회되었는지 여부입니다. |\n"
                "| cardData | README 카드 메타데이터입니다. |"
            ),
            responses={
                200: {
                    "description": "데이터셋 상세 정보를 정상 조회했습니다.",
                    "content": {
                        "application/json": {
                            "example": {
                                "dataset_info": {
                                    "default": {
                                        "description": "Multilingual speech dataset",
                                        "license": "cc-by-4.0",
                                        "dataset_name": "fleurs",
                                        "config_name": "default",
                                        "download_size": 123456,
                                        "dataset_size": 654321,
                                        "size_in_bytes": 777777,
                                    }
                                },
                                "pending": [],
                                "failed": [],
                                "partial": False,
                                "cardData": {"language": ["en", "ko"]},
                            }
                        }
                    },
                },
                401: {
                    "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
                    "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
                },
                404: {
                    "description": "요청한 데이터셋을 찾을 수 없습니다.",
                    "content": {"application/json": {"example": {"detail": "Dataset not found"}}},
                },
            })
async def get_dataset_info(
        repo_id: str = Path(..., description="The ID of the dataset repository"),
        market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
        current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_dataset_info(repo_id=repo_id)
    except Exception as e:
        logger.error(f"Error getting dataset info: {str(e)}")
        raise HTTPException(status_code=404, detail="Dataset not found")


@router.get("/{repo_id:path}/files",
            response_model=DatasetFileTreeResponse,
            summary="데이터셋 파일 목록 조회",
            description=(
                "데이터셋 저장소의 파일 트리를 조회합니다.\n\n"
                "### 입력 필드\n"
                "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| repo_id | path | Y | 데이터셋 저장소 ID입니다. | google/fleurs |\n"
                "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n\n"
                "### 응답 필드\n"
                "| 필드 | 설명 |\n"
                "| --- | --- |\n"
                "| root | 파일 목록입니다. |\n\n"
                "root 내부 항목:\n"
                "| 필드 | 설명 |\n"
                "| --- | --- |\n"
                "| path | 파일 경로입니다. |\n"
                "| type | 항목 타입입니다. |\n"
                "| size | 파일 크기(byte)입니다. |\n"
                "| blob_id | blob 식별자입니다. |\n"
                "| lfs | LFS 메타데이터입니다. |"
            ),
            responses={
                200: {
                    "description": "데이터셋 파일 목록을 정상 조회했습니다.",
                    "content": {
                        "application/json": {
                            "example": [
                                {
                                    "path": "README.md",
                                    "type": "file",
                                    "size": 0,
                                    "blob_id": None,
                                    "lfs": None,
                                }
                            ]
                        }
                    },
                },
                401: {
                    "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
                    "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
                },
                500: {
                    "description": "데이터셋 파일 목록 조회에 실패했습니다.",
                    "content": {"application/json": {"example": {"detail": "Failed to fetch dataset files"}}},
                },
            })
async def get_dataset_files(
        repo_id: str = Path(..., description="The ID of the dataset repository"),
        market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
        current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_dataset_files(repo_id=repo_id)
    except Exception as e:
        logger.error(f"Error getting dataset files: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch dataset files")


@router.get("/{repo_id:path}/download/{filename:path}",
            summary="데이터셋 파일 다운로드",
            description=(
                "데이터셋 저장소에서 단일 파일을 다운로드합니다.\n\n"
                "`download_dir`를 지정하면 서버에 파일을 저장하고 JSON 정보를 반환합니다.\n"
                "지정하지 않으면 파일 다운로드 응답을 반환합니다.\n\n"
                "### 입력 필드\n"
                "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| repo_id | path | Y | 데이터셋 저장소 ID입니다. | google/fleurs |\n"
                "| filename | path | Y | 다운로드할 파일 경로입니다. | README.md |\n"
                "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n"
                "| revision | query | N | 다운로드할 리비전입니다. | main |\n"
                "| download_dir | query | N | 서버 내 저장 경로입니다. | C:/downloads/datasets |\n\n"
                "### 응답 필드\n"
                "| 항목 | 설명 |\n"
                "| --- | --- |\n"
                "| 파일 응답 | `download_dir` 미지정 시 파일 다운로드 응답입니다. |\n"
                "| download_type | `download_dir` 지정 시 다운로드 방식입니다. |\n"
                "| file_path | 저장된 서버 경로입니다. |\n"
                "| file_size | 저장된 파일 크기(byte)입니다. |\n"
                "| filename | 다운로드한 파일명입니다. |\n"
                "| repo_id | 대상 데이터셋 ID입니다. |"
            ),
            responses={
                200: {
                    "description": "데이터셋 파일 다운로드를 처리했습니다.",
                    "content": {
                        "application/json": {
                            "example": {
                                "download_type": "custom_path",
                                "file_path": "C:/downloads/datasets/README.md",
                                "file_size": 1024,
                                "filename": "README.md",
                                "repo_id": "google/fleurs",
                            }
                        }
                    },
                },
                401: {
                    "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
                    "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
                },
                500: {
                    "description": "데이터셋 파일 다운로드에 실패했습니다.",
                    "content": {"application/json": {"example": {"detail": "Failed to download dataset file"}}},
                },
            })
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
        logger.error(f"Error downloading dataset file: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download dataset file")


@router.get("/{repo_id:path}/download",
            summary="데이터셋 스냅샷 다운로드",
            description=(
                "데이터셋 저장소 전체를 스냅샷 형태로 다운로드합니다.\n\n"
                "### 입력 필드\n"
                "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| repo_id | path | Y | 데이터셋 저장소 ID입니다. | google/fleurs |\n"
                "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n"
                "| revision | query | N | 다운로드할 리비전입니다. | main |\n"
                "| allow_patterns | query | N | 포함할 파일 패턴 목록입니다. | data/* |\n"
                "| ignore_patterns | query | N | 제외할 파일 패턴 목록입니다. | *.tmp |\n"
                "| download_dir | query | N | 서버 내 저장 경로입니다. | C:/downloads/datasets |\n\n"
                "### 응답 필드\n"
                "| 필드 | 설명 |\n"
                "| --- | --- |\n"
                "| download_type | 다운로드 방식입니다. |\n"
                "| snapshot_path | 저장된 스냅샷 경로입니다. |\n"
                "| repo_id | 대상 데이터셋 ID입니다. |\n"
                "| total_files | 사용자 지정 경로 다운로드 시 저장된 파일 수입니다. |\n"
                "| message | 캐시 다운로드 시 안내 메시지입니다. |"
            ),
            responses={
                200: {
                    "description": "데이터셋 스냅샷 다운로드를 처리했습니다.",
                    "content": {
                        "application/json": {
                            "example": {
                                "download_type": "cached_snapshot",
                                "snapshot_path": "C:/Users/user/.cache/huggingface/datasets/...",
                                "repo_id": "google/fleurs",
                                "message": "Files downloaded to HuggingFace cache. Access via snapshot_path.",
                            }
                        }
                    },
                },
                401: {
                    "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
                    "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
                },
                500: {
                    "description": "데이터셋 스냅샷 다운로드에 실패했습니다.",
                    "content": {"application/json": {"example": {"detail": "Failed to download dataset snapshot"}}},
                },
            })
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
        logger.error(f"Error downloading dataset snapshot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download dataset snapshot")
