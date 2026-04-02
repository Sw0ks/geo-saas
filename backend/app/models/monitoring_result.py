"""
Модель результата мониторинга.
Хранит ответ AI-платформы на конкретный промпт и факт упоминания бренда.
Платформы: 'alice' | 'gigachat'
Тональность: 'positive' | 'neutral' | 'negative'
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MonitoringResult(Base):
    __tablename__ = "monitoring_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Промпт который был отправлен в AI
    prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Платформа: 'alice' или 'gigachat'
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Упомянут ли бренд в ответе
    mentioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Позиция упоминания (None если не упомянут)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Тональность: 'positive' | 'neutral' | 'negative'
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Полный текст ответа AI
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Связи
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="monitoring_results"
    )

    def __repr__(self) -> str:
        return (
            f"<MonitoringResult id={self.id} platform={self.platform} "
            f"mentioned={self.mentioned} sentiment={self.sentiment}>"
        )
