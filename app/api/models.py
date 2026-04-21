from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Query, Depends

from app.core.auth import get_current_user
from app.core.logging import logger
from app.services.markets.async_common import get_async_market_service

router = APIRouter(tags=["models"])

@router.get(
    "/",
    summary="모델 목록 조회",
    description=(
        "마켓별 모델 목록을 조회하거나 검색합니다.\n\n"
        "정렬값이 `trending`이면 트렌딩 조회 로직을 사용하고, 그 외에는 일반 검색 로직을 사용합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n"
        "| query | query | N | 검색어입니다. | llama |\n"
        "| sort | query | N | 정렬 기준입니다. | downloads |\n"
        "| page | query | N | 페이지 번호입니다. 1부터 시작합니다. | 1 |\n"
        "| limit | query | N | 페이지당 최대 조회 개수입니다. | 30 |\n"
        "| num_parameters_min | query | N | 최소 파라미터 범위입니다. | 7B |\n"
        "| num_parameters_max | query | N | 최대 파라미터 범위입니다. | 70B |\n"
        "| include_parameters | query | N | 파라미터 수 포함 여부입니다. | true |\n"
        "| pipeline_tag | query | N | 단일 파이프라인 태그 필터입니다. | text-generation |\n"
        "| library | query | N | 다중 라이브러리 필터입니다. | transformers |\n"
        "| language | query | N | 다중 언어 필터입니다. | en |\n"
        "| license | query | N | 단일 라이선스 필터입니다. | apache-2.0 |\n"
        "| apps | query | N | 다중 앱 필터입니다. | llama.cpp |\n"
        "| inference_provider | query | N | 다중 추론 제공자 필터입니다. | nebius |\n"
        "| other | query | N | 기타 다중 필터입니다. | 4-bit |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| models | 모델 목록입니다. |\n"
        "| total | 전체 모델 수입니다. |\n"
        "| applied_filters | 실제 적용된 필터 정보입니다. 일부 마켓에서만 포함될 수 있습니다. |\n\n"
        "models 내부 공통 필드:\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| id | 모델 식별자입니다. |\n"
        "| downloads | 다운로드 수입니다. |\n"
        "| likes | 좋아요 수입니다. |\n"
        "| lastModified | 마지막 수정 시각입니다. |\n"
        "| pipeline_tag | 대표 태스크 태그입니다. |\n"
        "| tags | 태그 목록입니다. |\n"
        "| parameterDisplay | 사람이 읽기 쉬운 파라미터 표기입니다. |\n"
        "| parameterRange | 파라미터 범주 정보입니다. |"
    ),
    responses={
        200: {
            "description": "모델 목록을 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "models": [
                            {
                                "id": "meta-llama/Llama-3-8B",
                                "downloads": 120345,
                                "likes": 5321,
                                "lastModified": "2026-04-10T12:00:00Z",
                                "pipeline_tag": "text-generation",
                                "tags": ["transformers", "text-generation", "en"],
                                "parameterDisplay": "8B",
                                "parameterRange": "7B-10B",
                            }
                        ],
                        "total": 1234,
                        "applied_filters": {
                            "pipeline_tag": "text-generation",
                            "language": ["en"],
                        },
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "모델 목록 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "Internal server error"}}},
        },
    },
)
async def api_models(
    market: str = Query(..., description="Market name (e.g., huggingface, aihub)"),
    query: str = "",
    sort: str = "downloads",
    page: int = Query(1, ge=1),
    limit: int = 30,
    num_parameters_min: Optional[str] = Query(None, description="Minimum parameters (e.g., '3B', '7B', '24B')"),
    num_parameters_max: Optional[str] = Query(None, description="Maximum parameters (e.g., '128B', '256B')"),
    include_parameters: bool = Query(True, description="Include parameter count in response"),
    pipeline_tag: Optional[str] = Query(None, description="Filter by pipeline tag/task (single selection)"),
    library: Optional[List[str]] = Query(None, description="Filter by library (multiple allowed, e.g., transformers, peft)"),
    language: Optional[List[str]] = Query(None, description="Filter by language (multiple allowed, e.g., en, ru, multilingual)"),
    license: Optional[str] = Query(None, description="Filter by license (single selection, e.g., license:apache-2.0)"),
    apps: Optional[List[str]] = Query(None, description="Filter by apps (multiple allowed, e.g., llama.cpp, lmstudio)"),
    inference_provider: Optional[List[str]] = Query(None, description="Filter by inference provider (multiple allowed, e.g., novita, nebius)"),
    other: Optional[List[str]] = Query(None, description="Other filters (multiple allowed, e.g., endpoints_compatible, 4-bit)"),
    current_user: dict = Depends(get_current_user)
):
    try:
        market_service = await get_async_market_service(market)
        if sort == "trending":
            data = await market_service.get_trending_models(
                page,
                query,
                num_parameters_min,
                num_parameters_max,
                pipeline_tag,
                library,
                language,
                license,
                apps,
                inference_provider,
                other
            )
        else:
            data = await market_service.search_models(
                query,
                sort,
                page,
                limit,
                num_parameters_min,
                num_parameters_max,
                pipeline_tag,
                library,
                language,
                license,
                apps,
                inference_provider,
                other
            )

        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in api_models: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/{model_id:path}/files",
    summary="모델 파일 목록 조회",
    description=(
        "특정 모델 저장소의 파일 목록을 조회합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| model_id | path | Y | 모델 저장소 ID입니다. | meta-llama/Llama-3-8B |\n"
        "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| files | 모델 파일 목록입니다. |\n\n"
        "files 내부 항목:\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| name | 파일명 또는 저장소 내 경로입니다. |\n"
        "| size | 사람이 읽기 쉬운 파일 크기입니다. |\n"
        "| blob_id | 파일 blob 식별자입니다. |"
    ),
    responses={
        200: {
            "description": "모델 파일 목록을 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "files": [
                            {
                                "name": "config.json",
                                "size": "2.1 KB",
                                "blob_id": "abc123",
                            }
                        ]
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "모델 파일 목록 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "Failed to fetch model files"}}},
        },
    },
)
async def api_model_files(model_id: str, market: str = Query(..., description="Market name"), current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_model_files(model_id)
    except Exception as e:
        logger.error(f"Error in api_model_files: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch model files")

@router.get(
    "/{model_id:path}/download",
    summary="모델 파일 다운로드",
    description=(
        "특정 모델 파일을 다운로드합니다.\n\n"
        "`download_dir`를 지정하면 서버가 해당 경로로 파일을 복사하고 JSON 정보를 반환합니다.\n"
        "`download_dir`를 지정하지 않으면 파일 응답으로 바로 다운로드합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| model_id | path | Y | 모델 저장소 ID입니다. | meta-llama/Llama-3-8B |\n"
        "| filename | query | Y | 다운로드할 파일명입니다. | config.json |\n"
        "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n"
        "| download_dir | query | N | 서버 내 사용자 지정 다운로드 경로입니다. | C:/downloads/models |\n\n"
        "### 응답 필드\n"
        "| 항목 | 설명 |\n"
        "| --- | --- |\n"
        "| 파일 응답 | `download_dir` 미지정 시 파일 다운로드 응답입니다. |\n"
        "| download_type | `download_dir` 지정 시 다운로드 방식입니다. |\n"
        "| file_path | 저장된 서버 경로입니다. |\n"
        "| file_size | 저장된 파일 크기(byte)입니다. |\n"
        "| filename | 다운로드한 파일명입니다. |\n"
        "| model_id | 대상 모델 ID입니다. |"
    ),
    responses={
        200: {
            "description": "모델 파일 다운로드를 처리했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "download_type": "custom_path",
                        "file_path": "C:/downloads/models/config.json",
                        "file_size": 2145,
                        "filename": "config.json",
                        "model_id": "meta-llama/Llama-3-8B",
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "모델 파일 다운로드에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "Failed to download model file"}}},
        },
    },
)
async def download_model(model_id: str, filename: str, market: str = Query(..., description="Market name"), download_dir: Optional[str] = Query(None, description="Custom download directory path"), current_user: dict = Depends(get_current_user)):
    try:
        market_service = await get_async_market_service(market)
        return await market_service.download_model_file(model_id, filename, download_dir)
    except Exception as e:
        logger.error(f"Error in download_model: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download model file")

@router.get(
    "/{model_id:path}",
    summary="모델 상세 조회",
    description=(
        "특정 모델의 상세 정보를 조회합니다.\n\n"
        "마켓 서비스에서 받은 모델 정보와 모델 카드 정보를 합쳐 반환합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| model_id | path | Y | 모델 저장소 ID입니다. | meta-llama/Llama-3-8B |\n"
        "| market | query | Y | 대상 마켓 이름입니다. | huggingface |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| id | 모델 식별자입니다. |\n"
        "| downloads | 다운로드 수입니다. |\n"
        "| likes | 좋아요 수입니다. |\n"
        "| lastModified | 마지막 수정 시각입니다. |\n"
        "| pipeline_tag | 대표 태스크 태그입니다. |\n"
        "| tags | 태그 목록입니다. |\n"
        "| card_html | 모델 카드 내용을 HTML로 변환한 값입니다. |\n"
        "| 그 외 필드 | 마켓 카드 메타데이터가 추가로 포함될 수 있습니다. |"
    ),
    responses={
        200: {
            "description": "모델 상세 정보를 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "id": "meta-llama/Llama-3-8B",
                        "downloads": 120345,
                        "likes": 5321,
                        "lastModified": "2026-04-10T12:00:00Z",
                        "pipeline_tag": "text-generation",
                        "tags": ["transformers", "text-generation", "en"],
                        "card_html": "<p>Model card content...</p>",
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        404: {
            "description": "요청한 모델을 찾을 수 없습니다.",
            "content": {"application/json": {"example": {"detail": "Model not found"}}},
        },
    },
)
async def api_model_detail(model_id: str, market: str = Query(..., description="Market name"), current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        market_service = await get_async_market_service(market)
        return await market_service.get_model_detail(model_id)
    except Exception as e:
        logger.error(f"Error in api_model_detail: {str(e)}")
        raise HTTPException(status_code=404, detail="Model not found")
