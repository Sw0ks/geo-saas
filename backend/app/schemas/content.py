"""
Pydantic v2 схемы для планов действий агента и сгенерированного контента.
"""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Задача в плане действий ---

class ActionTask(BaseModel):
    """Одна задача в плане от агента."""
    priority: int  # 1 = самый важный
    category: Literal["content", "faq", "technical", "mentions", "tone"]
    title: str
    description: str
    expected_result: str


# --- Планы действий ---

class ActionPlanCreate(BaseModel):
    project_id: uuid.UUID


class ActionPlanResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    tasks_json: list[Any]  # список ActionTask в JSONB
    generated_at: datetime
    status: Literal["new", "in_progress", "done"]

    model_config = {"from_attributes": True}


class ActionPlanUpdateStatus(BaseModel):
    status: Literal["new", "in_progress", "done"]


# --- Сгенерированный контент ---

ContentType = Literal["article", "faq", "description"]
ContentStatus = Literal["draft", "published"]


class GeneratedContentCreate(BaseModel):
    project_id: uuid.UUID
    type: ContentType
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)


class GeneratedContentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    status: ContentStatus | None = None


class GeneratedContentResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    type: ContentType
    title: str
    body: str
    status: ContentStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Запрос на генерацию контента ---

class ContentGenerateRequest(BaseModel):
    project_id: uuid.UUID
    type: ContentType
    topic: str = Field(description="Тема или задача из плана действий")
    task_id: uuid.UUID | None = Field(
        default=None,
        description="ID задачи из action_plan (опционально, для контекста)",
    )
    additional_context: str | None = Field(
        default=None,
        description="Дополнительный контекст (описание бизнеса, ключевые слова)",
    )


class ContentUpdateStatus(BaseModel):
    status: ContentStatus
