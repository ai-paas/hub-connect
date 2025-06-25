import asyncio
import time
from typing import Callable, Any, Optional
from enum import Enum
from app.core.logging import logger

class CircuitState(Enum):
    CLOSED = "closed"      # 정상 동작
    OPEN = "open"          # 차단 상태
    HALF_OPEN = "half_open"  # 복구 시도 상태

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,     # 실패 임계값
        recovery_timeout: int = 60,     # 복구 시도 대기 시간(초)
        expected_exception: tuple = (Exception,)  # 감지할 예외 타입
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED
        
    def _can_attempt_reset(self) -> bool:
        """복구 시도가 가능한지 확인"""
        return (
            self.state == CircuitState.OPEN and
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    def _record_success(self):
        """성공 기록"""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        
    def _record_failure(self):
        """실패 기록"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Circuit breaker를 통한 함수 호출"""
        
        # OPEN 상태에서 복구 시도 가능한지 확인
        if self._can_attempt_reset():
            self.state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker attempting recovery")
        
        # OPEN 상태일 때는 즉시 실패
        if self.state == CircuitState.OPEN:
            raise Exception("Circuit breaker is OPEN - too many failures")
        
        try:
            # 함수 실행
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # 성공 시 상태 리셋
            self._record_success()
            if self.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker recovered - state is now CLOSED")
            
            return result
            
        except self.expected_exception as e:
            # 예상된 예외 발생 시 실패 기록
            self._record_failure()
            logger.error(f"Circuit breaker recorded failure: {str(e)}")
            raise
        except Exception as e:
            # 예상하지 못한 예외는 그대로 전파
            logger.error(f"Unexpected error in circuit breaker: {str(e)}")
            raise

# 글로벌 circuit breaker 인스턴스들
storage_circuit_breaker = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=30,
    expected_exception=(Exception,)
)

external_api_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=(Exception,)
)