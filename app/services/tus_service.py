import os
import json
import asyncio
from typing import Optional, Dict
from app.services.async_storage_service import AsyncStorageService
from app.services.redis_service import RedisService
from app.core.config import settings
from app.core.logging import logger


class TusStorageHandler:
    """Custom storage handler for tuspyserver integration with S3 and Redis."""
    
    def __init__(self, storage_service: AsyncStorageService, redis_service: RedisService):
        self.storage_service = storage_service
        self.redis_service = redis_service
        self.upload_prefix = "tus_upload:"
        self.expiration_seconds = 86400  # 24 hours
    
    async def handle_upload_complete(self, file_id: str, upload_info: dict):
        """Handle completed upload by moving to S3 and cleaning up."""
        logger.info(f"TUS upload completed: {file_id}")
        
        # Get file info from local storage
        local_path = upload_info.get("file_path")
        if not local_path or not os.path.exists(local_path):
            logger.error(f"Local file not found for completed upload: {file_id}")
            return
        
        try:
            # Upload to S3
            filename = upload_info.get("filename", f"upload_{file_id}")
            s3_key = f"tus_uploads/{file_id}/{filename}"

            await self.storage_service.upload_file_from_path(
                bucket_name=self._get_bucket_name(),
                s3_key=s3_key,
                local_file_path=local_path,
                content_type=upload_info.get("content_type", "application/octet-stream")
            )
            
            # Store upload info in Redis for tracking
            if self.redis_service.is_available:
                async with self.redis_service.get_client() as redis:
                    upload_record = {
                        "s3_key": s3_key,
                        "bucket": self._get_bucket_name(),
                        "original_filename": filename,
                        "size": upload_info.get("size", 0),
                        "completed_at": upload_info.get("completed_at"),
                        "content_type": upload_info.get("content_type")
                    }
                    await redis.set(
                        f"{self.upload_prefix}{file_id}",
                        json.dumps(upload_record),
                        ex=self.expiration_seconds
                    )
            
            # Clean up local file
            try:
                os.remove(local_path)
                logger.debug(f"Cleaned up local file: {local_path}")
            except OSError as e:
                logger.warning(f"Failed to clean up local file {local_path}: {e}")
                
            logger.info(
                f"TUS upload {file_id} successfully stored to S3: {s3_key} "
                f"(size: {upload_info.get('size', 0)} bytes)"
            )
            
        except Exception as e:
            logger.error(f"Failed to handle upload completion for {file_id}: {e}")
            raise
    
    async def get_upload_info(self, file_id: str) -> Optional[Dict]:
        """Get upload info from Redis."""
        if not self.redis_service.is_available:
            return None
            
        try:
            async with self.redis_service.get_client() as redis:
                data = await redis.get(f"{self.upload_prefix}{file_id}")
                if data:
                    return json.loads(data)
        except Exception as e:
            logger.error(f"Failed to get upload info for {file_id}: {e}")
        
        return None
    
    def _get_bucket_name(self) -> str:
        if not settings.TUS_UPLOAD_BUCKET:
            raise ValueError("TUS_UPLOAD_BUCKET is not configured in settings.")
        return settings.TUS_UPLOAD_BUCKET


# Global handler instance
tus_handler = None

def get_tus_handler(
    storage_service: AsyncStorageService,
    redis_service: RedisService
) -> TusStorageHandler:
    """Get or create TUS storage handler instance."""
    global tus_handler
    if tus_handler is None:
        tus_handler = TusStorageHandler(storage_service, redis_service)
    return tus_handler