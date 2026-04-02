"""
Роутер аутентификации.
Эндпоинты:
  POST /auth/register  — регистрация нового пользователя
  POST /auth/login     — вход, получение JWT
  GET  /auth/me        — данные текущего пользователя
  POST /auth/logout    — инвалидация (клиентская, токен stateless)
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.models.user import User
from app.schemas.user import LoginRequest, TokenResponse, UserCreate, UserResponse, UserUpdate

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────── Регистрация ───────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового пользователя",
)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Регистрирует нового пользователя.
    - Проверяет уникальность email
    - Хэширует пароль через bcrypt
    - Возвращает JWT access token
    """
    # Проверяем что email не занят
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )

    # Создаём пользователя
    user = User(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        subscription_plan="start",
    )
    db.add(user)
    await db.flush()   # получаем id без commit (commit — в get_db)

    token = create_access_token(subject=str(user.id))

    await logger.ainfo(
        "user_registered",
        user_id=str(user.id),
        email=user.email,
    )

    # Отправляем приветственное письмо (не блокируем — ошибка не ломает регистрацию)
    try:
        from app.services.email_service import send_welcome_email
        import asyncio
        asyncio.create_task(send_welcome_email(user.email, user.name))
    except Exception:
        pass

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


# ─────────────────────────── Вход ──────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход по email и паролю",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Аутентифицирует пользователя.
    - Ищет пользователя по email
    - Проверяет пароль bcrypt
    - Возвращает JWT access token

    Намеренно возвращает одинаковое сообщение для несуществующего email
    и неверного пароля (не раскрываем, существует ли email).
    """
    user = await db.scalar(select(User).where(User.email == body.email))

    # Единое сообщение — не раскрываем существование email
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=str(user.id))

    await logger.ainfo("user_logged_in", user_id=str(user.id), email=user.email)

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


# ─────────────────────────── Текущий пользователь ──────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Данные текущего пользователя",
)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Возвращает профиль авторизованного пользователя.
    Требует заголовок: Authorization: Bearer <token>
    """
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return UserResponse.model_validate(user)


# ─────────────────────────── Обновление профиля ───────────────────

@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Обновить профиль (имя или пароль)",
)
async def update_me(
    body: UserUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Обновляет имя и/или пароль текущего пользователя.
    Только переданные поля применяются (частичное обновление).
    """
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    if body.name is not None:
        user.name = body.name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    await db.flush()
    await logger.ainfo("user_updated", user_id=user_id)
    return UserResponse.model_validate(user)


# ─────────────────────────── Logout (stateless) ────────────────────

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход (клиентская инвалидация токена)",
)
async def logout(
    user_id: str = Depends(get_current_user_id),
) -> None:
    """
    JWT stateless — инвалидация на стороне клиента (удаляем токен из хранилища).
    Серверная сторона только логирует событие.
    В будущем: добавить Redis blocklist для немедленной инвалидации.
    """
    await logger.ainfo("user_logged_out", user_id=user_id)
