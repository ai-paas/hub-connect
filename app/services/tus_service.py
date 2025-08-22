import json
import uuid
from io import BytesIO
from typing import Optional
from tuspyserver.repo import BaseRepo
from tuspyserver.file_info import FileInfo
from app.services.async_storage_service import AsyncStorageService
from app.services.redis_service import RedisService
from app.core.config import settings
from app.core.logging import logger
from app.utils.tus_helpers import calculate_optimal_part_size, format_size, validate_part_constraints

# Use a specific prefix for tus uploads in Redis to avoid key collisions
REDIS_TUS_PREFIX = "tus_upload:"
REDIS_BUFFER_PREFIX = "tus_buffer:"
# Set an expiration time for upload metadata in Redis (e.g., 24 hours)
TUS_EXPIRATION_SECONDS = 86400
# Buffer expiration (shorter than main data)
BUFFER_EXPIRATION_SECONDS = 3600  # 1 hour

class ChunkBuffer:
    """Buffer for accumulating chunks before uploading as S3 parts."""
    
    def __init__(self, target_size: int):
        self.buffer = BytesIO()
        self.target_size = target_size
        self.total_written = 0
    
    def add_chunk(self, chunk: bytes) -> bool:
        """Add chunk to buffer. Returns True if buffer is ready for upload."""
        self.buffer.write(chunk)
        self.total_written += len(chunk)
        return self.total_written >= self.target_size
    
    def get_data(self) -> bytes:
        """Get buffered data and reset buffer."""
        data = self.buffer.getvalue()
        self.reset()
        return data
    
    def reset(self):
        """Reset buffer for next part."""
        self.buffer.close()
        self.buffer = BytesIO()
        self.total_written = 0
    
    def size(self) -> int:
        """Get current buffer size."""
        return self.total_written
    
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return self.total_written == 0


class S3TusRepo(BaseRepo):
    def __init__(self, storage_service: AsyncStorageService, redis_service: RedisService):
        self.storage_service = storage_service
        self.redis_service = redis_service
        # In-memory chunk buffers for active uploads
        self._chunk_buffers = {}

    def _serialize_file_info(self, file_info: FileInfo) -> str:
        """Serialize FileInfo object to a JSON string for Redis."""
        return json.dumps({
            "id": file_info.id,
            "size": file_info.size,
            "offset": file_info.offset,
            "metadata": file_info.metadata,
            "custom_metadata": file_info.custom_metadata
        })

    def _deserialize_file_info(self, data: str) -> FileInfo:
        """Deserialize JSON string from Redis back to a FileInfo object."""
        obj = json.loads(data)
        return FileInfo(
            id=obj["id"],
            size=obj["size"],
            offset=obj["offset"],
            metadata=obj["metadata"],
            custom_metadata=obj["custom_metadata"]
        )

    async def create(self, file_info: FileInfo) -> FileInfo:
        file_info.id = str(uuid.uuid4())
        file_location = f"tus_uploads/{file_info.id}/{file_info.metadata.get('filename', 'file')}"

        # Calculate optimal part size based on file size
        optimal_part_size = calculate_optimal_part_size(file_info.size)
        
        try:
            response = await self.storage_service.s3_client.create_multipart_upload(
                Bucket=self._get_bucket_name(),
                Key=file_location
            )
            file_info.custom_metadata = {
                "s3_upload_id": response['UploadId'],
                "s3_key": file_location,
                "parts": [],
                "target_part_size": optimal_part_size,
                "buffer_size": 0
            }
            
            # Initialize chunk buffer for this upload
            self._chunk_buffers[file_info.id] = ChunkBuffer(optimal_part_size)
            
            async with self.redis_service.get_client() as redis:
                await redis.set(
                    f"{REDIS_TUS_PREFIX}{file_info.id}",
                    self._serialize_file_info(file_info),
                    ex=TUS_EXPIRATION_SECONDS
                )
            
            logger.info(
                f"Created S3 multipart upload for Tus file {file_info.id} "
                f"(size: {format_size(file_info.size)}, part_size: {format_size(optimal_part_size)})"
            )
        except Exception as e:
            logger.error(f"Failed to create S3 multipart upload: {e}")
            raise
        return file_info

    async def get_file_info(self, file_id: str) -> FileInfo | None:
        async with self.redis_service.get_client() as redis:
            data = await redis.get(f"{REDIS_TUS_PREFIX}{file_id}")
            if data:
                return self._deserialize_file_info(data)
        return None

    async def patch(self, file_id: str, offset: int, chunk: bytes) -> FileInfo:
        file_info = await self.get_file_info(file_id)
        if file_info is None:
            raise FileNotFoundError(f"File with id {file_id} not found in Redis")

        if offset != file_info.offset:
            raise ValueError(f"Invalid offset. Expected {file_info.offset}, got {offset}")

        # Get or create chunk buffer for this upload
        if file_id not in self._chunk_buffers:
            target_part_size = file_info.custom_metadata.get("target_part_size", 
                                                            calculate_optimal_part_size(file_info.size))
            self._chunk_buffers[file_id] = ChunkBuffer(target_part_size)

        chunk_buffer = self._chunk_buffers[file_id]
        
        try:
            # Add chunk to buffer
            buffer_ready = chunk_buffer.add_chunk(chunk)
            file_info.offset += len(chunk)
            file_info.custom_metadata["buffer_size"] = chunk_buffer.size()
            
            # If buffer is ready or this is the final chunk, upload to S3
            is_final_chunk = file_info.offset >= file_info.size
            
            if buffer_ready or is_final_chunk:
                if not chunk_buffer.is_empty():
                    await self._upload_buffered_part(file_info, chunk_buffer)
            
            # Update Redis with current state
            async with self.redis_service.get_client() as redis:
                await redis.set(
                    f"{REDIS_TUS_PREFIX}{file_id}",
                    self._serialize_file_info(file_info),
                    ex=TUS_EXPIRATION_SECONDS
                )
            
            chunk_size_str = format_size(len(chunk))
            buffer_size_str = format_size(chunk_buffer.size())
            logger.debug(
                f"Processed chunk for Tus file {file_id}: "
                f"chunk={chunk_size_str}, buffer={buffer_size_str}, "
                f"offset={file_info.offset}/{file_info.size}"
            )
            
        except Exception as e:
            logger.error(f"Failed to process chunk for Tus file {file_id}: {e}")
            raise
        
        return file_info

    async def finish(self, file_id: str):
        file_info = await self.get_file_info(file_id)
        if file_info is None:
            raise FileNotFoundError(f"File with id {file_id} not found")

        try:
            # Upload any remaining buffered data
            if file_id in self._chunk_buffers:
                chunk_buffer = self._chunk_buffers[file_id]
                if not chunk_buffer.is_empty():
                    await self._upload_buffered_part(file_info, chunk_buffer)
                    
                    # Update Redis with final state
                    async with self.redis_service.get_client() as redis:
                        await redis.set(
                            f"{REDIS_TUS_PREFIX}{file_id}",
                            self._serialize_file_info(file_info),
                            ex=TUS_EXPIRATION_SECONDS
                        )
            
            # Complete multipart upload
            await self.storage_service.s3_client.complete_multipart_upload(
                Bucket=self._get_bucket_name(),
                Key=file_info.custom_metadata["s3_key"],
                UploadId=file_info.custom_metadata["s3_upload_id"],
                MultipartUpload={'Parts': file_info.custom_metadata["parts"]}
            )
            
            total_parts = len(file_info.custom_metadata["parts"])
            logger.info(
                f"Completed S3 multipart upload for Tus file {file_id}: "
                f"{total_parts} parts, {format_size(file_info.size)}"
            )
            
            # Clean up resources
            await self._cleanup_upload(file_id)
            
        except Exception as e:
            logger.error(f"Failed to complete S3 multipart upload for Tus file {file_id}: {e}")
            raise

    async def delete(self, file_id: str):
        file_info = await self.get_file_info(file_id)
        if file_info:
            try:
                await self.storage_service.s3_client.abort_multipart_upload(
                    Bucket=self._get_bucket_name(),
                    Key=file_info.custom_metadata["s3_key"],
                    UploadId=file_info.custom_metadata["s3_upload_id"]
                )
                logger.info(f"Aborted S3 multipart upload for Tus file {file_id}")
            except Exception as e:
                logger.error(f"Failed to abort S3 multipart upload for Tus file {file_id}: {e}")
            finally:
                # Always clean up all resources
                await self._cleanup_upload(file_id)

    async def _upload_buffered_part(self, file_info: FileInfo, chunk_buffer: ChunkBuffer):
        """Upload buffered chunks as a single S3 part."""
        if chunk_buffer.is_empty():
            return
            
        part_data = chunk_buffer.get_data()
        part_number = len(file_info.custom_metadata.get("parts", [])) + 1
        
        try:
            response = await self.storage_service.s3_client.upload_part(
                Bucket=self._get_bucket_name(),
                Key=file_info.custom_metadata["s3_key"],
                PartNumber=part_number,
                UploadId=file_info.custom_metadata["s3_upload_id"],
                Body=part_data
            )
            
            file_info.custom_metadata["parts"].append({
                'ETag': response['ETag'],
                'PartNumber': part_number
            })
            file_info.custom_metadata["buffer_size"] = 0
            
            logger.info(
                f"Uploaded part {part_number} for Tus file {file_info.id}: "
                f"{format_size(len(part_data))}"
            )
            
        except Exception as e:
            logger.error(
                f"Failed to upload part {part_number} for Tus file {file_info.id}: {e}"
            )
            raise
    
    async def _cleanup_upload(self, file_id: str):
        """Clean up all resources associated with an upload."""
        # Remove chunk buffer
        if file_id in self._chunk_buffers:
            self._chunk_buffers[file_id].reset()
            del self._chunk_buffers[file_id]
        
        # Remove from Redis
        async with self.redis_service.get_client() as redis:
            await redis.delete(f"{REDIS_TUS_PREFIX}{file_id}")
            await redis.delete(f"{REDIS_BUFFER_PREFIX}{file_id}")
    
    def _get_bucket_name(self) -> str:
        if not settings.TUS_UPLOAD_BUCKET:
            raise ValueError("TUS_UPLOAD_BUCKET is not configured in settings.")
        return settings.TUS_UPLOAD_BUCKET