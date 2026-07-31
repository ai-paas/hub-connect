from typing import Optional, List

from pydantic import field_validator, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    HF_API_TOKEN: str
    ALLOWED_ORIGINS: List[str] = ["*"]
    CACHE_TIMEOUT: int = 3600
    CACHE_REFRESH_INTERVAL: int = 3600  # Background cache refresh interval (seconds)
    GROUPS: List[str] = ["region", "other", "library", "license", "language", "dataset", "pipeline_tag", "deploy"]
    LIMITED_GROUPS: List[str] = ["language", "dataset"]
    LIMIT: int = 100

    # log level setting (ex: DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_LEVEL: str = "INFO"

    # JWT authentication settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Admin account settings
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: Optional[str] = None  # For development, set in .env
    ADMIN_PASSWORD_HASH: Optional[str] = ""  # For production, set in .env

    # Storage settings
    STORAGE_TYPE: Optional[str] = None  # aws or ceph
    
    # AWS S3 settings
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = "ap-northeast-2"
    
    # Ceph S3 settings
    CEPH_ACCESS_KEY_ID: Optional[str] = None
    CEPH_SECRET_ACCESS_KEY: Optional[str] = None
    CEPH_ENDPOINT_URL: Optional[str] = None

    # Redis settings for Tus server state (optional)
    REDIS_HOST: Optional[str] = None
    REDIS_PORT: Optional[int] = None
    REDIS_DB: int = 0
    
    # Tus protocol settings
    TUS_UPLOAD_BUCKET: str = "tus-uploads"
    TUS_UPLOAD_DIR: str = "/tmp/tus_uploads"  # Local temp storage before S3
    TUS_MAX_FILE_SIZE: int = 10 * 1024**3  # 10GB
    TUS_CHUNK_SIZE: int = 10 * 1024**2     # 10MB
    TUS_BUFFER_SIZE: int = 100 * 1024**2   # 100MB
    TUS_EXPIRATION_SECONDS: int = 86400    # 24 hours
    TUS_BUFFER_EXPIRATION: int = 3600      # 1 hour
    
    # Tus part size configuration
    TUS_PART_SIZE_MODE: str = "AUTO"       # AUTO or MANUAL
    TUS_MANUAL_PART_SIZE: int = 100 * 1024**2  # 100MB (when MANUAL)
    
    # Tus monitoring and logging
    TUS_ENABLE_METRICS: bool = True
    TUS_LOG_LEVEL: str = "INFO"
    
    # Dataset download settings
    DATASET_DOWNLOAD_DIR: Optional[str] = None  # Custom download directory

    # Kaggle marketplace settings
    KAGGLE_API_TOKEN: Optional[str] = None
    KAGGLE_USERNAME: Optional[str] = None
    KAGGLE_KEY: Optional[str] = None
    KAGGLE_TIMEOUT: int = 30
    KAGGLE_DOWNLOAD_TIMEOUT: int = 300

    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @field_validator('HF_API_TOKEN')
    @classmethod
    def validate_hf_token(cls, v: str) -> str:
        if not v:
            raise ValueError("HF_API_TOKEN is required")
        return v
    
    @field_validator('TUS_UPLOAD_BUCKET')
    @classmethod
    def validate_tus_bucket(cls, v: str) -> str:
        if not v:
            raise ValueError("TUS_UPLOAD_BUCKET is required")
        return v
    
    @field_validator('TUS_PART_SIZE_MODE')
    @classmethod
    def validate_tus_part_size_mode(cls, v: str) -> str:
        if v not in ["AUTO", "MANUAL"]:
            raise ValueError("TUS_PART_SIZE_MODE must be 'AUTO' or 'MANUAL'")
        return v
    
    @field_validator('TUS_MAX_FILE_SIZE')
    @classmethod
    def validate_tus_max_file_size(cls, v: int) -> int:
        if v <= 0 or v > 5 * 1024**4:  # 5TB limit
            raise ValueError("TUS_MAX_FILE_SIZE must be between 1 byte and 5TB")
        return v

    model_config = ConfigDict(env_file=".env")

settings = Settings()

def get_settings():
    return settings
