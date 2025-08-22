import asyncio
import time
from typing import Callable, Any, Optional
from enum import Enum
from app.core.logging import logger

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit blocked
    HALF_OPEN = "half_open"  # Recovery attempt state

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,     # Failure threshold
        recovery_timeout: int = 60,     # Recovery attempt wait time (seconds)
        expected_exception: tuple = (Exception,)  # Exception types to detect
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED
        
    def _can_attempt_reset(self) -> bool:
        """Check if recovery attempt is possible"""
        return (
            self.state == CircuitState.OPEN and
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    def _record_success(self):
        """Record success"""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        
    def _record_failure(self):
        """Record failure"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Function call through circuit breaker"""
        
        # Check if recovery attempt is possible in OPEN state
        if self._can_attempt_reset():
            self.state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker attempting recovery")
        
        # Immediate failure when in OPEN state
        if self.state == CircuitState.OPEN:
            raise Exception("Circuit breaker is OPEN - too many failures")
        
        try:
            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Reset state on success
            self._record_success()
            if self.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker recovered - state is now CLOSED")
            
            return result
            
        except self.expected_exception as e:
            # Record failure when expected exception occurs
            self._record_failure()
            logger.error(f"Circuit breaker recorded failure: {str(e)}")
            raise
        except Exception as e:
            # Propagate unexpected exceptions as-is
            logger.error(f"Unexpected error in circuit breaker: {str(e)}")
            raise

# Global circuit breaker instances
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