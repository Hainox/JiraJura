"""Конфигурация приложения."""
from pydantic_settings import BaseSettings

DEV_SECRET_KEY = "dev-secret-change-in-production"


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sao_inspection"
    SECRET_KEY: str = DEV_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 часов
    UPLOAD_DIR: str = "uploads"
    MAX_PHOTO_SIZE_MB: int = 20
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173"
    # Аварийный рубильник на "одна проверка площадки в сутки" — выключить
    # без редеплоя кода, если лимит где-то ошибочно блокирует реальную
    # работу в поле, пока разбираемся в чём дело. По умолчанию включён.
    ENABLE_DAILY_INSPECTION_LIMIT: bool = True
    # Rate-limit публичного эндпоинта загрузки вложений обращений (/feedback).
    # Лимит числа вложений на обращение снят (продуктовое решение), поэтому
    # диск защищаем на уровне IP: не более N загрузок и не более M байт за
    # одно окно. На проде один uvicorn-процесс — счётчик живёт в памяти
    # процесса (app/services/rate_limit.py).
    FEEDBACK_ATTACHMENT_MAX_PER_WINDOW: int = 20
    FEEDBACK_ATTACHMENT_RATE_WINDOW_SECONDS: int = 60
    FEEDBACK_ATTACHMENT_MAX_BYTES_PER_WINDOW: int = 100 * 1024 * 1024

    model_config = {"env_file": ".env"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
