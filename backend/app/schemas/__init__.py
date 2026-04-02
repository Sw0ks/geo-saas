"""
Экспорт всех Pydantic v2 схем.
"""
from app.schemas.content import (
    ActionPlanCreate,
    ActionPlanResponse,
    ActionPlanUpdateStatus,
    ActionTask,
    ContentGenerateRequest,
    GeneratedContentCreate,
    GeneratedContentResponse,
    GeneratedContentUpdate,
)
from app.schemas.crawler import (
    CrawlerEventIncoming,
    CrawlerEventResponse,
    CrawlerStats,
)
from app.schemas.monitoring import (
    MonitoringResultCreate,
    MonitoringResultResponse,
    MonitoringRunRequest,
    MonitoringStats,
)
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectShort,
    ProjectUpdate,
)
from app.schemas.user import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

__all__ = [
    # User / Auth
    "UserCreate", "UserUpdate", "UserResponse",
    "LoginRequest", "TokenResponse",
    # Project
    "ProjectCreate", "ProjectUpdate", "ProjectResponse", "ProjectShort",
    # Monitoring
    "MonitoringResultCreate", "MonitoringResultResponse",
    "MonitoringRunRequest", "MonitoringStats",
    # Crawler
    "CrawlerEventIncoming", "CrawlerEventResponse", "CrawlerStats",
    # Content / Plans
    "ActionTask", "ActionPlanCreate", "ActionPlanResponse", "ActionPlanUpdateStatus",
    "GeneratedContentCreate", "GeneratedContentUpdate", "GeneratedContentResponse",
    "ContentGenerateRequest",
]
