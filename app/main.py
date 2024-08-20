from fastapi import FastAPI, APIRouter
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings
from app.api import models, tags
from app.core.logging import logger, LoggingMiddleware
import logging

app = FastAPI(
    title="HUB Connect API",
    description="API for connecting 3rd party models to AI-PaaS",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

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
    logger.error(f"HTTP error occurred: {exc.detail}")
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
prefix_router.include_router(models.router, prefix="/models", tags=["models"])
prefix_router.include_router(tags.router, prefix="/tags", tags=["tags"])


# Add a new endpoint to show all routes under /api/v1
@prefix_router.get("/", summary="Get all API routes")
async def get_routes():
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
    logging.info("Application is shutting down")