import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException
from tuspyserver import create_tus_router

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.logging import logger
from app.services.async_service_manager import get_storage_service
from app.services.redis_service import get_redis_client, RedisService
from app.services.tus_service import get_tus_handler


# Create upload directory if it doesn't exist
def get_tus_upload_dir():
    """Get or create TUS upload directory."""
    upload_dir = getattr(settings, 'TUS_UPLOAD_DIR', tempfile.gettempdir())
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


async def tus_upload_complete_handler(file_id: str, upload_info: dict):
    """Handle completed TUS uploads by moving to S3."""
    try:
        # Get services
        storage_service = await get_storage_service()
        redis_service = get_redis_client()
        handler = get_tus_handler(storage_service, redis_service)
        
        # Handle the completed upload
        await handler.handle_upload_complete(file_id, upload_info)
        
    except Exception as e:
        logger.error(f"Error in TUS upload completion handler: {e}")
        raise


# Create a wrapper router that can conditionally include TUS router
router = APIRouter()

# Add a health check endpoint for Tus service
@router.get(
    "/health",
    summary="Tus 상태 조회",
    description=(
        "Tus resumable upload 기능과 Redis 연동 상태를 조회합니다.\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| tus_service | Tus 서비스 사용 가능 상태입니다. |\n"
        "| redis_status | Redis 연결 상태 상세 정보입니다. |\n"
        "| features | 재개 업로드, 대용량 업로드 지원 여부입니다. |\n"
        "| message | 현재 상태 설명 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "Tus 상태를 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "tus_service": "unavailable",
                        "redis_status": {
                            "connected": False,
                            "error": "Unable to retrieve Redis connection information",
                            "host": None,
                            "port": None,
                        },
                        "features": {
                            "resumable_uploads": False,
                            "large_file_support": False,
                        },
                        "message": "Tus service unavailable - Redis connection required",
                    }
                }
            },
        },
        503: {
            "description": "Tus 상태 정보를 일시적으로 조회할 수 없습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": "Service Unavailable",
                            "message": "Tus service health information is temporarily unavailable",
                            "code": "TUS_HEALTH_UNAVAILABLE",
                        }
                    }
                }
            },
        },
    },
)
async def tus_health(
    redis_service: RedisService = Depends(get_redis_client)
):
    """Check Tus service health status."""
    try:
        redis_info = await redis_service.get_connection_info()
    except Exception as e:
        logger.error(f"Failed to build Tus health response: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service Unavailable",
                "message": "Tus service health information is temporarily unavailable",
                "code": "TUS_HEALTH_UNAVAILABLE"
            }
        )
    
    return {
        "tus_service": "available" if redis_service.is_available else "unavailable",
        "redis_status": redis_info,
        "features": {
            "resumable_uploads": redis_service.is_available,
            "large_file_support": redis_service.is_available
        },
        "message": "Tus service is ready" if redis_service.is_available else "Tus service unavailable - Redis connection required"
    }

# Create the TUS router conditionally
if settings.REDIS_HOST and settings.REDIS_PORT:
    try:
        # Configure TUS router with file storage and S3 completion handler
        tus_config = {
            "prefix": "files",
            "files_dir": get_tus_upload_dir(),
            "max_size": getattr(settings, 'TUS_MAX_FILE_SIZE', 128849018880),  # ~120GB default
            "auth": get_current_user,
            "days_to_keep": getattr(settings, 'TUS_DAYS_TO_KEEP', 5),
            "on_upload_complete": tus_upload_complete_handler,
            "tags": ["tus", "uploads"]
        }
        
        # This router will handle the TUS protocol (POST, HEAD, PATCH, etc.)
        tus_router = create_tus_router(**tus_config)
        
        # The tuspyserver router already applies its own "files" prefix.
        router.include_router(tus_router)
        logger.info("Tus router created at /files. Ready to accept resumable uploads.")
        
    except Exception as e:
        logger.warning(f"Failed to create Tus router: {e}. Resumable uploads will be unavailable.")
        tus_configured = False
else:
    logger.info("Redis not configured - Tus resumable uploads disabled")
    tus_configured = False

# Add fallback endpoint when TUS is not configured
if not (settings.REDIS_HOST and settings.REDIS_PORT):
    @router.api_route(
        "/files/{path:path}",
        methods=["GET", "POST", "PATCH", "HEAD", "DELETE"],
        summary="Tus 업로드 비활성 응답",
        description=(
            "Redis가 설정되지 않은 환경에서 Tus 업로드 경로로 요청했을 때 반환되는 안내 응답입니다.\n\n"
            "### 입력 필드\n"
            "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | path | Y | Tus 업로드 대상 경로입니다. | upload-123 |\n\n"
            "### 응답 필드\n"
            "| 필드 | 설명 |\n"
            "| --- | --- |\n"
            "| detail.error | 오류 유형입니다. |\n"
            "| detail.message | 서비스 비활성 상태 설명입니다. |\n"
            "| detail.code | 오류 코드입니다. |\n"
            "| detail.suggestion | 활성화 방법 안내입니다. |"
        ),
        responses={
            503: {
                "description": "Tus 업로드 서비스가 설정되지 않았습니다.",
                "content": {
                    "application/json": {
                        "example": {
                            "detail": {
                                "error": "Service Unavailable",
                                "message": "Resumable upload service is not configured",
                                "code": "TUS_SERVICE_NOT_CONFIGURED",
                                "suggestion": "Configure REDIS_HOST and REDIS_PORT in environment variables to enable TUS uploads",
                            }
                        }
                    }
                },
            },
        },
    )
    async def tus_unavailable():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service Unavailable",
                "message": "Resumable upload service is not configured",
                "code": "TUS_SERVICE_NOT_CONFIGURED",
                "suggestion": "Configure REDIS_HOST and REDIS_PORT in environment variables to enable TUS uploads"
            }
        )
