"""
Модель события краулера.
Фиксирует каждый визит AI-бота на сайт клиента через трекер-сниппет.
Боты: 'AliceBot' | 'YandexBot' | 'GigaBot' | 'GPTBot' | 'ClaudeBot' | 'PerplexityBot'
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CrawlerEvent(Base):
    __tablename__ = "crawler_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Название бота: 'AliceBot', 'YandexBot', 'GigaBot', 'GPTBot', 'ClaudeBot', 'PerplexityBot'
    bot_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # User-Agent строка запроса
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Путь URL который обходил бот (/about, /products/123 и т.д.)
    url_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    # IP-адрес бота
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 до 45 символов

    # Верифицирован ли IP по официальным диапазонам Яндекса
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    visited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Связи
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="crawler_events"
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlerEvent id={self.id} bot={self.bot_name} "
            f"url={self.url_path} verified={self.verified}>"
        )
