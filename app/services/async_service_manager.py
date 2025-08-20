import asyncio
from contextlib import asynccontextmanager
from typing import AsyncContextManager, Optional
from app.core.logging import logger
from app.services.async_storage_service import AsyncStorageService
from app.services.markets.huggingface.async_huggingface_models import AsyncHuggingFaceService
from app.services.markets.huggingface.async_huggingface_tags import AsyncHuggingFaceTagsService

class AsyncServiceManager:
    """Centralized manager for all async services with proper resource management"""
    
    def __init__(self):
        self.storage_service: Optional[AsyncStorageService] = None
        self.huggingface_service: Optional[AsyncHuggingFaceService] = None
        self.huggingface_tags_service: Optional[AsyncHuggingFaceTagsService] = None
        self._initialized = False
        
    async def initialize(self):
        """Initialize all async services"""
        if self._initialized:
            return
            
        try:
            logger.info("Initializing async services...")
            
            # Initialize storage service with proper context manager
            self.storage_service = AsyncStorageService()
            await self.storage_service.__aenter__()
            
            # Initialize HuggingFace services
            self.huggingface_service = AsyncHuggingFaceService()
            self.huggingface_tags_service = AsyncHuggingFaceTagsService()
            
            self._initialized = True
            logger.info("All async services initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize async services: {str(e)}")
            await self.cleanup()
            raise
    
    async def cleanup(self):
        """Cleanup all async services"""
        if not self._initialized:
            return
            
        try:
            logger.info("Cleaning up async services...")
            
            # Cleanup storage service
            if self.storage_service:
                await self.storage_service.__aexit__(None, None, None)
                self.storage_service = None
                
            # Cleanup HuggingFace services
            if self.huggingface_service:
                await self.huggingface_service.close_http_client()
                self.huggingface_service = None
                
            if self.huggingface_tags_service:
                await self.huggingface_tags_service.close_http_client()
                self.huggingface_tags_service = None
                
            self._initialized = False
            logger.info("All async services cleaned up successfully")
            
        except Exception as e:
            logger.error(f"Error during async services cleanup: {str(e)}")
    
    @asynccontextmanager
    async def get_storage_service(self) -> AsyncContextManager[AsyncStorageService]:
        """Get storage service with proper context management"""
        if not self._initialized:
            await self.initialize()
            
        if not self.storage_service:
            raise RuntimeError("Storage service not initialized")
            
        yield self.storage_service
    
    @asynccontextmanager
    async def get_huggingface_service(self) -> AsyncContextManager[AsyncHuggingFaceService]:
        """Get HuggingFace service with proper context management"""
        if not self._initialized:
            await self.initialize()
            
        if not self.huggingface_service:
            raise RuntimeError("HuggingFace service not initialized")
            
        yield self.huggingface_service
    
    @asynccontextmanager
    async def get_huggingface_tags_service(self) -> AsyncContextManager[AsyncHuggingFaceTagsService]:
        """Get HuggingFace tags service with proper context management"""
        if not self._initialized:
            await self.initialize()
            
        if not self.huggingface_tags_service:
            raise RuntimeError("HuggingFace tags service not initialized")
            
        yield self.huggingface_tags_service
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()

# Global service manager instance
service_manager = AsyncServiceManager()

# Application lifespan context managers
@asynccontextmanager
async def lifespan_context():
    """Application lifespan context manager"""
    async with service_manager:
        yield service_manager

# Dependency injection functions for FastAPI
async def get_storage_service():
    """FastAPI dependency for storage service"""
    if not service_manager._initialized:
        await service_manager.initialize()
    return service_manager.storage_service

async def get_huggingface_service():
    """FastAPI dependency for HuggingFace service"""
    if not service_manager._initialized:
        await service_manager.initialize()
    return service_manager.huggingface_service

async def get_huggingface_tags_service():
    """FastAPI dependency for HuggingFace tags service"""
    if not service_manager._initialized:
        await service_manager.initialize()
    return service_manager.huggingface_tags_service