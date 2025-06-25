import asyncio
import time
from typing import Dict, Optional
from dataclasses import dataclass
from app.core.logging import logger

@dataclass
class UploadProgress:
    upload_id: str
    filename: str
    total_size: int
    uploaded_size: int
    status: str  # 'uploading', 'completed', 'failed', 'cancelled'
    start_time: float
    parts_completed: int = 0
    total_parts: int = 0
    error_message: Optional[str] = None
    
    @property
    def progress_percent(self) -> float:
        if self.total_size == 0:
            return 0.0
        return (self.uploaded_size / self.total_size) * 100
    
    @property  
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    @property
    def upload_speed(self) -> float:
        """업로드 속도 (bytes/second)"""
        if self.elapsed_time == 0:
            return 0.0
        return self.uploaded_size / self.elapsed_time

class UploadTracker:
    def __init__(self):
        self._uploads: Dict[str, UploadProgress] = {}
        self._lock = asyncio.Lock()
    
    async def start_upload(self, upload_id: str, filename: str, total_size: int, total_parts: int = 1) -> None:
        """업로드 시작"""
        async with self._lock:
            self._uploads[upload_id] = UploadProgress(
                upload_id=upload_id,
                filename=filename,
                total_size=total_size,
                uploaded_size=0,
                status='uploading',
                start_time=time.time(),
                total_parts=total_parts
            )
        logger.info(f"Started tracking upload: {upload_id}")
    
    async def update_progress(self, upload_id: str, uploaded_size: int, parts_completed: int = 0) -> None:
        """업로드 진행 상황 업데이트"""
        async with self._lock:
            if upload_id in self._uploads:
                upload = self._uploads[upload_id]
                upload.uploaded_size = uploaded_size
                upload.parts_completed = parts_completed
    
    async def complete_upload(self, upload_id: str) -> None:
        """업로드 완료"""
        async with self._lock:
            if upload_id in self._uploads:
                upload = self._uploads[upload_id]
                upload.status = 'completed'
                upload.uploaded_size = upload.total_size
        logger.info(f"Completed upload: {upload_id}")
    
    async def fail_upload(self, upload_id: str, error_message: str) -> None:
        """업로드 실패"""
        async with self._lock:
            if upload_id in self._uploads:
                upload = self._uploads[upload_id]
                upload.status = 'failed'
                upload.error_message = error_message
        logger.error(f"Failed upload: {upload_id}, error: {error_message}")
    
    async def cancel_upload(self, upload_id: str) -> None:
        """업로드 취소"""
        async with self._lock:
            if upload_id in self._uploads:
                upload = self._uploads[upload_id]
                upload.status = 'cancelled'
        logger.info(f"Cancelled upload: {upload_id}")
    
    async def get_progress(self, upload_id: str) -> Optional[UploadProgress]:
        """업로드 진행 상황 조회"""
        async with self._lock:
            return self._uploads.get(upload_id)
    
    async def get_all_uploads(self) -> Dict[str, UploadProgress]:
        """모든 업로드 상황 조회"""
        async with self._lock:
            return self._uploads.copy()
    
    async def cleanup_old_uploads(self, max_age_hours: int = 24) -> None:
        """오래된 업로드 기록 정리"""
        cutoff_time = time.time() - (max_age_hours * 3600)
        async with self._lock:
            to_remove = [
                upload_id for upload_id, upload in self._uploads.items()
                if upload.start_time < cutoff_time and upload.status in ['completed', 'failed', 'cancelled']
            ]
            for upload_id in to_remove:
                del self._uploads[upload_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old upload records")

# 글로벌 업로드 트래커 인스턴스
upload_tracker = UploadTracker()