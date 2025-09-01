import asyncio
from contextlib import asynccontextmanager
from typing import Set

import time
from fastapi import FastAPI, APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api import models, tags, auth, datasets
from app.api.storage import buckets_router, uploads_router
from app.api.tus import router as tus_router
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.logging import logger, LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.async_service_manager import service_manager
from app.services.redis_service import redis_service
from app.services.background_cache import background_cache_service


# Application lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting async services...")
    
    # Initialize storage service (required)
    await service_manager.initialize()
    
    # Initialize Redis service (optional - fail silently)
    try:
        await redis_service.initialize(fail_silently=True)
        if redis_service.is_available:
            logger.info("Redis service initialized successfully - Tus uploads enabled")
        else:
            logger.warning("Redis service not available - Tus uploads disabled")
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e} - Tus uploads disabled")
    
    # Start background cache service for tag preloading
    cache_refresh_interval = getattr(settings, 'CACHE_REFRESH_INTERVAL', 3600)  # 1 hour default
    await background_cache_service.start(refresh_interval_seconds=cache_refresh_interval)
    
    yield
    
    # Shutdown
    logger.info("Shutting down async services...")
    await service_manager.cleanup()
    
    # Stop background cache service
    await background_cache_service.stop()
    logger.info("Background cache service stopped")
    
    # Close Redis if it was initialized
    if redis_service.is_available:
        await redis_service.close()
        logger.info("Redis service closed")
    else:
        logger.info("Redis service was not active - no cleanup needed")

app = FastAPI(
    title="HUB Connect API",
    description="API for connecting 3rd party models to AI-PaaS",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
    lifespan=lifespan
)


# Request timeout middleware
class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout: int = 300, exclude_paths: Set[str] = None):
        super().__init__(app)
        self.timeout = timeout
        self.exclude_paths = exclude_paths or set()

    async def dispatch(self, request: Request, call_next):
        # Check if the request path should be excluded from timeout
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        try:
            # Apply timeout to request
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.error(f"Request timeout after {self.timeout}s: {request.url}")
            return JSONResponse(
                status_code=504,
                content={"detail": f"Request timeout after {self.timeout} seconds"}
            )
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )

app.add_middleware(
    RequestTimeoutMiddleware,
    timeout=300,
    exclude_paths={
        "/api/v1/buckets/{bucket_id}/objects", # Disable timeout for file uploads
        "/api/v1/models/{model_id:path}/download" # Disable timeout for model downloads
    }
)
app.add_middleware(RateLimitMiddleware, calls=200, period=60)  # Limit to 200 calls per minute
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    # Exclude 404 errors and Chrome DevTools related requests from error logs
    if exc.status_code == 404 and any(path in str(request.url) for path in [
        ".well-known/appspecific/com.chrome.devtools.json",
        "favicon.ico"
    ]):
        # Log only at debug level
        logger.debug(f"Resource not found: {request.url.path}")
    elif exc.status_code >= 500:
        # Log server errors only at ERROR level
        logger.error(f"HTTP error occurred: {exc.detail}")
    else:
        # Log client errors at INFO level
        logger.info(f"HTTP {exc.status_code}: {exc.detail}")
    
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# Live check (keep this outside the prefix_router)
@app.get("/")
async def root():
    logger.info("Live check endpoint accessed")
    return {"message": "Live check"}

# Enhanced health check endpoint
@app.get("/health")
async def health_check():
    """Comprehensive health check for all services."""
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {}
    }
    
    # Check Redis service
    redis_info = await redis_service.get_connection_info()
    health_status["services"]["redis"] = {
        "status": "available" if redis_service.is_available else "unavailable",
        "details": redis_info
    }
    
    # Check storage services
    try:
        storage_status = await service_manager.get_health_status()
        health_status["services"]["storage"] = {
            "status": "available",
            "details": storage_status
        }
    except Exception as e:
        health_status["services"]["storage"] = {
            "status": "unavailable",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # Check background cache service
    cache_status = background_cache_service.get_cache_status()
    health_status["services"]["background_cache"] = {
        "status": "running" if cache_status["is_running"] else "stopped",
        "details": cache_status
    }
    
    # Feature availability
    health_status["features"] = {
        "model_search": True,  # Always available (HuggingFace API)
        "tag_management": True,  # Always available
        "tag_preloading": cache_status["is_running"],  # Background cache preloading
        "file_storage": health_status["services"]["storage"]["status"] == "available",
        "resumable_uploads": redis_service.is_available,
        "large_file_support": redis_service.is_available
    }
    
    # Overall status determination
    if not health_status["features"]["model_search"]:
        health_status["status"] = "unhealthy"
    elif not redis_service.is_available or health_status["services"]["storage"]["status"] != "available":
        health_status["status"] = "degraded"
    
    return health_status


# Cache management endpoints
@app.get("/cache/status")
async def cache_status(current_user: dict = Depends(get_current_user)):
    """Get detailed cache service status."""
    return background_cache_service.get_cache_status()

@app.post("/cache/refresh")
async def cache_refresh(market: str = None, current_user: dict = Depends(get_current_user)):
    """Force cache refresh for specific market or all markets."""
    try:
        await background_cache_service.force_refresh(market)
        return {
            "message": f"Cache refresh completed for {'all markets' if not market else market}",
            "market": market
        }
    except Exception as e:
        logger.error(f"Cache refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache refresh failed: {str(e)}")


# Create a prefix router
prefix_router = APIRouter(prefix="/api/v1")

# Include other routers in the prefix_router
prefix_router.include_router(auth.router, prefix="/auth", tags=["auth"])
prefix_router.include_router(models.router, prefix="/models", tags=["models"])
prefix_router.include_router(tags.router, prefix="/tags", tags=["tags"])
prefix_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
prefix_router.include_router(buckets_router)  # /api/v1/buckets (enhanced with new features)
prefix_router.include_router(uploads_router)  # /api/v1/uploads (enhanced with cancel functionality)
prefix_router.include_router(tus_router, prefix="/tus", tags=["tus"])


# Add a new endpoint to show all routes under /api/v1
@prefix_router.get("/", summary="Get all API routes")
async def get_routes(request: Request, current_user: dict = Depends(get_current_user)):
    logger.info("Retrieving all API routes from cache")
    return {"routes": request.app.state.routes}


# Include the prefix_router in the main app
app.include_router(prefix_router)


# Legacy startup and shutdown events (kept for compatibility)
@app.on_event("startup")
async def startup_event():
    logger.info(f"Application is starting up. Log level: {settings.LOG_LEVEL}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application is shutting down")