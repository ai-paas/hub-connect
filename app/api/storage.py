from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import io

from app.services.storage_service import StorageService
from app.core.auth import get_current_user
from app.core.logging import logger
from app.services.upload_tracker import upload_tracker

router = APIRouter(tags=["storage"])

# 필요한 최소한의 모델들만 여기서 정의 (기존 패턴 유지)
class FileRenameRequest(BaseModel):
    old_name: str
    new_name: str

class CreateBucketRequest(BaseModel):
    name: str
    description: Optional[str] = None

@router.get("/")
async def list_storage(
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """저장소 목록 조회"""
    try:
        return await storage_service.list_buckets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{storage_name}/files")
async def list_files(
    storage_name: str,
    path: str = Query("", description="Path to the directory"),
    depth: Optional[int] = Query(None, description="Depth of folder structure to return"),
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """저장소 내 파일 목록을 트리 구조로 조회"""
    try:
        return await storage_service.list_objects_as_tree(storage_name, path, depth)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{storage_name}/upload")
async def upload_file(
    storage_name: str,
    file: UploadFile = File(...),
    prefix: str = Query("", description="업로드 경로"),
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """파일 업로드 (대용량 파일 지원)"""
    try:
        result = await storage_service.upload_file(storage_name, file, prefix)
        return {
            "success": True,
            "message": "File uploaded successfully",
            "file_url": result["file_url"],
            "upload_id": result["upload_id"],
            "file_size": file.size,
            "filename": file.filename
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in upload_file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{storage_name}/download/{file_key:path}")
async def download_file(
        storage_name: str,
        file_key: str,
        storage_service: StorageService = Depends(StorageService),
        current_user: dict = Depends(get_current_user)
):
    """파일 다운로드"""
    try:
        content = await storage_service.download_file(storage_name, file_key)

        # 파일 확장자로부터 미디어 타입 추정
        content_type = "application/octet-stream"
        if file_key.lower().endswith(('.png', '.jpg', '.jpeg')):
            content_type = "image/jpeg" if file_key.lower().endswith('.jpg') or file_key.lower().endswith(
                '.jpeg') else "image/png"
        elif file_key.lower().endswith('.pdf'):
            content_type = "application/pdf"

        return StreamingResponse(
            io.BytesIO(content),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={file_key.split('/')[-1]}"
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in download_file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{storage_name}/rename")
async def rename_file(
    storage_name: str,
    request: FileRenameRequest,
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """파일 이름 변경"""
    try:
        await storage_service.rename_file(
            storage_name,
            request.old_name,
            request.new_name
        )
        return {
            "success": True,
            "message": "File renamed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{storage_name}/{file_key:path}")
async def delete_file(
    storage_name: str,
    file_key: str,
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """파일 삭제"""
    try:
        await storage_service.delete_file(storage_name, file_key)
        return {
            "success": True,
            "message": "File deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bucket")
async def create_bucket(
    request: CreateBucketRequest,
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """새로운 버킷 생성"""
    try:
        await storage_service.create_bucket(request.name)
        return {
            "success": True,
            "message": f"Bucket '{request.name}' created successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/bucket/{bucket_name}")
async def delete_bucket(
    bucket_name: str,
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """버킷 삭제 (버킷 내 모든 파일도 함께 삭제)"""
    try:
        await storage_service.delete_bucket(bucket_name)
        return {
            "success": True,
            "message": f"Bucket '{bucket_name}' and all its contents deleted successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{storage_name}/upload/{upload_id}/progress")
async def get_upload_progress(
    storage_name: str,
    upload_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """업로드 진행 상황 조회"""
    try:
        progress = await upload_tracker.get_progress(upload_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Upload not found")
        
        return {
            "upload_id": progress.upload_id,
            "filename": progress.filename,
            "progress_percent": round(progress.progress_percent, 2),
            "uploaded_size": progress.uploaded_size, 
            "total_size": progress.total_size,
            "status": progress.status,
            "elapsed_time": round(progress.elapsed_time, 2),
            "upload_speed": round(progress.upload_speed / 1024 / 1024, 2),  # MB/s
            "parts_completed": progress.parts_completed,
            "total_parts": progress.total_parts,
            "error_message": progress.error_message
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/uploads")
async def list_uploads(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """모든 업로드 목록 조회"""
    try:
        uploads = await upload_tracker.get_all_uploads()
        return {
            "uploads": [
                {
                    "upload_id": upload.upload_id,
                    "filename": upload.filename,
                    "progress_percent": round(upload.progress_percent, 2),
                    "status": upload.status,
                    "elapsed_time": round(upload.elapsed_time, 2)
                }
                for upload in uploads.values()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
