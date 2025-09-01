import time
from typing import Dict, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.logging import logger

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls  # Allowed number of calls
        self.period = period  # Time period (seconds)
        self.clients: Dict[str, Tuple[int, float]] = {}  # {client_id: (count, timestamp)}
    
    def _get_client_id(self, request: Request) -> str:
        """Extract client identifier"""
        # IP address based (in real environment, user ID etc. can be used)
        return request.client.host if request.client else "unknown"
    
    def _is_rate_limited(self, client_id: str) -> bool:
        """Check rate limit"""
        current_time = time.time()
        
        if client_id not in self.clients:
            self.clients[client_id] = (1, current_time)
            return False
        
        count, timestamp = self.clients[client_id]
        
        # Reset count if time period has passed
        if current_time - timestamp > self.period:
            self.clients[client_id] = (1, current_time)
            return False
        
        # Check limit exceeded
        if count >= self.calls:
            return True
        
        # Increment count
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