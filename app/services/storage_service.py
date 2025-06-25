import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from typing import List, Optional, Dict, Any
from fastapi import UploadFile, HTTPException
import time
from app.core.config import settings
from app.core.logging import logger

class StorageService:
    def __init__(self):
        try:
            if settings.STORAGE_TYPE == 'ceph':
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=settings.CEPH_ENDPOINT_URL,
                    aws_access_key_id=settings.CEPH_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.CEPH_SECRET_ACCESS_KEY,
                    config=Config(signature_version='s3v4')
                )
                logger.info(f"Initialized Ceph S3 client with endpoint: {settings.CEPH_ENDPOINT_URL}")
            else:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION
                )
                logger.info("Initialized AWS S3 client")

        except Exception as e:
            logger.error(f"Failed to initialize storage service: {str(e)}")
            raise

    def list_buckets(self) -> List[Dict[str, Any]]:
        try:
            response = self.s3_client.list_buckets()
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

    def list_objects_as_tree(self, bucket_name: str, prefix: str = "", depth: int = None) -> Dict[str, Any]:
        try:
            if prefix.startswith('/'):
                prefix = prefix[1:]

            def get_object_info(key: str, is_prefix: bool = False) -> Dict[str, Any]:
                try:
                    if is_prefix:
                        return {
                            "name": key.rstrip('/').split('/')[-1],
                            "path": f"/{key}",
                            "type": "folder",
                            "size": 4096,  # 폴더 기본 크기
                            "modified": time.time(),  # 현재 시간을 기본값으로
                            "children": []
                        }
                    else:
                        obj = self.s3_client.head_object(Bucket=bucket_name, Key=key)
                        return {
                            "name": key.split('/')[-1],
                            "path": f"/{key}",
                            "type": "file",
                            "size": obj['ContentLength'],
                            "modified": obj['LastModified'].timestamp()
                        }
                except Exception as e:
                    logger.error(f"Error getting object info for {key}: {str(e)}")
                    return None

            def build_tree(prefix: str, current_depth: int) -> List[Dict[str, Any]]:
                if depth is not None and current_depth > depth:
                    return []

                result = []
                paginator = self.s3_client.get_paginator('list_objects_v2')

                for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix, Delimiter='/'):
                    # 처리 폴더
                    for common_prefix in page.get('CommonPrefixes', []):
                        prefix_path = common_prefix.get('Prefix')
                        folder_info = get_object_info(prefix_path, True)
                        if folder_info:
                            if depth is None or current_depth < depth:
                                folder_info['children'] = build_tree(prefix_path, current_depth + 1)
                            else:
                                # depth 제한에 도달했을 때 has_children 확인
                                try:
                                    next_level = self.s3_client.list_objects_v2(
                                        Bucket=bucket_name,
                                        Prefix=prefix_path,
                                        MaxKeys=1
                                    )
                                    folder_info['has_children'] = 'Contents' in next_level
                                except:
                                    folder_info['has_children'] = False
                            result.append(folder_info)

                    # 처리 파일
                    for obj in page.get('Contents', []):
                        key = obj['Key']
                        if not key.endswith('/'):  # 폴더 마커 제외
                            file_info = get_object_info(key)
                            if file_info:
                                result.append(file_info)

                return result

            root_info = {
                "name": prefix.rstrip('/').split('/')[-1] if prefix else bucket_name,
                "path": f"/{prefix}" if prefix else "/",
                "type": "folder",
                "size": 4096,
                "modified": time.time(),
                "children": build_tree(prefix, 1)
            }

            return root_info

        except ClientError as e:
            logger.error(f"Error listing objects: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def upload_file(self, bucket_name: str, file: UploadFile, prefix: str = "") -> str:
        try:
            # prefix가 /로 시작하면 제거
            if prefix.startswith('/'):
                prefix = prefix[1:]

            # 파일명 설정
            file_location = f"{prefix}/{file.filename}" if prefix else file.filename
            file_location = file_location.replace('//', '/')  # 중복 슬래시 제거

            logger.info(f"Uploading file to {bucket_name}/{file_location}")

            # 파일 업로드
            file_content = file.file.read()
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=file_location,
                Body=file_content
            )

            # 업로드된 파일의 URL 생성
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': file_location
                },
                ExpiresIn=3600  # URL 만료 시간 (초)
            )

            logger.info(f"File uploaded successfully: {file_location}")
            return url

        except ClientError as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def download_file(self, bucket_name: str, file_key: str) -> bytes:
        try:
            logger.info(f"Downloading file: {bucket_name}/{file_key}")

            # 파일 존재 여부 확인
            try:
                self.s3_client.head_object(Bucket=bucket_name, Key=file_key)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    raise HTTPException(
                        status_code=404,
                        detail=f"File '{file_key}' not found in bucket '{bucket_name}'"
                    )
                raise

            # 파일 다운로드
            response = self.s3_client.get_object(
                Bucket=bucket_name,
                Key=file_key
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

    def rename_file(self, bucket_name: str, old_key: str, new_key: str) -> None:
        try:
            # Copy object to new key
            self.s3_client.copy_object(
                Bucket=bucket_name,
                CopySource={'Bucket': bucket_name, 'Key': old_key},
                Key=new_key
            )
            # Delete old object
            self.s3_client.delete_object(
                Bucket=bucket_name,
                Key=old_key
            )
        except ClientError as e:
            logger.error(f"Error renaming file: {str(e)}")
            raise

    def delete_file(self, bucket_name: str, file_key: str) -> None:
        try:
            self.s3_client.delete_object(
                Bucket=bucket_name,
                Key=file_key
            )
        except ClientError as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise

    def create_bucket(self, bucket_name: str) -> bool:
        try:
            logger.info(f"Creating bucket: {bucket_name}")
            self.s3_client.create_bucket(Bucket=bucket_name)
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

    def delete_bucket(self, bucket_name: str) -> bool:
        try:
            logger.info(f"Deleting bucket: {bucket_name}")

            # 버킷 존재 여부 확인
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
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
                    self.s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': objects}
                    )

            # 버킷 삭제
            self.s3_client.delete_bucket(Bucket=bucket_name)
            return True

        except ClientError as e:
            logger.error(f"Error deleting bucket: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error deleting bucket: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
