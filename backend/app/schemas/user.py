"""
Pydantic v2 схемы для пользователей и аутентификации.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# --- Базовые ---

class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)


# --- Создание ---

class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Минимальная проверка надёжности пароля."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")
        return v


# --- Обновление ---

class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


# --- Ответ API ---

class UserResponse(UserBase):
    id: uuid.UUID
    subscription_plan: str
    subscription_expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Аутентификация ---

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # секунды
    user: UserResponse
