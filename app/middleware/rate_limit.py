import time
from typing import Dict, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.logging import logger

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls  # 허용 호출 수
        self.period = period  # 시간 기간 (초)
        self.clients: Dict[str, Tuple[int, float]] = {}  # {client_id: (count, timestamp)}
    
    def _get_client_id(self, request: Request) -> str:
        """클라이언트 식별자 추출"""
        # IP 주소 기반 (실제 환경에서는 사용자 ID 등을 사용할 수 있음)
        return request.client.host if request.client else "unknown"
    
    def _is_rate_limited(self, client_id: str) -> bool:
        """rate limit 체크"""
        current_time = time.time()
        
        if client_id not in self.clients:
            self.clients[client_id] = (1, current_time)
            return False
        
        count, timestamp = self.clients[client_id]
        
        # 시간 기간이 지났으면 카운트 리셋
        if current_time - timestamp > self.period:
            self.clients[client_id] = (1, current_time)
            return False
        
        # 제한 초과 확인
        if count >= self.calls:
            return True
        
        # 카운트 증가
        self.clients[client_id] = (count + 1, timestamp)
        return False
    
    async def dispatch(self, request: Request, call_next):
        client_id = self._get_client_id(request)
        
        if self._is_rate_limited(client_id):
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."}
            )
        
        response = await call_next(request)
        return response