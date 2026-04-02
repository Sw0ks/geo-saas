"""
Экспорт всех SQLAlchemy моделей.
Импортируем здесь чтобы Alembic видел все модели при автогенерации миграций.
"""
from app.models.crawler_event import CrawlerEvent
from app.models.monitoring_result import MonitoringResult
from app.models.project import Project
from app.models.subscription import ActionPlan, GeneratedContent
from app.models.user import User

__all__ = [
    "User",
    "Project",
    "MonitoringResult",
    "CrawlerEvent",
    "ActionPlan",
    "GeneratedContent",
]
