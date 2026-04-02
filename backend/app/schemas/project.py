"""
Pydantic v2 схемы для проектов.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# --- Базовые ---

class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=3, max_length=255, description="Домен без https:// (пример: myshop.ru)")
    competitors: list[str] = Field(default_factory=list, description="Список доменов конкурентов")
    prompts: list[str] = Field(default_factory=list, description="Промпты для мониторинга в AI")

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, v: str) -> str:
        """Убираем схему если пользователь вставил полный URL."""
        v = v.strip().lower()
        v = v.removeprefix("https://").removeprefix("http://")
        v = v.rstrip("/")
        return v

    @field_validator("competitors", mode="before")
    @classmethod
    def clean_competitors(cls, v: list) -> list:
        """Нормализуем домены конкурентов."""
        result = []
        for domain in v:
            domain = str(domain).strip().lower()
            domain = domain.removeprefix("https://").removeprefix("http://")
            domain = domain.rstrip("/")
            if domain:
                result.append(domain)
        return result


# --- Создание ---

class ProjectCreate(ProjectBase):
    pass


# --- Обновление (все поля опциональны) ---

class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    domain: str | None = None
    competitors: list[str] | None = None
    prompts: list[str] | None = None


# --- Ответ API ---

class ProjectResponse(ProjectBase):
    id: uuid.UUID
    user_id: uuid.UUID
    tracker_token: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Краткая версия для списков ---

class ProjectShort(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    created_at: datetime

    model_config = {"from_attributes": True}
