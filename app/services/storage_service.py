import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from typing import List, Optional, Dict, Any
from fastapi import UploadFile, HTTPException
import time
import asyncio
from app.core.config import settings
from app.core.logging import logger
from app.utils.circuit_breaker import storage_circuit_breaker
from app.services.upload_tracker import upload_tracker
import uuid

# Configure timeouts for storage operations
STORAGE_TIMEOUT_CONFIG = Config(
    read_timeout=60,      # 60 seconds for read operations
    connect_timeout=10,   # 10 seconds for connection
    retries={'max_attempts': 3, 'mode': 'adaptive'},  # Retry failed requests
    max_pool_connections=50,  # Connection pool size
    region_name='us-east-1'  # Default region
)

class StorageService:
    def __init__(self):
        try:
            if settings.STORAGE_TYPE == 'ceph':
                # Merge timeout config with Ceph-specific config
                ceph_config = Config(
                    signature_version='s3v4',
                    read_timeout=STORAGE_TIMEOUT_CONFIG.read_timeout,
                    connect_timeout=STORAGE_TIMEOUT_CONFIG.connect_timeout,
                    retries=STORAGE_TIMEOUT_CONFIG.retries
                )
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=settings.CEPH_ENDPOINT_URL,
                    aws_access_key_id=settings.CEPH_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.CEPH_SECRET_ACCESS_KEY,
                    config=ceph_config
                )
                logger.info(f"Initialized Ceph S3 client with endpoint: {settings.CEPH_ENDPOINT_URL}")
            else:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION,
                    config=STORAGE_TIMEOUT_CONFIG
                )
                logger.info("Initialized AWS S3 client")

        except Exception as e:
            logger.error(f"Failed to initialize storage service: {str(e)}")
            raise

    async def list_buckets(self) -> List[Dict[str, Any]]:
        try:
            response = await storage_circuit_breaker.call(
                self.s3_client.list_buckets
            )
            return [
                {
                    "name": bucket['Name'],
                    "creation_date": bucket['CreationDate'].isoformat()
                }
                for bucket in response['Buckets']
            ]
        except Exception as e:
            logger.error(f"Error listing buckets: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def list_objects_as_tree(self, bucket_name: str, prefix: str = "", depth: int = None) -> Dict[str, Any]:
        try:
            if prefix.startswith('/'):
                prefix = prefix[1:]

            def get_folder_info(key: str) -> Dict[str, Any]:
                return {
                    "name": key.rstrip('/').split('/')[-1],
                    "path": f"/{key}",
                    "type": "folder",
                    "size": 4096,
                    "modified": time.time(),
                    "children": []
                }
            
            def get_file_info(obj: Dict[str, Any]) -> Dict[str, Any]:
                key = obj['Key']
                return {
                    "name": key.split('/')[-1],
                    "path": f"/{key}",
                    "type": "file",
                    "size": obj['Size'],
                    "modified": obj['LastModified'].timestamp()
                }

            async def build_tree(prefix: str, current_depth: int) -> List[Dict[str, Any]]:
                if depth is not None and current_depth > depth:
                    return []

                result = []
                
                # Use circuit breaker for list_objects_v2 paginate operation with optimized page size
                paginator = self.s3_client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(
                    Bucket=bucket_name, 
                    Prefix=prefix, 
                    Delimiter='/',
                    PaginationConfig={'MaxItems': 1000, 'PageSize': 1000}  # Increase page size for fewer API calls
                )
                
                # Process pages sequentially
                for page in page_iterator:
                    # Process folders
                    folder_tasks = []
                    folder_infos = []
                    
                    for common_prefix in page.get('CommonPrefixes', []):
                        prefix_path = common_prefix.get('Prefix')
                        folder_info = get_folder_info(prefix_path)
                        folder_infos.append((folder_info, prefix_path))
                        
                        if depth is None or current_depth < depth:
                            # Recursively build children
                            folder_tasks.append(build_tree(prefix_path, current_depth + 1))
                    
                    # Execute folder children tasks concurrently
                    if folder_tasks:
                        children_results = await asyncio.gather(*folder_tasks, return_exceptions=True)
                        for (folder_info, _), children in zip(folder_infos, children_results):
                            if isinstance(children, Exception):
                                logger.error(f"Error building folder children: {children}")
                                folder_info['children'] = []
                            else:
                                folder_info['children'] = children
                            result.append(folder_info)
                    else:
                        # No children to build, just add folders
                        for folder_info, _ in folder_infos:
                            result.append(folder_info)
                    
                    # Process files - use data from list_objects_v2 directly (no additional API calls)
                    for obj in page.get('Contents', []):
                        if not obj['Key'].endswith('/'):  # Exclude folder markers
                            file_info = get_file_info(obj)
                            result.append(file_info)

                return result

            # Build the root tree structure
            children = await build_tree(prefix, 1)
            
            root_info = {
                "name": prefix.rstrip('/').split('/')[-1] if prefix else bucket_name,
                "path": f"/{prefix}" if prefix else "/",
                "type": "folder",
                "size": 4096,
                "modified": time.time(),
                "children": children
            }

            return root_info

        except ClientError as e:
            logger.error(f"Error listing objects: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def upload_file(self, bucket_name: str, file: UploadFile, prefix: str = "") -> Dict[str, Any]:
        upload_id = str(uuid.uuid4())
        
        try:
            # prefix가 /로 시작하면 제거
            if prefix.startswith('/'):
                prefix = prefix[1:]

            # 파일명 설정
            file_location = f"{prefix}/{file.filename}" if prefix else file.filename
            file_location = file_location.replace('//', '/')  # 중복 슬래시 제거

            logger.info(f"Uploading file to {bucket_name}/{file_location}, size: {file.size}")

            # Upload tracker 시작
            await upload_tracker.start_upload(
                upload_id=upload_id,
                filename=file.filename,
                total_size=file.size or 0,
                total_parts=1 if not file.size or file.size <= 100 * 1024 * 1024 else (file.size // (50 * 1024 * 1024)) + 1
            )

            # 큰 파일은 멀티파트 업로드 사용 (100MB 이상)
            if file.size and file.size > 100 * 1024 * 1024:  # 100MB
                file_url = await self._multipart_upload(bucket_name, file, file_location, upload_id)
            else:
                file_url = await self._simple_upload(bucket_name, file, file_location, upload_id)
            
            await upload_tracker.complete_upload(upload_id)
            
            return {
                "file_url": file_url,
                "upload_id": upload_id
            }

        except Exception as e:
            await upload_tracker.fail_upload(upload_id, str(e))
            logger.error(f"Error uploading file: {str(e)}")
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=str(e))

    async def _simple_upload(self, bucket_name: str, file: UploadFile, file_location: str, upload_id: str) -> str:
        """작은 파일용 단순 업로드"""
        loop = asyncio.get_event_loop()
        
        # 스트리밍 방식으로 파일 읽기
        file_content = await loop.run_in_executor(None, file.file.read)
        
        # 업로드 진행률 업데이트
        await upload_tracker.update_progress(upload_id, len(file_content), 1)
        
        # Circuit breaker를 통한 업로드
        await storage_circuit_breaker.call(
            lambda: self.s3_client.put_object(
                Bucket=bucket_name,
                Key=file_location,
                Body=file_content
            )
        )

        # URL 생성
        url = self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': file_location},
            ExpiresIn=3600
        )
        
        logger.info(f"File uploaded successfully: {file_location}")
        return url

    async def _multipart_upload(self, bucket_name: str, file: UploadFile, file_location: str, upload_id: str) -> str:
        """대용량 파일용 멀티파트 업로드"""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        CHUNK_SIZE = 50 * 1024 * 1024  # 50MB chunks
        
        try:
            # 멀티파트 업로드 시작
            response = await storage_circuit_breaker.call(
                lambda: self.s3_client.create_multipart_upload(
                    Bucket=bucket_name,
                    Key=file_location
                )
            )
            upload_id = response['UploadId']
            
            logger.info(f"Started multipart upload for {file_location}, upload_id: {upload_id}")
            
            parts = []
            part_number = 1
            uploaded_size = 0
            
            # 스트리밍 방식으로 청크 단위 업로드
            while True:
                chunk = await asyncio.get_event_loop().run_in_executor(
                    None, file.file.read, CHUNK_SIZE
                )
                
                if not chunk:
                    break
                
                logger.debug(f"Uploading part {part_number}, size: {len(chunk)}")
                
                # 각 파트 업로드
                s3_upload_id = response['UploadId']  # multipart upload의 upload_id
                part_response = await storage_circuit_breaker.call(
                    lambda: self.s3_client.upload_part(
                        Bucket=bucket_name,
                        Key=file_location,
                        PartNumber=part_number,
                        UploadId=s3_upload_id,
                        Body=chunk
                    )
                )
                
                parts.append({
                    'ETag': part_response['ETag'],
                    'PartNumber': part_number
                })
                
                # 진행률 업데이트
                uploaded_size += len(chunk)
                await upload_tracker.update_progress(upload_id, uploaded_size, part_number)
                
                part_number += 1
            
            # 멀티파트 업로드 완료
            await storage_circuit_breaker.call(
                lambda: self.s3_client.complete_multipart_upload(
                    Bucket=bucket_name,
                    Key=file_location,
                    UploadId=s3_upload_id,
                    MultipartUpload={'Parts': parts}
                )
            )
            
            # URL 생성
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': file_location},
                ExpiresIn=3600
            )
            
            logger.info(f"Multipart upload completed: {file_location}, parts: {len(parts)}")
            return url
            
        except Exception as e:
            # 실패 시 멀티파트 업로드 중단
            try:
                await storage_circuit_breaker.call(
                    lambda: self.s3_client.abort_multipart_upload(
                        Bucket=bucket_name,
                        Key=file_location,
                        UploadId=s3_upload_id
                    )
                )
                logger.info(f"Aborted multipart upload: {s3_upload_id}")
            except:
                pass
            raise

    async def download_file(self, bucket_name: str, file_key: str) -> bytes:
        try:
            logger.info(f"Downloading file: {bucket_name}/{file_key}")

            # 파일 존재 여부 확인
            try:
                await storage_circuit_breaker.call(
                    lambda: self.s3_client.head_object(Bucket=bucket_name, Key=file_key)
                )
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    raise HTTPException(
                        status_code=404,
                        detail=f"File '{file_key}' not found in bucket '{bucket_name}'"
                    )
                raise

            # 파일 다운로드
            response = await storage_circuit_breaker.call(
                lambda: self.s3_client.get_object(Bucket=bucket_name, Key=file_key)
            )

            # 파일 내용 읽기
            file_content = response['Body'].read()

            logger.info(f"File downloaded successfully: {file_key}")
            return file_content

        except ClientError as e:
            logger.error(f"Error downloading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error downloading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def rename_file(self, bucket_name: str, old_key: str, new_key: str) -> None:
        try:
            # Copy object to new key
            await storage_circuit_breaker.call(
                lambda: self.s3_client.copy_object(
                    Bucket=bucket_name,
                    CopySource={'Bucket': bucket_name, 'Key': old_key},
                    Key=new_key
                )
            )
            # Delete old object
            await storage_circuit_breaker.call(
                lambda: self.s3_client.delete_object(
                    Bucket=bucket_name,
                    Key=old_key
                )
            )
        except ClientError as e:
            logger.error(f"Error renaming file: {str(e)}")
            raise

    async def delete_file(self, bucket_name: str, file_key: str) -> None:
        try:
            await storage_circuit_breaker.call(
                lambda: self.s3_client.delete_object(
                    Bucket=bucket_name,
                    Key=file_key
                )
            )
        except ClientError as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise

    async def create_bucket(self, bucket_name: str) -> bool:
        try:
            logger.info(f"Creating bucket: {bucket_name}")
            await storage_circuit_breaker.call(
                lambda: self.s3_client.create_bucket(Bucket=bucket_name)
            )
            return True
        except ClientError as e:
            logger.error(f"Error creating bucket: {str(e)}")
            error_code = e.response['Error']['Code']
            if error_code == 'BucketAlreadyExists':
                raise HTTPException(
                    status_code=400,
                    detail=f"Bucket '{bucket_name}' already exists"
                )
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error creating bucket: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_bucket(self, bucket_name: str) -> bool:
        try:
            logger.info(f"Deleting bucket: {bucket_name}")

            # 버킷 존재 여부 확인
            try:
                await storage_circuit_breaker.call(
                    lambda: self.s3_client.head_bucket(Bucket=bucket_name)
                )
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    raise HTTPException(
                        status_code=404,
                        detail=f"Bucket '{bucket_name}' not found"
                    )
                raise

            # 버킷 내 모든 객체 삭제
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket_name):
                if 'Contents' in page:
                    objects = [{'Key': obj['Key']} for obj in page['Contents']]
                    await storage_circuit_breaker.call(
                        lambda: self.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': objects}
                        )
                    )

            # 버킷 삭제
            await storage_circuit_breaker.call(
                lambda: self.s3_client.delete_bucket(Bucket=bucket_name)
            )
            return True

        except ClientError as e:
            logger.error(f"Error deleting bucket: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error deleting bucket: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
