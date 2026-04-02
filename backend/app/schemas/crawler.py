"""
Pydantic v2 схемы для трекера AI-краулеров.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# Известные AI-боты которые отслеживаем
BotNameType = Literal[
    "AliceBot",
    "YandexBot",
    "GigaBot",
    "GPTBot",
    "ClaudeBot",
    "PerplexityBot",
    "Other",
]


# --- Входящее событие от трекер-сниппета ---

class CrawlerEventIncoming(BaseModel):
    """
    Данные от GET /v1/track endpoint.
    Параметры query-строки от сниппета на сайте клиента.
    """
    token: str = Field(description="Токен проекта клиента")
    url: str = Field(max_length=2048, description="URL страницы которую обходил бот")
    bot: str = Field(description="Имя бота из User-Agent")
    host: str | None = Field(default=None, description="Хост сайта клиента")


# --- Хранимое событие ---

class CrawlerEventResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    bot_name: str
    user_agent: str | None
    url_path: str
    ip: str | None
    verified: bool
    visited_at: datetime

    model_config = {"from_attributes": True}


# --- Статистика по ботам ---

class CrawlerStats(BaseModel):
    project_id: uuid.UUID
    total_visits: int
    verified_visits: int
    by_bot: dict[str, int] = Field(description="{'AliceBot': N, 'GPTBot': N, ...}")
    by_day: list[dict] = Field(description="[{'date': '2024-01-01', 'count': N}, ...]")
    top_pages: list[dict] = Field(
        description="[{'url': '/about', 'visits': N}, ...]"
    )
