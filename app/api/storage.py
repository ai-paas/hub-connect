from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import io

from app.services.storage_service import StorageService
from app.core.auth import get_current_user
from app.core.logging import logger

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
        return storage_service.list_buckets()
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
        return storage_service.list_objects_as_tree(storage_name, path, depth)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{storage_name}/upload")
def upload_file(
    storage_name: str,
    file: UploadFile = File(...),
    prefix: str = Query("", description="업로드 경로"),
    storage_service: StorageService = Depends(StorageService),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """파일 업로드"""
    try:
        file_url = storage_service.upload_file(storage_name, file, prefix)
        return {
            "success": True,
            "message": "File uploaded successfully",
            "file_url": file_url
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in upload_file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{storage_name}/download/{file_key:path}")
def download_file(
        storage_name: str,
        file_key: str,
        storage_service: StorageService = Depends(StorageService),
        current_user: dict = Depends(get_current_user)
):
    """파일 다운로드"""
    try:
        content = storage_service.download_file(storage_name, file_key)

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
        storage_service.rename_file(
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
        storage_service.delete_file(storage_name, file_key)
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
        storage_service.create_bucket(request.name)
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
        storage_service.delete_bucket(bucket_name)
        return {
            "success": True,
            "message": f"Bucket '{bucket_name}' and all its contents deleted successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
