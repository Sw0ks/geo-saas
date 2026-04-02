"""
Настройка асинхронного подключения к базе данных через SQLAlchemy 2.0.
Экспортирует: engine, AsyncSessionLocal, Base, get_db (dependency для FastAPI).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# --- Движок ---
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,          # SQL-логи только в debug-режиме
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,            # проверяем соединение перед использованием
)

# --- Фабрика сессий ---
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,        # объекты доступны после commit без re-fetch
    autoflush=False,
    autocommit=False,
)


# --- Базовый класс для всех моделей ---
class Base(DeclarativeBase):
    pass


# --- FastAPI dependency для получения сессии ---
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency-инъекция для FastAPI роутеров.
    Использование:
        async def endpoint(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
