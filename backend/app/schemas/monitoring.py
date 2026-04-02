"""
Pydantic v2 схемы для мониторинга GEO-позиций в AI.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# Допустимые платформы и тональности
PlatformType = Literal["alice", "gigachat"]
SentimentType = Literal["positive", "neutral", "negative"]


# --- Результат проверки ---

class MonitoringResultBase(BaseModel):
    prompt: str = Field(min_length=3, description="Промпт который отправлялся в AI")
    platform: PlatformType
    mentioned: bool
    position: int | None = None
    sentiment: SentimentType | None = None
    response_text: str | None = None


class MonitoringResultCreate(MonitoringResultBase):
    project_id: uuid.UUID


class MonitoringResultResponse(MonitoringResultBase):
    id: uuid.UUID
    project_id: uuid.UUID
    checked_at: datetime

    model_config = {"from_attributes": True}


# --- Запрос на запуск проверки ---

class MonitoringRunRequest(BaseModel):
    project_id: uuid.UUID
    platforms: list[PlatformType] = Field(
        default=["alice", "gigachat"],
        description="Платформы для проверки",
    )
    prompts: list[str] | None = Field(
        default=None,
        description="Переопределить промпты проекта (опционально)",
    )


# --- Статистика по проекту ---

class MonitoringStats(BaseModel):
    project_id: uuid.UUID
    total_checks: int
    mentioned_count: int
    mention_rate: float = Field(description="Процент упоминаний (0.0–1.0)")
    avg_position: float | None
    sentiment_breakdown: dict[str, int] = Field(
        description="{'positive': N, 'neutral': N, 'negative': N}"
    )
    by_platform: dict[str, dict] = Field(
        description="Статистика по каждой платформе"
    )
