"""
Утилиты безопасности: хэширование паролей (bcrypt) и JWT-токены.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# --- Контекст bcrypt для хэширования паролей ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─────────────────────────── Пароли ────────────────────────────

def hash_password(plain_password: str) -> str:
    """Возвращает bcrypt-хэш пароля."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Сравнивает открытый пароль с хэшем. Безопасно к тайминговым атакам."""
    return pwd_context.verify(plain_password, hashed_password)


# ─────────────────────────── JWT ───────────────────────────────

def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Создаёт JWT access token.

    Args:
        subject: идентификатор пользователя (обычно str(user.id))
        expires_delta: время жизни; если None — берём из settings

    Returns:
        Подписанный JWT-токен (строка)
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Декодирует и валидирует JWT токен.

    Returns:
        Payload словарь с полями sub, exp, iat, type

    Raises:
        JWTError: если токен невалиден или просрочен
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def get_subject_from_token(token: str) -> str | None:
    """
    Безопасно извлекает subject (user_id) из токена.
    Возвращает None если токен невалиден — не бросает исключение.
    """
    try:
        payload = decode_access_token(token)
        subject: str | None = payload.get("sub")
        return subject
    except JWTError:
        return None


# ─────────────────── FastAPI Dependency ────────────────────────

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    FastAPI Dependency: извлекает user_id из Bearer-токена.

    Использование в роутере:
        async def endpoint(user_id: str = Depends(get_current_user_id)):
    """
    token = credentials.credentials
    subject = get_subject_from_token(token)

    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен недействителен или просрочен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return subject
