"""
Модели для планов действий и сгенерированного контента.

ActionPlan — задачи от Claude-агента для улучшения GEO-позиций.
GeneratedContent — статьи, FAQ, описания сгенерированные агентом.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ActionPlan(Base):
    """
    План действий от агента.
    Статусы: 'new' | 'in_progress' | 'done'
    """

    __tablename__ = "action_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # JSONB список задач от агента:
    # [{"id": 1, "title": "...", "description": "...", "priority": "high"}, ...]
    tasks_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 'new' | 'in_progress' | 'done'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")

    # Связи
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="action_plans"
    )

    def __repr__(self) -> str:
        return f"<ActionPlan id={self.id} status={self.status}>"


class GeneratedContent(Base):
    """
    Сгенерированный контент (статьи, FAQ, описания).
    Типы: 'article' | 'faq' | 'description'
    Статусы: 'draft' | 'published'
    """

    __tablename__ = "generated_content"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Тип контента: 'article' | 'faq' | 'description'
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # 'draft' | 'published'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Связи
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="generated_contents"
    )

    def __repr__(self) -> str:
        return f"<GeneratedContent id={self.id} type={self.type} status={self.status}>"
