import re
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.core.auth import get_current_user
from app.core.logging import logger
from app.services.async_service_manager import get_storage_service
from app.services.upload_tracker import upload_tracker

# Unified storage router (maintaining existing URL structure)
buckets_router = APIRouter(prefix="/buckets", tags=["buckets"])
uploads_router = APIRouter(prefix="/uploads", tags=["uploads"])

# Request/Response models
class CreateBucketRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=3,
        max_length=63,
        description=(
            "생성할 버킷 이름입니다. 3~63자의 영문 소문자, 숫자, 하이픈(-), 마침표(.)를 사용할 수 있습니다."
        ),
        examples=["team-assets"],
    )
    
    @field_validator('name')
    @classmethod
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
    id: str = Field(
        ...,
        description="버킷 식별자입니다. 현재는 버킷 이름과 동일합니다.",
        examples=["team-assets"],
    )
    name: str = Field(
        ...,
        description="버킷 이름입니다.",
        examples=["team-assets"],
    )
    creation_date: str = Field(
        ...,
        description="스토리지 백엔드가 반환한 버킷 생성 시각 문자열입니다.",
        examples=["2026-04-15T09:30:00Z"],
    )
    object_count: Optional[int] = None
    size: Optional[int] = None


class CreateBucketResponse(BaseModel):
    id: str = Field(
        ...,
        description="생성된 버킷 식별자입니다.",
        examples=["team-assets"],
    )
    name: str = Field(
        ...,
        description="생성된 버킷 이름입니다.",
        examples=["team-assets"],
    )
    message: str = Field(
        ...,
        description="버킷 생성 결과 메시지입니다.",
        examples=["Bucket 'team-assets' created successfully"],
    )

# ==============================================
# BUCKET MANAGEMENT APIs
# ==============================================

@buckets_router.get(
    "",
    response_model=List[BucketResponse],
    summary="버킷 목록 조회",
    description=(
        "인증된 사용자가 접근 가능한 버킷 목록을 조회합니다.\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| id | 버킷 식별자입니다. 현재는 버킷 이름과 동일합니다. |\n"
        "| name | 버킷 이름입니다. |\n"
        "| creation_date | 스토리지에서 반환한 버킷 생성 시각입니다. |"
    ),
    responses={
        200: {
            "description": "버킷 목록을 정상적으로 조회했습니다.",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "team-assets",
                            "name": "team-assets",
                            "creation_date": "2026-04-15T09:30:00Z",
                        },
                        {
                            "id": "ml-datasets",
                            "name": "ml-datasets",
                            "creation_date": "2026-04-10T14:12:33Z",
                        },
                    ]
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            },
        },
        500: {
            "description": "내부 오류 또는 스토리지 연동 문제로 버킷 목록 조회에 실패했습니다.",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to list buckets"}
                }
            },
        },
    },
)
async def list_buckets(
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> List[BucketResponse]:
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
        logger.error(f"Error listing buckets: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list buckets")

@buckets_router.post(
    "",
    response_model=CreateBucketResponse,
    summary="버킷 생성",
    description=(
        "새 버킷을 생성합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- |\n"
        "| name | Y | 3~63자. 영문 소문자, 숫자, 하이픈(-), 마침표(.) 사용 가능. 시작과 끝은 영문 소문자 또는 숫자여야 하며 '..', '.-', '-.' 및 IP 주소 형식은 허용되지 않습니다. | team-assets |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| id | 생성된 버킷 식별자입니다. |\n"
        "| name | 생성된 버킷 이름입니다. |\n"
        "| message | 생성 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "버킷이 정상적으로 생성되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "id": "team-assets",
                        "name": "team-assets",
                        "message": "Bucket 'team-assets' created successfully",
                    }
                }
            },
        },
        400: {
            "description": "버킷 이름 형식이 잘못되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid bucket name: Bucket name cannot be formatted as an IP address"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            },
        },
        409: {
            "description": "동일한 이름의 버킷이 이미 존재합니다.",
            "content": {
                "application/json": {
                    "example": {"detail": "Bucket 'team-assets' already exists."}
                }
            },
        },
        422: {
            "description": "요청 본문 검증에 실패했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "string_too_short",
                                "loc": ["body", "name"],
                                "msg": "String should have at least 3 characters",
                                "input": "ab",
                                "ctx": {"min_length": 3},
                            }
                        ]
                    }
                }
            },
        },
        500: {
            "description": "내부 오류 또는 스토리지 연동 문제로 버킷 생성에 실패했습니다.",
            "content": {
                "application/json": {
                    "example": {"detail": "Create bucket failed: internal error"}
                }
            },
        },
    },
)
async def create_bucket(
    request: CreateBucketRequest,
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
) -> CreateBucketResponse:
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

@buckets_router.get(
    "/{bucket_id}",
    response_model=BucketResponse,
    summary="버킷 상세 조회",
    description=(
        "버킷 상세 정보를 조회합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 조회할 버킷 이름입니다. | team-assets |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| id | 버킷 식별자입니다. |\n"
        "| name | 버킷 이름입니다. |\n"
        "| creation_date | 버킷 생성 시각입니다. |\n"
        "| object_count | 버킷 내부 객체 개수입니다. |\n"
        "| size | 버킷 내부 전체 객체 크기 합계(byte)입니다. |"
    ),
    responses={
        200: {
            "description": "버킷 상세 정보를 정상적으로 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "id": "team-assets",
                        "name": "team-assets",
                        "creation_date": "2026-04-15T09:30:00Z",
                        "object_count": 128,
                        "size": 104857600,
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        404: {
            "description": "요청한 버킷이 존재하지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Bucket 'team-assets' not found"}}},
        },
        500: {
            "description": "버킷 상세 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def get_bucket(
    bucket_id: str = Path(..., description="조회할 버킷 이름", examples=["team-assets"]),
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

@buckets_router.delete(
    "/{bucket_id}",
    summary="버킷 삭제",
    description=(
        "버킷과 내부 객체를 모두 삭제합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 삭제할 버킷 이름입니다. | team-assets |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| message | 삭제 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "버킷 삭제가 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Bucket 'team-assets' and all its contents deleted successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        404: {
            "description": "요청한 버킷이 존재하지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Bucket 'team-assets' not found"}}},
        },
        500: {
            "description": "버킷 삭제에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def delete_bucket(
    bucket_id: str = Path(..., description="삭제할 버킷 이름", examples=["team-assets"]),
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

@buckets_router.get(
    "/{bucket_id}/objects",
    summary="버킷 객체 목록 조회",
    description=(
        "버킷 내부 객체와 폴더 구조를 조회합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 조회할 버킷 이름입니다. | team-assets |\n"
        "| prefix | query | N | 특정 경로 하위만 조회할 때 사용하는 접두 경로입니다. | images/2026/ |\n"
        "| depth | query | N | 반환할 폴더 깊이입니다. | 2 |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| name | 현재 조회 기준 폴더 이름입니다. prefix가 없으면 버킷 이름이 들어갑니다. |\n"
        "| path | 현재 조회 기준 경로입니다. |\n"
        "| type | 현재 노드 타입입니다. 루트는 `folder`입니다. |\n"
        "| size | 현재 노드 크기 값입니다. 폴더는 고정값 4096으로 반환됩니다. |\n"
        "| modified | 현재 노드 수정 시각 타임스탬프입니다. |\n"
        "| children | 하위 폴더/파일 목록입니다. 폴더와 파일이 함께 포함됩니다. |\n\n"
        "children 내부 항목:\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| name | 파일 또는 폴더 이름입니다. |\n"
        "| path | 전체 경로입니다. |\n"
        "| type | `file` 또는 `folder`입니다. |\n"
        "| size | 파일 크기(byte) 또는 폴더 고정값 4096입니다. |\n"
        "| modified | 수정 시각 타임스탬프입니다. |\n"
        "| children | 하위 폴더 목록입니다. 폴더일 때만 포함됩니다. |"
    ),
    responses={
        200: {
            "description": "객체 목록을 정상적으로 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "name": "team-assets",
                        "path": "",
                        "type": "folder",
                        "size": 4096,
                        "modified": 1776237164.0,
                        "children": [
                            {
                                "name": "images",
                                "path": "images",
                                "type": "folder",
                                "size": 4096,
                                "modified": 1776237164.0,
                                "children": [
                                    {
                                        "name": "logo.png",
                                        "path": "images/logo.png",
                                        "type": "file",
                                        "size": 204800,
                                        "modified": 1776100000.0,
                                    }
                                ],
                            }
                        ],
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "객체 목록 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def list_folder_contents(
    bucket_id: str = Path(..., description="조회할 버킷 이름", examples=["team-assets"]),
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

@buckets_router.post(
    "/{bucket_id}/folders",
    summary="폴더 생성",
    description=(
        "버킷 안에 빈 폴더 경로를 생성합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| path | body | Y | 생성할 폴더 경로입니다. | images/2026/04/ |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| message | 생성 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "폴더가 정상적으로 생성되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Folder 'images/2026/04/' created successfully in bucket 'team-assets'"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "폴더 생성에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def create_folder(
    request: CreateFolderRequest,
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
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

@buckets_router.delete(
    "/{bucket_id}/folders/{folder_path:path}",
    summary="폴더 삭제",
    description=(
        "폴더와 하위 파일 및 하위 폴더를 모두 삭제합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| folder_path | path | Y | 삭제할 폴더 경로입니다. | images/2026/04/ |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| message | 삭제 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "폴더 삭제가 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Folder 'images/2026/04/' and all its contents deleted successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "폴더 삭제에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def delete_folder(
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
    folder_path: str = Path(..., description="삭제할 폴더 경로", examples=["images/2026/04/"]),
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

@buckets_router.put(
    "/{bucket_id}/folders/{folder_path:path}",
    summary="폴더 이름 변경",
    description=(
        "폴더 경로를 변경하거나 다른 위치로 이동합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| folder_path | path | Y | 변경 전 폴더 경로입니다. | images/tmp/ |\n"
        "| new_path | body | Y | 변경 후 폴더 경로입니다. | images/archive/ |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| old_path | 변경 전 폴더 경로입니다. |\n"
        "| new_path | 변경 후 폴더 경로입니다. |\n"
        "| message | 처리 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "폴더 경로 변경이 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "old_path": "images/tmp/",
                        "new_path": "images/archive/",
                        "message": "Folder renamed successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "폴더 이름 변경에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def rename_folder(
    request: RenameFolderRequest,
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
    folder_path: str = Path(..., description="변경 전 폴더 경로", examples=["images/tmp/"]),
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

@buckets_router.post(
    "/{bucket_id}/folders/{folder_path:path}/copy",
    summary="폴더 복사",
    description=(
        "폴더와 하위 내용을 지정한 경로로 복사합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| folder_path | path | Y | 복사할 원본 폴더 경로입니다. | images/source/ |\n"
        "| destination_path | body | Y | 복사 대상 폴더 경로입니다. | backup/images/source/ |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| source_path | 복사 원본 폴더 경로입니다. |\n"
        "| destination_path | 복사 대상 폴더 경로입니다. |\n"
        "| message | 처리 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "폴더 복사가 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "source_path": "images/source/",
                        "destination_path": "backup/images/source/",
                        "message": "Folder copied successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "폴더 복사에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def copy_folder(
    request: CopyFolderRequest,
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
    folder_path: str = Path(..., description="복사할 원본 폴더 경로", examples=["images/source/"]),
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

@buckets_router.get(
    "/{bucket_id}/folders/{folder_path:path}/stats",
    summary="폴더 통계 조회",
    description=(
        "폴더 하위 객체 수와 용량 등의 통계를 조회합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| folder_path | path | Y | 통계를 조회할 폴더 경로입니다. | images/2026/ |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| path | 통계 기준 폴더 경로입니다. |\n"
        "| total_size | 하위 파일 전체 크기 합계(byte)입니다. |\n"
        "| file_count | 하위 파일 개수입니다. |\n"
        "| folder_count | 하위 폴더 개수입니다. |"
    ),
    responses={
        200: {
            "description": "폴더 통계를 정상적으로 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "path": "images/2026/",
                        "file_count": 24,
                        "folder_count": 3,
                        "total_size": 52428800
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "폴더 통계 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def get_folder_stats(
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
    folder_path: str = Path(..., description="통계를 조회할 폴더 경로", examples=["images/2026/"]),
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

@buckets_router.post(
    "/{bucket_id}/objects",
    summary="객체 업로드",
    description=(
        "파일 객체를 버킷에 업로드합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 업로드 대상 버킷 이름입니다. | team-assets |\n"
        "| file | form-data | Y | 업로드할 파일입니다. | report.pdf |\n"
        "| prefix | query | N | 업로드할 경로 접두사입니다. | docs/2026/ |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| object_key | 업로드된 최종 객체 경로입니다. |\n"
        "| upload_id | 업로드 추적 ID입니다. |\n"
        "| file_size | 업로드 파일 크기(byte)입니다. |\n"
        "| filename | 업로드 원본 파일명입니다. |\n"
        "| message | 처리 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "객체 업로드가 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "object_key": "docs/2026/report.pdf",
                        "upload_id": "upload-123",
                        "file_size": 204800,
                        "filename": "report.pdf",
                        "message": "Object uploaded successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "객체 업로드에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def upload_object(
    bucket_id: str = Path(..., description="업로드 대상 버킷 이름", examples=["team-assets"]),
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

@buckets_router.get(
    "/{bucket_id}/objects/{object_key:path}",
    summary="객체 다운로드",
    description=(
        "버킷의 객체 파일을 다운로드합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| object_key | path | Y | 다운로드할 객체 경로입니다. | docs/2026/report.pdf |\n\n"
        "### 응답 필드\n"
        "| 항목 | 설명 |\n"
        "| --- | --- |\n"
        "| 응답 본문 | 파일 바이너리 스트림입니다. |\n"
        "| Content-Disposition | 다운로드 파일명을 포함한 헤더입니다. |\n"
        "| Content-Length | 파일 크기(byte)입니다. |\n"
        "| Accept-Ranges | 바이트 단위 다운로드 지원 여부입니다. |\n"
        "| ETag | 객체 ETag입니다. 값이 있을 때만 포함됩니다. |\n"
        "| Last-Modified | 객체 최종 수정 시각입니다. 값이 있을 때만 포함됩니다. |"
    ),
    responses={
        200: {
            "description": "파일 스트리밍 다운로드가 시작됩니다.",
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "객체 다운로드에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def download_object(
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
    object_key: str = Path(..., description="다운로드할 객체 경로", examples=["docs/2026/report.pdf"]),
    storage_service = Depends(get_storage_service),
    current_user: dict = Depends(get_current_user)
):
    """Download object with true streaming (no full memory buffering)"""
    try:
        stream_gen, metadata = await storage_service.stream_file(bucket_id, object_key)

        filename = object_key.split('/')[-1]

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(metadata["content_length"]),
            "Accept-Ranges": "bytes",
        }
        if metadata.get("etag"):
            headers["ETag"] = metadata["etag"]
        if metadata.get("last_modified"):
            headers["Last-Modified"] = str(metadata["last_modified"])

        return StreamingResponse(
            stream_gen,
            media_type=metadata["content_type"],
            headers=headers,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in download_object: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@buckets_router.put(
    "/{bucket_id}/objects/{object_key:path}",
    summary="객체 이름 변경",
    description=(
        "객체 이름을 변경하거나 다른 경로로 이동합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| object_key | path | Y | 변경 전 객체 경로입니다. | docs/draft.pdf |\n"
        "| new_key | body | Y | 변경 후 객체 경로입니다. | docs/final.pdf |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| old_key | 변경 전 객체 경로입니다. |\n"
        "| new_key | 변경 후 객체 경로입니다. |\n"
        "| message | 처리 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "객체 이름 변경이 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "old_key": "docs/draft.pdf",
                        "new_key": "docs/final.pdf",
                        "message": "Object renamed successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "객체 이름 변경에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def update_object(
    request: ObjectRenameRequest,
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
    object_key: str = Path(..., description="변경 전 객체 경로", examples=["docs/draft.pdf"]),
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

@buckets_router.post(
    "/{bucket_id}/objects/{object_key:path}/copy",
    summary="객체 복사",
    description=(
        "객체를 같은 버킷 또는 다른 버킷으로 복사합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 원본 버킷 이름입니다. | team-assets |\n"
        "| object_key | path | Y | 복사할 원본 객체 경로입니다. | docs/report.pdf |\n"
        "| destination_key | body | Y | 복사 후 객체 경로입니다. | backup/report.pdf |\n"
        "| destination_bucket | body | N | 대상 버킷 이름입니다. 없으면 현재 버킷에 복사합니다. | archive-assets |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| source_key | 복사 원본 객체 경로입니다. |\n"
        "| destination_key | 복사 대상 객체 경로입니다. |\n"
        "| destination_bucket | 복사 대상 버킷 이름입니다. 지정하지 않으면 현재 버킷 이름이 반환됩니다. |\n"
        "| message | 처리 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "객체 복사가 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "source_key": "docs/report.pdf",
                        "destination_key": "backup/report.pdf",
                        "destination_bucket": "archive-assets",
                        "message": "Object copied successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "객체 복사에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def copy_object(
    request: CopyObjectRequest,
    bucket_id: str = Path(..., description="원본 버킷 이름", examples=["team-assets"]),
    object_key: str = Path(..., description="복사할 원본 객체 경로", examples=["docs/report.pdf"]),
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

@buckets_router.delete(
    "/{bucket_id}/objects/{object_key:path}",
    summary="객체 삭제",
    description=(
        "버킷의 객체 파일을 삭제합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| bucket_id | path | Y | 대상 버킷 이름입니다. | team-assets |\n"
        "| object_key | path | Y | 삭제할 객체 경로입니다. | docs/report.pdf |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| object_key | 삭제한 객체 경로입니다. |\n"
        "| message | 처리 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "객체 삭제가 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "object_key": "docs/report.pdf",
                        "message": "Object deleted successfully"
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "객체 삭제에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
async def delete_object(
    bucket_id: str = Path(..., description="대상 버킷 이름", examples=["team-assets"]),
    object_key: str = Path(..., description="삭제할 객체 경로", examples=["docs/report.pdf"]),
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

@uploads_router.get(
    "",
    summary="업로드 목록 조회",
    description=(
        "현재 추적 중인 업로드 작업 목록을 조회합니다.\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| uploads | 업로드 작업 목록입니다. |\n\n"
        "uploads 내부 항목:\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| upload_id | 업로드 추적 ID입니다. |\n"
        "| filename | 업로드 파일명입니다. |\n"
        "| progress_percent | 업로드 진행률(%)입니다. |\n"
        "| status | 업로드 상태입니다. |\n"
        "| elapsed_time | 업로드 시작 후 경과 시간(초)입니다. |"
    ),
    responses={
        200: {
            "description": "업로드 목록을 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "uploads": [
                            {
                                "upload_id": "upload-123",
                                "filename": "report.pdf",
                                "progress_percent": 65.5,
                                "status": "uploading",
                                "elapsed_time": 12.3,
                            }
                        ]
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        500: {
            "description": "업로드 목록 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
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

@uploads_router.get(
    "/{upload_id}",
    summary="업로드 진행 상태 조회",
    description=(
        "특정 업로드 작업의 진행 상태를 상세 조회합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| upload_id | path | Y | 조회할 업로드 추적 ID입니다. | upload-123 |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| upload_id | 업로드 추적 ID입니다. |\n"
        "| filename | 업로드 파일명입니다. |\n"
        "| progress_percent | 업로드 진행률(%)입니다. |\n"
        "| uploaded_size | 현재까지 업로드한 크기(byte)입니다. |\n"
        "| total_size | 전체 파일 크기(byte)입니다. |\n"
        "| status | 업로드 상태입니다. |\n"
        "| elapsed_time | 업로드 시작 후 경과 시간(초)입니다. |\n"
        "| upload_speed | 업로드 속도(MB/s)입니다. |\n"
        "| parts_completed | 완료된 파트 수입니다. |\n"
        "| total_parts | 전체 파트 수입니다. |\n"
        "| error_message | 오류 발생 시 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "업로드 진행 상태를 정상 조회했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "upload_id": "upload-123",
                        "filename": "report.pdf",
                        "progress_percent": 65.5,
                        "uploaded_size": 655360,
                        "total_size": 1000000,
                        "status": "uploading",
                        "elapsed_time": 12.3,
                        "upload_speed": 5.25,
                        "parts_completed": 3,
                        "total_parts": 5,
                        "error_message": None,
                    }
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        404: {
            "description": "요청한 업로드 ID가 존재하지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Upload not found"}}},
        },
        500: {
            "description": "업로드 진행 상태 조회에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
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

@uploads_router.delete(
    "/{upload_id}",
    summary="업로드 취소",
    description=(
        "진행 중인 업로드 작업을 취소합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| upload_id | path | Y | 취소할 업로드 추적 ID입니다. | upload-123 |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| upload_id | 취소한 업로드 추적 ID입니다. |\n"
        "| message | 취소 결과 메시지입니다. |"
    ),
    responses={
        200: {
            "description": "업로드 취소가 완료되었습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "upload_id": "upload-123",
                        "message": "Upload cancelled successfully",
                    }
                }
            },
        },
        400: {
            "description": "현재 상태에서는 업로드를 취소할 수 없습니다.",
            "content": {
                "application/json": {
                    "example": {"detail": "Cannot cancel upload with status: completed"}
                }
            },
        },
        401: {
            "description": "인증이 필요하거나 인증 정보가 올바르지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
        404: {
            "description": "요청한 업로드 ID가 존재하지 않습니다.",
            "content": {"application/json": {"example": {"detail": "Upload not found"}}},
        },
        500: {
            "description": "업로드 취소에 실패했습니다.",
            "content": {"application/json": {"example": {"detail": "internal error"}}},
        },
    },
)
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
