from functools import wraps
from typing import Callable, Any
from fastapi import HTTPException
from app.core.logging import logger


def handle_api_errors(default_status_code: int = 500, default_message: str = "Internal server error"):
    """
    API 엔드포인트에서 발생하는 예외를 일관되게 처리하는 데코레이터
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # FastAPI HTTPException은 그대로 재발생
                raise
            except Exception as e:
                # 모든 기타 예외를 로깅하고 일관된 HTTPException으로 변환
                logger.error(f"Error in {func.__name__}: {str(e)}")
                raise HTTPException(status_code=default_status_code, detail=default_message)
        return wrapper
    return decorator


def handle_service_errors(operation: str):
    """
    서비스 레이어에서 발생하는 예외를 처리하는 데코레이터
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {operation}: {str(e)}")
                raise
        return wrapper
    return decorator