from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    HF_API_TOKEN: str
    ALLOWED_ORIGINS: list = ["*"]
    CACHE_TIMEOUT: int = 3600
    GROUPS: list = ["region", "other", "library", "license", "language", "dataset", "pipeline_tag"]
    LIMITED_GROUPS: list = ["language", "dataset"]
    LIMIT: int = 100

    # log level setting (ex: DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # JWT 인증 설정
    SECRET_KEY: str = os.getenv("SECRET_KEY", "fallback-secret-key-change-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # 관리자 계정 설정
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")  # 개발용
    ADMIN_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "")  # 프로덕션용

    # Storage 설정
    STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "aws")  # aws 또는 ceph
    
    # AWS S3 설정
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-northeast-2")
    
    # Ceph S3 설정
    CEPH_ACCESS_KEY_ID: str = os.getenv("CEPH_ACCESS_KEY_ID", "")
    CEPH_SECRET_ACCESS_KEY: str = os.getenv("CEPH_SECRET_ACCESS_KEY", "")
    CEPH_ENDPOINT_URL: str = os.getenv("CEPH_ENDPOINT_URL", "")

    class Config:
        env_file = ".env"

settings = Settings()

def get_settings():
    return settings