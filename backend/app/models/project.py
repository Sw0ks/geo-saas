"""
Модель проекта.
Каждый проект принадлежит пользователю и хранит:
- домен сайта
- список конкурентов (JSONB)
- список промптов для мониторинга (JSONB)
"""
import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)

    # Уникальный токен для идентификации проекта в трекер-сниппетах
    # Генерируется автоматически при создании проекта, уникален в БД
    tracker_token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
    )

    # Массив доменов конкурентов: ["competitor1.ru", "competitor2.ru"]
    competitors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Массив промптов для мониторинга: ["где купить ...", "лучший ... в Москве"]
    prompts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="projects")  # noqa: F821
    monitoring_results: Mapped[list["MonitoringResult"]] = relationship(  # noqa: F821
        "MonitoringResult", back_populates="project", cascade="all, delete-orphan"
    )
    crawler_events: Mapped[list["CrawlerEvent"]] = relationship(  # noqa: F821
        "CrawlerEvent", back_populates="project", cascade="all, delete-orphan"
    )
    action_plans: Mapped[list["ActionPlan"]] = relationship(  # noqa: F821
        "ActionPlan", back_populates="project", cascade="all, delete-orphan"
    )
    generated_contents: Mapped[list["GeneratedContent"]] = relationship(  # noqa: F821
        "GeneratedContent", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} domain={self.domain}>"
