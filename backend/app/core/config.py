"""
Конфигурация приложения через pydantic-settings.
Все значения берутся из переменных окружения или .env файла.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- База данных ---
    database_url: str = "postgresql+asyncpg://user:pass@localhost/geo_db"
    redis_url: str = "redis://localhost:6379"

    # --- AI API ---
    anthropic_api_key: str = ""
    yandex_gpt_api_key: str = ""
    yandex_cloud_folder_id: str = ""
    gigachat_client_id: str = ""
    gigachat_client_secret: str = ""
    gigachat_api_key: str = ""

    # --- Оплата ЮKassa ---
    yokassa_shop_id: str = ""
    yokassa_secret_key: str = ""

    # --- Auth ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 дней
    nextauth_secret: str = ""
    nextauth_url: str = "https://yourdomain.ru"

    # --- Приложение ---
    domain: str = "yourdomain.ru"
    tracker_endpoint: str = "https://api.yourdomain.ru/v1/track"
    debug: bool = False

    # --- SMTP (email-уведомления) ---
    smtp_host: str = "smtp.yandex.ru"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # --- Лимиты тарифов ---
    plan_start_prompts: int = 10
    plan_start_projects: int = 1
    plan_business_prompts: int = 50
    plan_business_projects: int = 3
    plan_agency_prompts: int = 200
    plan_agency_projects: int = 10


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()


# Удобный алиас для импорта в других модулях
settings = get_settings()
