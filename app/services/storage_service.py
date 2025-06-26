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

    async def get_bucket_details(self, bucket_name: str) -> Dict[str, Any]:
        try:
            # Check if bucket exists and get creation date
            try:
                head_response = await storage_circuit_breaker.call(
                    lambda: self.s3_client.head_bucket(Bucket=bucket_name)
                )
                creation_date = head_response['ResponseMetadata']['HTTPHeaders']['last-modified']
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' not found")
                raise

            # Get object count and total size
            object_count = 0
            total_size = 0
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name)
            for page in page_iterator:
                if 'Contents' in page:
                    object_count += len(page['Contents'])
                    total_size += sum(obj['Size'] for obj in page['Contents'])

            return {
                "name": bucket_name,
                "creation_date": creation_date,
                "object_count": object_count,
                "size": total_size
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting bucket details for {bucket_name}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def list_objects_as_tree(self, bucket_name: str, prefix: str = "", depth: int = None) -> Dict[str, Any]:
        try:
            if prefix.startswith('/'):
                prefix = prefix[1:]

            def get_folder_info(key: str) -> Dict[str, Any]:
                # Ensure path is relative and without leading/trailing slashes
                clean_key = key.strip('/')
                return {
                    "name": clean_key.split('/')[-1],
                    "path": clean_key, # Path without leading/trailing slash
                    "type": "folder",
                    "size": 4096,
                    "modified": time.time(),
                    "children": []
                }
            
            def get_file_info(obj: Dict[str, Any]) -> Dict[str, Any]:
                # Ensure path is relative and without leading/trailing slashes
                clean_key = obj['Key'].strip('/')
                return {
                    "name": clean_key.split('/')[-1],
                    "path": clean_key, # Path without leading/trailing slash
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
                "path": prefix.rstrip('/'), # Path without leading/trailing slash
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
        s3_upload_id = None
        
        try:
            # 멀티파트 업로드 시작
            response = await storage_circuit_breaker.call(
                lambda: self.s3_client.create_multipart_upload(
                    Bucket=bucket_name,
                    Key=file_location
                )
            )
            s3_upload_id = response['UploadId']
            
            logger.info(f"Started multipart upload for {file_location}, upload_id: {s3_upload_id}")
            
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
            if s3_upload_id:
                try:
                    await storage_circuit_breaker.call(
                        lambda: self.s3_client.abort_multipart_upload(
                            Bucket=bucket_name,
                            Key=file_location,
                            UploadId=s3_upload_id
                        )
                    )
                    logger.info(f"Aborted multipart upload: {s3_upload_id}")
                except Exception as abort_e:
                    logger.error(f"Failed to abort multipart upload {s3_upload_id}: {abort_e}")
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

    async def create_folder(self, bucket_name: str, folder_path: str) -> None:
        """Creates a folder in S3 by creating a zero-byte object with a trailing slash."""
        if not folder_path.endswith('/'):
            folder_path += '/'
        
        loop = asyncio.get_event_loop()
        try:
            logger.info(f"Creating folder: {bucket_name}/{folder_path}")
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.put_object(Bucket=bucket_name, Key=folder_path, Body=b'')
            )
        except ClientError as e:
            logger.error(f"Error creating folder '{folder_path}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not create folder: {str(e)}")

    async def delete_folder(self, bucket_name: str, folder_path: str) -> None:
        """Delete a folder and all its contents recursively."""
        try:
            if not folder_path.endswith('/'):
                folder_path += '/'
            
            logger.info(f"Deleting folder: {bucket_name}/{folder_path}")
            
            # Get all objects with this prefix
            objects_to_delete = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=folder_path)
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            # Delete objects in batches (S3 limit is 1000 per batch)
            batch_size = 1000
            for i in range(0, len(objects_to_delete), batch_size):
                batch = objects_to_delete[i:i + batch_size]
                if batch:
                    await storage_circuit_breaker.call(
                        lambda: self.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': batch}
                        )
                    )
            
            logger.info(f"Deleted folder {folder_path} with {len(objects_to_delete)} objects")
            
        except ClientError as e:
            logger.error(f"Error deleting folder '{folder_path}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not delete folder: {str(e)}")

    async def rename_folder(self, bucket_name: str, old_path: str, new_path: str) -> None:
        """Rename a folder by copying all objects to new prefix and deleting old ones."""
        try:
            if not old_path.endswith('/'):
                old_path += '/'
            if not new_path.endswith('/'):
                new_path += '/'
            
            logger.info(f"Renaming folder: {bucket_name}/{old_path} -> {new_path}")
            
            # Get all objects with old prefix
            objects_to_copy = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=old_path)
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        old_key = obj['Key']
                        new_key = new_path + old_key[len(old_path):]
                        objects_to_copy.append((old_key, new_key))
            
            # Copy objects to new location
            for old_key, new_key in objects_to_copy:
                await storage_circuit_breaker.call(
                    lambda: self.s3_client.copy_object(
                        Bucket=bucket_name,
                        CopySource={'Bucket': bucket_name, 'Key': old_key},
                        Key=new_key
                    )
                )
            
            # Delete old objects
            objects_to_delete = [{'Key': old_key} for old_key, _ in objects_to_copy]
            if objects_to_delete:
                batch_size = 1000
                for i in range(0, len(objects_to_delete), batch_size):
                    batch = objects_to_delete[i:i + batch_size]
                    await storage_circuit_breaker.call(
                        lambda: self.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': batch}
                        )
                    )
            
            logger.info(f"Renamed folder {old_path} to {new_path} ({len(objects_to_copy)} objects)")
            
        except ClientError as e:
            logger.error(f"Error renaming folder '{old_path}' to '{new_path}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not rename folder: {str(e)}")

    async def copy_folder(self, bucket_name: str, source_path: str, dest_path: str) -> None:
        """Copy a folder and all its contents to a new location."""
        try:
            if not source_path.endswith('/'):
                source_path += '/'
            if not dest_path.endswith('/'):
                dest_path += '/'
            
            logger.info(f"Copying folder: {bucket_name}/{source_path} -> {dest_path}")
            
            # Get all objects with source prefix
            objects_to_copy = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=source_path)
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        source_key = obj['Key']
                        dest_key = dest_path + source_key[len(source_path):]
                        objects_to_copy.append((source_key, dest_key))
            
            # Copy objects to destination
            for source_key, dest_key in objects_to_copy:
                await storage_circuit_breaker.call(
                    lambda: self.s3_client.copy_object(
                        Bucket=bucket_name,
                        CopySource={'Bucket': bucket_name, 'Key': source_key},
                        Key=dest_key
                    )
                )
            
            logger.info(f"Copied folder {source_path} to {dest_path} ({len(objects_to_copy)} objects)")
            
        except ClientError as e:
            logger.error(f"Error copying folder '{source_path}' to '{dest_path}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not copy folder: {str(e)}")

    async def copy_file(self, bucket_name: str, source_key: str, dest_key: str, dest_bucket: str = None) -> None:
        """Copy a file to a new location."""
        try:
            if dest_bucket is None:
                dest_bucket = bucket_name
                
            logger.info(f"Copying file: {bucket_name}/{source_key} -> {dest_bucket}/{dest_key}")
            
            await storage_circuit_breaker.call(
                lambda: self.s3_client.copy_object(
                    Bucket=dest_bucket,
                    CopySource={'Bucket': bucket_name, 'Key': source_key},
                    Key=dest_key
                )
            )
            
            logger.info(f"Copied file {source_key} to {dest_key}")
            
        except ClientError as e:
            logger.error(f"Error copying file '{source_key}' to '{dest_key}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not copy file: {str(e)}")

    async def get_folder_stats(self, bucket_name: str, folder_path: str) -> Dict[str, Any]:
        """Get statistics for a folder."""
        try:
            if not folder_path.endswith('/'):
                folder_path += '/'
            
            total_size = 0
            file_count = 0
            folder_count = 0
            
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=folder_path)
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if obj['Key'].endswith('/'):
                            folder_count += 1
                        else:
                            file_count += 1
                            total_size += obj['Size']
            
            return {
                "path": folder_path.rstrip('/'),
                "total_size": total_size,
                "file_count": file_count,
                "folder_count": folder_count
            }
            
        except ClientError as e:
            logger.error(f"Error getting folder stats for '{folder_path}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not get folder stats: {str(e)}")

    async def create_bucket(self, bucket_name: str) -> bool:
        try:
            # Validate bucket name
            if not bucket_name or not bucket_name.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Bucket name cannot be empty or None"
                )
            
            bucket_name = bucket_name.strip()
            
            # 1. Check if bucket already exists
            try:
                await storage_circuit_breaker.call(
                    lambda: self.s3_client.head_bucket(Bucket=bucket_name)
                )
                # If head_bucket succeeds, the bucket exists.
                raise HTTPException(
                    status_code=409, # 409 Conflict is more appropriate for existing resources
                    detail=f"Bucket '{bucket_name}' already exists."
                )
            except ClientError as e:
                # A 404 Not Found error means the bucket does not exist, which is what we want.
                if e.response['Error']['Code'] != '404':
                    # For other errors (e.g., permissions), re-raise the exception.
                    logger.error(f"Error checking bucket existence: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Error checking bucket: {str(e)}")
            
            # 2. If it does not exist, create it
            logger.info(f"Creating bucket: {bucket_name}")
            await storage_circuit_breaker.call(
                lambda: self.s3_client.create_bucket(Bucket=bucket_name)
            )
            return True
        except HTTPException as e:
            # Re-raise HTTPExceptions directly (like the 409 Conflict from the check)
            raise e
        except Exception as e:
            logger.error(f"Unexpected error creating bucket: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_bucket(self, bucket_name: str) -> bool:
        try:
            logger.info(f"Deleting bucket: {bucket_name}")

            # Circuit breaker 없이 직접 호출하여 동기화 문제 해결
            loop = asyncio.get_event_loop()
            
            # 버킷 존재 여부 확인
            try:
                await loop.run_in_executor(
                    None, 
                    lambda: self.s3_client.head_bucket(Bucket=bucket_name)
                )
                logger.info(f"Bucket {bucket_name} exists, proceeding with deletion")
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code in ['404', 'NoSuchBucket']:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Bucket '{bucket_name}' not found"
                    )
                logger.error(f"Error checking bucket existence: {str(e)}")
                raise

            # 버킷 내 모든 객체 삭제
            try:
                logger.info(f"Listing objects in bucket {bucket_name}")
                response = await loop.run_in_executor(
                    None,
                    lambda: self.s3_client.list_objects_v2(Bucket=bucket_name)
                )
                
                # 객체가 있으면 삭제
                if 'Contents' in response and response['Contents']:
                    objects = [{'Key': obj['Key']} for obj in response['Contents']]
                    logger.info(f"Found {len(objects)} objects to delete from bucket {bucket_name}")
                    
                    # 객체 일괄 삭제
                    await loop.run_in_executor(
                        None,
                        lambda: self.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': objects}
                        )
                    )
                    logger.info(f"Deleted {len(objects)} objects from bucket {bucket_name}")
                    
                    # 객체가 많은 경우 페이지네이션으로 계속 삭제
                    while response.get('IsTruncated', False):
                        logger.info(f"Continuing pagination for bucket {bucket_name}")
                        response = await loop.run_in_executor(
                            None,
                            lambda: self.s3_client.list_objects_v2(
                                Bucket=bucket_name,
                                ContinuationToken=response['NextContinuationToken']
                            )
                        )
                        if 'Contents' in response and response['Contents']:
                            objects = [{'Key': obj['Key']} for obj in response['Contents']]
                            await loop.run_in_executor(
                                None,
                                lambda: self.s3_client.delete_objects(
                                    Bucket=bucket_name,
                                    Delete={'Objects': objects}
                                )
                            )
                            logger.info(f"Deleted additional {len(objects)} objects from bucket {bucket_name}")
                else:
                    logger.info(f"Bucket {bucket_name} is empty, no objects to delete")
                    
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NoSuchBucket':
                    logger.warning(f"Bucket {bucket_name} disappeared during object deletion")
                    raise HTTPException(
                        status_code=404,
                        detail=f"Bucket '{bucket_name}' not found"
                    )
                else:
                    logger.error(f"Error listing/deleting objects in bucket {bucket_name}: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Error deleting objects: {str(e)}")

            # 버킷 삭제
            logger.info(f"Deleting empty bucket {bucket_name}")
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.delete_bucket(Bucket=bucket_name)
            )
            logger.info(f"Successfully deleted bucket {bucket_name}")
            return True

        except HTTPException:
            # HTTPException은 그대로 재발생
            raise
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 ClientError deleting bucket {bucket_name}: {error_code} - {str(e)}")
            if error_code == 'NoSuchBucket':
                raise HTTPException(
                    status_code=404,
                    detail=f"Bucket '{bucket_name}' not found"
                )
            elif error_code == 'BucketNotEmpty':
                raise HTTPException(
                    status_code=400,
                    detail=f"Bucket '{bucket_name}' is not empty. Please try again."
                )
            else:
                raise HTTPException(status_code=500, detail=f"S3 Error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error deleting bucket {bucket_name}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
