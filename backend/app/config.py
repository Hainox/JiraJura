"""Конфигурация приложения."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sao_inspection"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 часов
    UPLOAD_DIR: str = "uploads"
    MAX_PHOTO_SIZE_MB: int = 20

    model_config = {"env_file": ".env"}


settings = Settings()
