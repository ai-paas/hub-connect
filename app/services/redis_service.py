
import redis.asyncio as redis
import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from app.core.config import settings
from app.core.logging import logger

class RedisService:
    def __init__(self):
        self.pool: Optional[redis.ConnectionPool] = None
        self.is_connected = False
        self.is_available = False  # Track if Redis is available for use
        self._connection_retries = 0
        self._max_retries = 5
        self._retry_delay = 2.0
        self._initialization_failed = False

    async def initialize(self, fail_silently: bool = False):
        """Create a Redis connection pool with retry logic.
        
        Args:
            fail_silently: If True, don't raise exception on failure
        """
        if self.pool and self.is_connected and self.is_available:
            return
        
        # Check if Redis is configured
        if not settings.REDIS_HOST or not settings.REDIS_PORT:
            self.is_available = False
            self.is_connected = False
            self._initialization_failed = True
            
            if fail_silently:
                logger.info("Redis not configured - Redis features disabled")
                return
            else:
                error_msg = "Redis is not configured (REDIS_HOST and REDIS_PORT required)"
                logger.error(error_msg)
                raise ConnectionError(error_msg)
        
        # Reset state
        self._initialization_failed = False
        
        for attempt in range(self._max_retries):
            try:
                self.pool = redis.ConnectionPool.from_url(
                    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                    max_connections=20,
                    decode_responses=True,
                    retry_on_timeout=True,
                    retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                    health_check_interval=30,
                    socket_connect_timeout=5,
                    socket_timeout=10
                )
                
                # Test the connection
                if await self.ping():
                    self.is_connected = True
                    self.is_available = True
                    self._connection_retries = 0
                    
                    logger.info(
                        f"Redis connection pool created for {settings.REDIS_HOST}:{settings.REDIS_PORT} "
                        f"(attempt {attempt + 1}/{self._max_retries})"
                    )
                    return
                else:
                    raise redis.ConnectionError("Failed to ping Redis after connection")
                
            except Exception as e:
                self._connection_retries = attempt + 1
                self.is_connected = False
                self.is_available = False
                
                if attempt < self._max_retries - 1:
                    wait_time = self._retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Redis connection attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self._initialization_failed = True
                    error_msg = f"Failed to create Redis connection pool after {self._max_retries} attempts: {e}"
                    
                    if fail_silently:
                        logger.warning(f"{error_msg} - Redis features will be disabled")
                        return
                    else:
                        logger.error(error_msg)
                        raise

    async def close(self):
        """Close the Redis connection pool."""
        if self.pool:
            try:
                await self.pool.disconnect()
                logger.info("Redis connection pool closed.")
            except Exception as e:
                logger.warning(f"Error closing Redis connection pool: {e}")
            finally:
                self.pool = None
                self.is_connected = False
                self._connection_retries = 0

    @asynccontextmanager
    async def get_client(self):
        """Get a Redis client from the pool with automatic reconnection."""
        if not self.is_available:
            raise redis.ConnectionError("Redis is not available")
            
        if not self.pool or not self.is_connected:
            await self.initialize(fail_silently=False)
        
        client = None
        try:
            client = redis.Redis(connection_pool=self.pool)
            yield client
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis connection error: {e}. Attempting to reconnect...")
            self.is_connected = False
            self.is_available = False
            
            # Try to reconnect once
            try:
                await self.initialize(fail_silently=False)
                if client:
                    await client.close()
                client = redis.Redis(connection_pool=self.pool)
                yield client
            except Exception as reconnect_error:
                logger.error(f"Failed to reconnect to Redis: {reconnect_error}")
                self.is_available = False
                raise
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            raise
        finally:
            if client:
                try:
                    await client.close()
                except Exception as close_error:
                    logger.warning(f"Error closing Redis client: {close_error}")

    async def ping(self) -> bool:
        """Check if the Redis server is available."""
        try:
            if not self.pool:
                return False
                
            client = redis.Redis(connection_pool=self.pool)
            result = await client.ping()
            await client.close()
            return result
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            self.is_connected = False
            return False
    
    async def get_connection_info(self) -> dict:
        """Get Redis connection information for monitoring."""
        try:
            async with self.get_client() as client:
                info = await client.info()
                return {
                    "connected": self.is_connected,
                    "host": settings.REDIS_HOST,
                    "port": settings.REDIS_PORT,
                    "db": settings.REDIS_DB,
                    "connection_retries": self._connection_retries,
                    "redis_version": info.get("redis_version", "unknown"),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", 0)
                }
        except Exception as e:
            logger.warning(f"Unable to retrieve Redis connection information: {e}")
            return {
                "connected": False,
                "error": "Unable to retrieve Redis connection information",
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "connection_retries": self._connection_retries,
                "initialization_failed": self._initialization_failed
            }

redis_service = RedisService()

# Dependency for FastAPI
async def get_redis_client():
    return redis_service
