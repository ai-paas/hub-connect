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

    class Config:
        env_file = ".env"

settings = Settings()