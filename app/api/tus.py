from fastapi import APIRouter, Depends, HTTPException
from tuspyserver import create_tus_router
from app.services.tus_service import S3TusRepo
from app.services.async_service_manager import get_storage_service
from app.services.redis_service import get_redis_client, RedisService
from app.services.async_storage_service import AsyncStorageService
from app.core.logging import logger

# Dependency provider for the S3TusRepo
# This function will be called by tuspyserver for each request.
async def get_s3_tus_repo(
    storage_service: AsyncStorageService = Depends(get_storage_service),
    redis_service: RedisService = Depends(get_redis_client)
) -> S3TusRepo:
    """Provides a configured S3TusRepo instance with necessary dependencies."""
    # Check if Redis is available before allowing Tus operations
    if not redis_service.is_available:
        logger.warning("Tus upload request rejected - Redis service not available")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service Unavailable",
                "message": "Resumable upload service is temporarily unavailable due to Redis connection issues",
                "code": "TUS_REDIS_UNAVAILABLE",
                "retry_after": 60  # Suggest retry after 60 seconds
            }
        )
    
    logger.debug("Creating S3TusRepo instance for a Tus request.")
    return S3TusRepo(storage_service, redis_service)

# Create a wrapper router that can conditionally include TUS router
router = APIRouter()

# Add a health check endpoint for Tus service
@router.get("/health")
async def tus_health(
    redis_service: RedisService = Depends(get_redis_client)
):
    """Check Tus service health status."""
    redis_info = await redis_service.get_connection_info()
    
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
try:
    # This router will handle the TUS protocol (POST, HEAD, PATCH, etc.)
    tus_router = create_tus_router(
        repo_provider=get_s3_tus_repo,
        # The location header will be built using the request URL.
        # For example, if the client is at https://example.com and the router is at /tus,
        # the location will be https://example.com/tus/{file_id}
    )
    
    # Include the tus_router
    router.include_router(tus_router, prefix="/files")
    logger.info("Tus router created at /files. Ready to accept resumable uploads.")
    
except Exception as e:
    logger.warning(f"Failed to create Tus router: {e}. Resumable uploads will be unavailable.")
    
    # Add fallback endpoint that explains the service is unavailable
    @router.api_route("/files/{path:path}", methods=["GET", "POST", "PATCH", "HEAD", "DELETE"])
    async def tus_unavailable():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service Unavailable",
                "message": "Resumable upload service is not available",
                "code": "TUS_SERVICE_DISABLED",
                "suggestion": "Please check Redis service configuration"
            }
        )