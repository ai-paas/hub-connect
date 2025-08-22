from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from fastapi.responses import StreamingResponse
import io
import re

from app.services.async_service_manager import get_storage_service
from app.core.auth import get_current_user
from app.core.logging import logger
from app.services.upload_tracker import upload_tracker

# Unified storage router (maintaining existing URL structure)
buckets_router = APIRouter(prefix="/buckets", tags=["buckets"])
uploads_router = APIRouter(prefix="/uploads", tags=["uploads"])

# Request/Response models
class CreateBucketRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=63, description="Bucket name (3-63 characters)")
    description: Optional[str] = None
    
    @validator('name')
    def validate_bucket_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Bucket name cannot be empty or whitespace only')
        
        v = v.strip().lower()  # S3 bucket names should be lowercase
        
        # S3 bucket naming rules
        if not re.match(r'^[a-z0-9][a-z0-9.-]*[a-z0-9]$', v):
            raise ValueError('Bucket name must start and end with alphanumeric characters and contain only lowercase letters, numbers, hyphens, and periods')
        
        if '..' in v or '.-' in v or '-.' in v:
            raise ValueError('Bucket name cannot contain consecutive periods or period-hyphen combinations')
            
        if v.startswith('xn--') or v.endswith('-s3alias'):
            raise ValueError('Bucket name cannot start with "xn--" or end with "-s3alias"')
            
        # Check for IP address format
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', v):
            raise ValueError('Bucket name cannot be formatted as an IP address')
            
        return v

class ObjectRenameRequest(BaseModel):
    new_key: str

class CreateFolderRequest(BaseModel):
    path: str

class RenameFolderRequest(BaseModel):
    new_path: str

class CopyFolderRequest(BaseModel):
    destination_path: str

class CopyObjectRequest(BaseModel):
    destination_key: str
    destination_bucket: Optional[str] = None  # None if same bucket

class BatchOperationRequest(BaseModel):
    operation: str  # "copy", "move", "delete"
    items: List[str]  # object keys or folder paths
    destination: Optional[str] = None  # for copy/move operations

class BucketResponse(BaseModel):
    id: str
    name: str
    creation_date: str
    object_count: Optional[int] = None
    size: Optional[int] = None

# ==============================================
# BUCKET MANAGEMENT APIs
# ==============================================

@buckets_router.get("")
async def list_buckets(
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """List all buckets"""
    try:
        buckets = await storage_service.list_buckets()
        return [
            {
                "id": bucket["name"],
                "name": bucket["name"],
                "creation_date": bucket["creation_date"]
            }
            for bucket in buckets
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.post("")
async def create_bucket(
    request: CreateBucketRequest,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Create a new bucket"""
    try:
        await storage_service.create_bucket(request.name)
        return {
            "id": request.name,
            "name": request.name,
            "message": f"Bucket '{request.name}' created successfully"
        }
    except HTTPException as e:
        raise e
    except ValueError as e:
        # Handle validation errors from pydantic
        raise HTTPException(status_code=400, detail=f"Invalid bucket name: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error creating bucket '{request.name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Create bucket failed: {str(e)}")

@buckets_router.get("/{bucket_id}")
async def get_bucket(
    bucket_id: str,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> BucketResponse:
    """Get bucket details (includes object count and total size)"""
    try:
        details = await storage_service.get_bucket_details(bucket_id)
        return BucketResponse(
            id=details["name"],
            name=details["name"],
            creation_date=details["creation_date"],
            object_count=details["object_count"],
            size=details["size"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.delete("/{bucket_id}")
async def delete_bucket(
    bucket_id: str,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete bucket (deletes all objects in bucket as well)"""
    try:
        await storage_service.delete_bucket(bucket_id)
        return {
            "message": f"Bucket '{bucket_id}' and all its contents deleted successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================
# FOLDER MANAGEMENT APIs
# ==============================================

@buckets_router.get("/{bucket_id}/objects")
async def list_folder_contents(
    bucket_id: str,
    prefix: str = Query("", description="Folder path prefix"),
    depth: Optional[int] = Query(None, description="Depth of folder structure to return"),
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """List folder contents in tree structure"""
    try:
        return await storage_service.list_objects_as_tree(bucket_id, prefix, depth)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.post("/{bucket_id}/folders")
async def create_folder(
    bucket_id: str,
    request: CreateFolderRequest,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Create empty folder"""
    try:
        await storage_service.create_folder(bucket_id, request.path)
        return {
            "message": f"Folder '{request.path}' created successfully in bucket '{bucket_id}'"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.delete("/{bucket_id}/folders/{folder_path:path}")
async def delete_folder(
    bucket_id: str,
    folder_path: str,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete folder and all files/subfolders inside"""
    try:
        await storage_service.delete_folder(bucket_id, folder_path)
        return {
            "message": f"Folder '{folder_path}' and all its contents deleted successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error deleting folder '{folder_path}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.put("/{bucket_id}/folders/{folder_path:path}")
async def rename_folder(
    bucket_id: str,
    folder_path: str,
    request: RenameFolderRequest,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Rename/move folder"""
    try:
        await storage_service.rename_folder(bucket_id, folder_path, request.new_path)
        return {
            "old_path": folder_path,
            "new_path": request.new_path,
            "message": "Folder renamed successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error renaming folder '{folder_path}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.post("/{bucket_id}/folders/{folder_path:path}/copy")
async def copy_folder(
    bucket_id: str,
    folder_path: str,
    request: CopyFolderRequest,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Copy folder"""
    try:
        await storage_service.copy_folder(bucket_id, folder_path, request.destination_path)
        return {
            "source_path": folder_path,
            "destination_path": request.destination_path,
            "message": "Folder copied successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error copying folder '{folder_path}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.get("/{bucket_id}/folders/{folder_path:path}/stats")
async def get_folder_stats(
    bucket_id: str,
    folder_path: str,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get folder statistics"""
    try:
        stats = await storage_service.get_folder_stats(bucket_id, folder_path)
        return stats
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error getting folder stats for '{folder_path}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================
# OBJECT MANAGEMENT APIs
# ==============================================

@buckets_router.post("/{bucket_id}/objects")
async def upload_object(
    bucket_id: str,
    file: UploadFile = File(...),
    prefix: str = Query("", description="Object key prefix (upload path)"),
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Upload object (supports large files)"""
    try:
        result = await storage_service.upload_file(bucket_id, file, prefix)
        return {
            "object_key": f"{prefix}/{file.filename}" if prefix else file.filename,
            "upload_id": result["upload_id"],
            "file_size": file.size,
            "filename": file.filename,
            "message": "Object uploaded successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in upload_object: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.get("/{bucket_id}/objects/{object_key:path}")
async def download_object(
    bucket_id: str,
    object_key: str,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
):
    """Download object"""
    try:
        content = await storage_service.download_file(bucket_id, object_key)

        # Determine media type from file extension
        content_type = "application/octet-stream"
        if object_key.lower().endswith(('.png', '.jpg', '.jpeg')):
            content_type = "image/jpeg" if object_key.lower().endswith('.jpg') or object_key.lower().endswith(
                '.jpeg') else "image/png"
        elif object_key.lower().endswith('.pdf'):
            content_type = "application/pdf"

        return StreamingResponse(
            io.BytesIO(content),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={object_key.split('/')[-1]}"
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in download_object: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.put("/{bucket_id}/objects/{object_key:path}")
async def update_object(
    bucket_id: str,
    object_key: str,
    request: ObjectRenameRequest,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Rename/move object"""
    try:
        await storage_service.rename_file(
            bucket_id,
            object_key, # Use object_key from URL
            request.new_key
        )
        return {
            "old_key": object_key,
            "new_key": request.new_key,
            "message": "Object renamed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.post("/{bucket_id}/objects/{object_key:path}/copy")
async def copy_object(
    bucket_id: str,
    object_key: str,
    request: CopyObjectRequest,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Copy object"""
    try:
        await storage_service.copy_file(
            bucket_id, 
            object_key, 
            request.destination_key,
            request.destination_bucket
        )
        return {
            "source_key": object_key,
            "destination_key": request.destination_key,
            "destination_bucket": request.destination_bucket or bucket_id,
            "message": "Object copied successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error copying object '{object_key}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.delete("/{bucket_id}/objects/{object_key:path}")
async def delete_object(
    bucket_id: str,
    object_key: str,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete object"""
    try:
        await storage_service.delete_file(bucket_id, object_key)
        return {
            "object_key": object_key,
            "message": "Object deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================
# UPLOAD MANAGEMENT APIs
# ==============================================

@uploads_router.get("")
async def list_uploads(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """List all uploads"""
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

@uploads_router.get("/{upload_id}")
async def get_upload_progress(
    upload_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get upload progress"""
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

@uploads_router.delete("/{upload_id}")
async def cancel_upload(
    upload_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Cancel upload"""
    try:
        progress = await upload_tracker.get_progress(upload_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Upload not found")
        
        if progress.status in ["completed", "failed"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot cancel upload with status: {progress.status}"
            )
        
        await upload_tracker.fail_upload(upload_id, "Upload cancelled by user")
        
        return {
            "upload_id": upload_id,
            "message": "Upload cancelled successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error cancelling upload '{upload_id}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))