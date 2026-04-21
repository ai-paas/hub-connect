import asyncio
import re
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query
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
from app.services.background_cache import background_cache_service
from app.services.redis_service import redis_service


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
    def __init__(self, app, timeout: int = 300, exclude_patterns: List[re.Pattern] = None):
        super().__init__(app)
        self.timeout = timeout
        self.exclude_patterns = exclude_patterns or []

    def _is_excluded(self, path: str) -> bool:
        return any(p.match(path) for p in self.exclude_patterns)

    async def dispatch(self, request: Request, call_next):
        # Check if the request path should be excluded from timeout
        if self._is_excluded(request.url.path):
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
    exclude_patterns=[
        re.compile(r"^/api/v1/buckets/[^/]+/objects$"),     # File uploads (POST)
        re.compile(r"^/api/v1/buckets/[^/]+/objects/.+"),   # File downloads (GET with key path)
        re.compile(r"^/api/v1/models/.+/download"),          # Model downloads
        re.compile(r"^/api/v1/datasets/.+/download"),        # Dataset downloads
        re.compile(r"^/api/v1/tus/"),                        # TUS resumable uploads
    ]
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
@app.get(
    "/",
    summary="라이브 체크",
    description=(
        "서버가 기동 중인지 확인하는 간단한 라이브 체크 엔드포인트입니다.\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| message | 고정 응답 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "서버가 정상 응답 중입니다.",
            "content": {
                "application/json": {
                    "example": {"message": "Live check"}
                }
            },
        },
    },
)
async def root():
    logger.info("Live check endpoint accessed")
    return {"message": "Live check"}

# Enhanced health check endpoint
@app.get(
    "/health",
    summary="서비스 상태 조회",
    description=(
        "애플리케이션과 주요 하위 서비스 상태를 종합 조회합니다.\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| status | 전체 서비스 상태입니다. `healthy`, `degraded`, `unhealthy` 중 하나입니다. |\n"
        "| timestamp | 상태 점검 시각의 Unix timestamp입니다. |\n"
        "| services | Redis, storage, background cache 상태 상세입니다. |\n"
        "| features | 기능별 사용 가능 여부입니다. |\n"
        "| features.model_search | 모델 검색 기능 사용 가능 여부입니다. |\n"
        "| features.tag_management | 태그 관리 기능 사용 가능 여부입니다. |\n"
        "| features.tag_preloading | 백그라운드 캐시 태그 프리로딩 사용 가능 여부입니다. |\n"
        "| features.file_storage | 파일 스토리지 기능 사용 가능 여부입니다. |\n"
        "| features.resumable_uploads | Tus 재개 업로드 사용 가능 여부입니다. Redis 연동 필요입니다. |\n"
        "| features.large_file_support | 대용량 파일 업로드 지원 여부입니다. Redis 연동 필요입니다. |"
    ),
    responses={
        200: {
            "description": "서비스 상태를 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "degraded",
                        "timestamp": 1776237164.551043,
                        "services": {
                            "redis": {
                                "status": "unavailable",
                                "details": {
                                    "connected": False,
                                    "error": "Unable to retrieve Redis connection information",
                                },
                            },
                            "storage": {
                                "status": "available",
                                "details": {
                                    "initialized": True,
                                    "services": {
                                        "storage": {"status": "healthy", "bucket_count": 3}
                                    },
                                },
                            },
                            "background_cache": {
                                "status": "running",
                                "details": {
                                    "is_running": True,
                                    "refresh_interval": 3600,
                                },
                            },
                        },
                        "features": {
                            "model_search": True,
                            "tag_management": True,
                            "tag_preloading": True,
                            "file_storage": True,
                            "resumable_uploads": False,
                            "large_file_support": False,
                        },
                    }
                }
            },
        },
    },
)
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
@app.get(
    "/cache/status",
    summary="캐시 상태 조회",
    description=(
        "백그라운드 캐시 서비스 상태를 조회합니다.\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| is_running | 백그라운드 캐시 서비스 실행 여부입니다. |\n"
        "| refresh_interval | 자동 새로고침 주기(초)입니다. |\n"
        "| supported_markets | 캐시 워밍업 대상 마켓 목록입니다. |\n"
        "| last_refresh | 마켓별 마지막 새로고침 시각입니다. |\n"
        "| next_refresh | 다음 새로고침 예정 시각입니다. |"
    ),
    responses={
        200: {
            "description": "캐시 상태를 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "is_running": True,
                        "refresh_interval": 3600,
                        "supported_markets": ["huggingface", "aihub"],
                        "last_refresh": {
                            "huggingface": "2026-04-15T16:09:53.144110"
                        },
                        "next_refresh": "2026-04-15T17:12:44.663748",
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
    },
)
async def cache_status(current_user: dict = Depends(get_current_user)):
    """Get detailed cache service status."""
    return background_cache_service.get_cache_status()

@app.post(
    "/cache/refresh",
    summary="캐시 강제 새로고침",
    description=(
        "특정 마켓 또는 전체 마켓의 캐시를 즉시 새로고침합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| market | query | N | 특정 마켓만 새로고침할 때 사용하는 값입니다. 비우면 전체 마켓을 대상으로 합니다. | huggingface |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| message | 새로고침 결과 메시지입니다. |\n"
        "| market | 요청한 마켓 이름입니다. 전체 새로고침이면 `null`입니다. |"
    ),
    responses={
        200: {
            "description": "캐시 새로고침이 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Cache refresh completed for huggingface",
                        "market": "huggingface",
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "캐시 새로고침에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "Cache refresh failed"}}},
        },
    },
)
async def cache_refresh(
    market: str | None = Query(None, description="새로고침할 마켓 이름", examples=["huggingface"]),
    current_user: dict = Depends(get_current_user)
):
    """Force cache refresh for specific market or all markets."""
    try:
        await background_cache_service.force_refresh(market)
        return {
            "message": f"Cache refresh completed for {'all markets' if not market else market}",
            "market": market
        }
    except Exception as e:
        logger.error(f"Cache refresh failed: {e}")
        raise HTTPException(status_code=500, detail="Cache refresh failed")


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
@prefix_router.get(
    "/",
    summary="API 라우트 목록 조회",
    description=(
        "현재 등록된 `/api/v1` 라우트 목록을 조회합니다.\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| routes | 등록된 라우트 정보 목록입니다. |"
    ),
    responses={
        200: {
            "description": "라우트 목록을 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "routes": [
                            {"path": "/api/v1/auth/login", "name": "login_for_access_token"}
                        ]
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
    },
)
async def get_routes(request: Request, current_user: dict = Depends(get_current_user)):
    logger.info("Retrieving all API routes from cache")
    return {"routes": request.app.state.routes}


# Include the prefix_router in the main app
app.include_router(prefix_router)
