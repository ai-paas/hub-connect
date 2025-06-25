from fastapi import FastAPI, APIRouter, Depends
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import asyncio
import time
from app.core.config import settings
from app.api import models, tags, storage, auth
from app.core.logging import logger, LoggingMiddleware
from app.core.auth import get_current_user
from app.middleware.rate_limit import RateLimitMiddleware

app = FastAPI(
    title="HUB Connect API",
    description="API for connecting 3rd party models to AI-PaaS",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Request timeout middleware
class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout: int = 300):  # 5분 타임아웃
        super().__init__(app)
        self.timeout = timeout
    
    async def dispatch(self, request: Request, call_next):
        try:
            # 요청에 타임아웃 적용
            response = await asyncio.wait_for(
                call_next(request), 
                timeout=self.timeout
            )
            return response
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

app.add_middleware(RequestTimeoutMiddleware, timeout=300)
app.add_middleware(RateLimitMiddleware, calls=200, period=60)  # 분당 200회 제한
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
    # 404 오류와 Chrome DevTools 관련 요청은 에러 로그에서 제외
    if exc.status_code == 404 and any(path in str(request.url) for path in [
        ".well-known/appspecific/com.chrome.devtools.json",
        "favicon.ico"
    ]):
        # 디버그 레벨로만 기록
        logger.debug(f"Resource not found: {request.url.path}")
    elif exc.status_code >= 500:
        # 서버 에러만 ERROR 레벨로 기록
        logger.error(f"HTTP error occurred: {exc.detail}")
    else:
        # 클라이언트 에러는 INFO 레벨로 기록
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


# Create a prefix router
prefix_router = APIRouter(prefix="/api/v1")

# Include other routers in the prefix_router
prefix_router.include_router(auth.router, prefix="/auth", tags=["auth"])
prefix_router.include_router(models.router, prefix="/models", tags=["models"])
prefix_router.include_router(tags.router, prefix="/tags", tags=["tags"])
prefix_router.include_router(storage.router, prefix="/storage", tags=["storage"])


# Add a new endpoint to show all routes under /api/v1
@prefix_router.get("/", summary="Get all API routes")
async def get_routes(current_user: dict = Depends(get_current_user)):
    logger.info("Retrieving all API routes")
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1"):
            for method in route.methods:
                routes.append(f"{method} {route.path}")

    # Sort routes first by path, then by HTTP method
    sorted_routes = sorted(set(routes), key=lambda x: (x.split()[1], x.split()[0]))

    logger.debug(f"Found {len(sorted_routes)} routes")
    return {"routes": sorted_routes}


# Include the prefix_router in the main app
app.include_router(prefix_router)


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info(f"Application is starting up. Log level: {settings.LOG_LEVEL}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application is shutting down")