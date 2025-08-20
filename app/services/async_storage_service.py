import aiofiles
from aiobotocore.session import get_session
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError
from typing import List, Optional, Dict, Any, AsyncContextManager
from fastapi import UploadFile, HTTPException
import time
import asyncio
from app.core.config import settings
from app.core.logging import logger
from app.utils.circuit_breaker import storage_circuit_breaker
from app.services.upload_tracker import upload_tracker
import uuid

# Configure timeouts for async storage operations
ASYNC_STORAGE_CONFIG = AioConfig(
    read_timeout=60,
    connect_timeout=10,
    retries={'max_attempts': 3, 'mode': 'adaptive'},
    max_pool_connections=50,
    region_name=settings.AWS_REGION or 'us-east-1'
)

class AsyncStorageService:
    def __init__(self):
        self.session = get_session()
        self.s3_client = None
        self._client_context = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        try:
            if settings.STORAGE_TYPE == 'ceph':
                ceph_config = AioConfig(
                    signature_version='s3v4',
                    read_timeout=ASYNC_STORAGE_CONFIG.read_timeout,
                    connect_timeout=ASYNC_STORAGE_CONFIG.connect_timeout,
                    retries=ASYNC_STORAGE_CONFIG.retries,
                    max_pool_connections=ASYNC_STORAGE_CONFIG.max_pool_connections
                )
                self._client_context = self.session.create_client(
                    's3',
                    endpoint_url=settings.CEPH_ENDPOINT_URL,
                    aws_access_key_id=settings.CEPH_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.CEPH_SECRET_ACCESS_KEY,
                    config=ceph_config
                )
                logger.info(f"Initialized async Ceph S3 client with endpoint: {settings.CEPH_ENDPOINT_URL}")
            else:
                self._client_context = self.session.create_client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION,
                    config=ASYNC_STORAGE_CONFIG
                )
                logger.info("Initialized async AWS S3 client")
            
            self.s3_client = await self._client_context.__aenter__()
            return self
        except Exception as e:
            logger.error(f"Failed to initialize async storage service: {str(e)}")
            raise
            
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client_context:
            await self._client_context.__aexit__(exc_type, exc_val, exc_tb)
            self.s3_client = None
            self._client_context = None

    async def list_buckets(self) -> List[Dict[str, Any]]:
        """List all buckets asynchronously"""
        try:
            response = await self.s3_client.list_buckets()
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
        """Get bucket details asynchronously"""
        try:
            # Check if bucket exists
            try:
                head_response = await self.s3_client.head_bucket(Bucket=bucket_name)
                creation_date = head_response['ResponseMetadata']['HTTPHeaders'].get('last-modified', '')
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    raise HTTPException(status_code=404, detail=f"Bucket '{bucket_name}' not found")
                raise

            # Get object count and total size with async pagination
            object_count = 0
            total_size = 0
            
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name)
            async for page in page_iterator:
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
        """Build object tree structure asynchronously"""
        try:
            if prefix.startswith('/'):
                prefix = prefix[1:]

            def get_folder_info(key: str) -> Dict[str, Any]:
                clean_key = key.strip('/')
                return {
                    "name": clean_key.split('/')[-1],
                    "path": clean_key,
                    "type": "folder",
                    "size": 4096,
                    "modified": time.time(),
                    "children": []
                }
            
            def get_file_info(obj: Dict[str, Any]) -> Dict[str, Any]:
                clean_key = obj['Key'].strip('/')
                return {
                    "name": clean_key.split('/')[-1],
                    "path": clean_key,
                    "type": "file",
                    "size": obj['Size'],
                    "modified": obj['LastModified'].timestamp()
                }

            async def build_tree(prefix: str, current_depth: int) -> List[Dict[str, Any]]:
                if depth is not None and current_depth > depth:
                    return []

                result = []
                
                # Use async pagination for better performance
                paginator = self.s3_client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(
                    Bucket=bucket_name, 
                    Prefix=prefix, 
                    Delimiter='/',
                    PaginationConfig={'MaxItems': 1000, 'PageSize': 1000}
                )
                folder_tasks = []
                folder_infos = []
                
                async for page in page_iterator:
                    # Process folders
                    for common_prefix in page.get('CommonPrefixes', []):
                        prefix_path = common_prefix.get('Prefix')
                        folder_info = get_folder_info(prefix_path)
                        folder_infos.append((folder_info, prefix_path))
                        
                        if depth is None or current_depth < depth:
                            folder_tasks.append(build_tree(prefix_path, current_depth + 1))
                    
                    # Process files
                    for obj in page.get('Contents', []):
                        if not obj['Key'].endswith('/'):
                            file_info = get_file_info(obj)
                            result.append(file_info)
                
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
                    for folder_info, _ in folder_infos:
                        result.append(folder_info)

                return result

            children = await build_tree(prefix, 1)
            
            root_info = {
                "name": prefix.rstrip('/').split('/')[-1] if prefix else bucket_name,
                "path": prefix.rstrip('/'),
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
        """Upload file asynchronously"""
        upload_id = str(uuid.uuid4())
        
        try:
            if prefix.startswith('/'):
                prefix = prefix[1:]

            file_location = f"{prefix}/{file.filename}" if prefix else file.filename
            file_location = file_location.replace('//', '/')

            logger.info(f"Uploading file to {bucket_name}/{file_location}, size: {file.size}")

            await upload_tracker.start_upload(
                upload_id=upload_id,
                filename=file.filename,
                total_size=file.size or 0,
                total_parts=1 if not file.size or file.size <= 100 * 1024 * 1024 else (file.size // (50 * 1024 * 1024)) + 1
            )

            # Use multipart upload for large files
            if file.size and file.size > 100 * 1024 * 1024:  # 100MB
                file_url = await self._async_multipart_upload(bucket_name, file, file_location, upload_id)
            else:
                file_url = await self._async_simple_upload(bucket_name, file, file_location, upload_id)
            
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

    async def _async_simple_upload(self, bucket_name: str, file: UploadFile, file_location: str, upload_id: str) -> str:
        """Simple async upload for small files"""
        file_content = await file.read()
        
        await upload_tracker.update_progress(upload_id, len(file_content), 1)
        
        await self.s3_client.put_object(
            Bucket=bucket_name,
            Key=file_location,
            Body=file_content
        )

        url = await self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': file_location},
            ExpiresIn=3600
        )
        
        logger.info(f"File uploaded successfully: {file_location}")
        return url

    async def _async_multipart_upload(self, bucket_name: str, file: UploadFile, file_location: str, upload_id: str) -> str:
        """Async multipart upload for large files"""
        CHUNK_SIZE = 50 * 1024 * 1024  # 50MB chunks
        s3_upload_id = None
        
        try:
            # Start multipart upload
            response = await self.s3_client.create_multipart_upload(
                Bucket=bucket_name,
                Key=file_location
            )
            s3_upload_id = response['UploadId']
            
            logger.info(f"Started multipart upload for {file_location}, upload_id: {s3_upload_id}")
            
            parts = []
            part_number = 1
            uploaded_size = 0
            
            # Stream upload in chunks
            while True:
                chunk = await file.read(CHUNK_SIZE)
                
                if not chunk:
                    break
                
                logger.debug(f"Uploading part {part_number}, size: {len(chunk)}")
                
                part_response = await self.s3_client.upload_part(
                    Bucket=bucket_name,
                    Key=file_location,
                    PartNumber=part_number,
                    UploadId=s3_upload_id,
                    Body=chunk
                )
                
                parts.append({
                    'ETag': part_response['ETag'],
                    'PartNumber': part_number
                })
                
                uploaded_size += len(chunk)
                await upload_tracker.update_progress(upload_id, uploaded_size, part_number)
                
                part_number += 1
            
            # Complete multipart upload
            await self.s3_client.complete_multipart_upload(
                Bucket=bucket_name,
                Key=file_location,
                UploadId=s3_upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            url = await self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': file_location},
                ExpiresIn=3600
            )
            
            logger.info(f"Multipart upload completed: {file_location}, parts: {len(parts)}")
            return url
            
        except Exception as e:
            if s3_upload_id:
                try:
                    await self.s3_client.abort_multipart_upload(
                        Bucket=bucket_name,
                        Key=file_location,
                        UploadId=s3_upload_id
                    )
                    logger.info(f"Aborted multipart upload: {s3_upload_id}")
                except Exception as abort_e:
                    logger.error(f"Failed to abort multipart upload {s3_upload_id}: {abort_e}")
            raise

    async def download_file(self, bucket_name: str, file_key: str) -> bytes:
        """Download file asynchronously"""
        try:
            logger.info(f"Downloading file: {bucket_name}/{file_key}")

            # Check if file exists
            try:
                await self.s3_client.head_object(Bucket=bucket_name, Key=file_key)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    raise HTTPException(
                        status_code=404,
                        detail=f"File '{file_key}' not found in bucket '{bucket_name}'"
                    )
                raise

            # Download file
            response = await self.s3_client.get_object(Bucket=bucket_name, Key=file_key)

            # Read file content asynchronously
            async with response['Body'] as stream:
                file_content = await stream.read()

            logger.info(f"File downloaded successfully: {file_key}")
            return file_content

        except ClientError as e:
            logger.error(f"Error downloading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error downloading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_file(self, bucket_name: str, file_key: str) -> None:
        """Delete file asynchronously"""
        try:
            await self.s3_client.delete_object(
                Bucket=bucket_name,
                Key=file_key
            )
        except ClientError as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise

    async def create_folder(self, bucket_name: str, folder_path: str) -> None:
        """Creates a folder in S3 by creating a zero-byte object with a trailing slash."""
        try:
            if not folder_path.endswith('/'):
                folder_path += '/'
            
            logger.info(f"Creating folder: {bucket_name}/{folder_path}")
            await self.s3_client.put_object(
                Bucket=bucket_name,
                Key=folder_path,
                Body=b''
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
            
            async for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            # Delete objects in batches (S3 limit is 1000 per batch)
            batch_size = 1000
            for i in range(0, len(objects_to_delete), batch_size):
                batch = objects_to_delete[i:i + batch_size]
                if batch:
                    await self.s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': batch}
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
            
            async for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        old_key = obj['Key']
                        new_key = new_path + old_key[len(old_path):]
                        objects_to_copy.append((old_key, new_key))
            
            # Copy objects to new location
            for old_key, new_key in objects_to_copy:
                await self.s3_client.copy_object(
                    Bucket=bucket_name,
                    CopySource={'Bucket': bucket_name, 'Key': old_key},
                    Key=new_key
                )
            
            # Delete old objects
            objects_to_delete = [{'Key': old_key} for old_key, _ in objects_to_copy]
            if objects_to_delete:
                batch_size = 1000
                for i in range(0, len(objects_to_delete), batch_size):
                    batch = objects_to_delete[i:i + batch_size]
                    await self.s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': batch}
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
            
            async for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        source_key = obj['Key']
                        dest_key = dest_path + source_key[len(source_path):]
                        objects_to_copy.append((source_key, dest_key))
            
            # Copy objects to destination
            for source_key, dest_key in objects_to_copy:
                await self.s3_client.copy_object(
                    Bucket=bucket_name,
                    CopySource={'Bucket': bucket_name, 'Key': source_key},
                    Key=dest_key
                )
            
            logger.info(f"Copied folder {source_path} to {dest_path} ({len(objects_to_copy)} objects)")
            
        except ClientError as e:
            logger.error(f"Error copying folder '{source_path}' to '{dest_path}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not copy folder: {str(e)}")

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
            
            async for page in page_iterator:
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

    async def rename_file(self, bucket_name: str, old_key: str, new_key: str) -> None:
        """Rename a file by copying to new key and deleting old one."""
        try:
            # Copy object to new key
            await self.s3_client.copy_object(
                Bucket=bucket_name,
                CopySource={'Bucket': bucket_name, 'Key': old_key},
                Key=new_key
            )
            # Delete old object
            await self.s3_client.delete_object(
                Bucket=bucket_name,
                Key=old_key
            )
        except ClientError as e:
            logger.error(f"Error renaming file: {str(e)}")
            raise

    async def copy_file(self, bucket_name: str, source_key: str, dest_key: str, dest_bucket: str = None) -> None:
        """Copy a file to a new location."""
        try:
            if dest_bucket is None:
                dest_bucket = bucket_name
                
            logger.info(f"Copying file: {bucket_name}/{source_key} -> {dest_bucket}/{dest_key}")
            
            await self.s3_client.copy_object(
                Bucket=dest_bucket,
                CopySource={'Bucket': bucket_name, 'Key': source_key},
                Key=dest_key
            )
            
            logger.info(f"Copied file {source_key} to {dest_key}")
            
        except ClientError as e:
            logger.error(f"Error copying file '{source_key}' to '{dest_key}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Could not copy file: {str(e)}")

    async def create_bucket(self, bucket_name: str) -> bool:
        """Create bucket asynchronously"""
        try:
            if not bucket_name or not bucket_name.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Bucket name cannot be empty or None"
                )
            
            bucket_name = bucket_name.strip()
            
            # Check if bucket already exists
            try:
                await self.s3_client.head_bucket(Bucket=bucket_name)
                raise HTTPException(
                    status_code=409,
                    detail=f"Bucket '{bucket_name}' already exists."
                )
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    logger.error(f"Error checking bucket existence: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Error checking bucket: {str(e)}")
            
            # Create bucket
            logger.info(f"Creating bucket: {bucket_name}")
            await self.s3_client.create_bucket(Bucket=bucket_name)
            return True
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating bucket: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_bucket(self, bucket_name: str) -> bool:
        """Delete bucket asynchronously"""
        try:
            logger.info(f"Deleting bucket: {bucket_name}")
            
            # Check if bucket exists
            try:
                await self.s3_client.head_bucket(Bucket=bucket_name)
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

            # Delete all objects in bucket
            try:
                logger.info(f"Listing objects in bucket {bucket_name}")
                paginator = self.s3_client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(Bucket=bucket_name)
                
                async for page in page_iterator:
                    if 'Contents' in page and page['Contents']:
                        objects = [{'Key': obj['Key']} for obj in page['Contents']]
                        logger.info(f"Found {len(objects)} objects to delete from bucket {bucket_name}")
                        
                        # Delete objects in batches
                        await self.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': objects}
                        )
                        logger.info(f"Deleted {len(objects)} objects from bucket {bucket_name}")
                        
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

            # Delete bucket
            logger.info(f"Deleting empty bucket {bucket_name}")
            await self.s3_client.delete_bucket(Bucket=bucket_name)
            logger.info(f"Successfully deleted bucket {bucket_name}")
            return True

        except HTTPException:
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

# Global async storage service instance
async_storage_service = AsyncStorageService()