"""
Middleware проверки подписки и лимитов промптов.

Срабатывает на запросы к:
  /api/v1/monitoring/*
  /api/v1/agent/*

Проверяет:
1. Подписка не истекла (если subscription_expires_at задан)
2. Количество проверок за текущий месяц не превышает лимит тарифа

При нарушении возвращает HTTP 402 Payment Required с сообщением на русском.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.database import AsyncSessionLocal
from app.core.security import get_subject_from_token
from app.models.monitoring_result import MonitoringResult
from app.models.project import Project
from app.models.user import User
from app.services.yokassa import PLAN_DETAILS

logger = structlog.get_logger(__name__)

# Защищённые префиксы путей
_PROTECTED_PREFIXES = (
    "/api/v1/monitoring",
    "/api/v1/agent",
)


class SubscriptionMiddleware(BaseHTTPMiddleware):
    """
    Проверяет активность подписки и лимиты перед запросами к мониторингу и агенту.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Пропускаем все пути которые не требуют проверки
        if not any(path.startswith(p) for p in _PROTECTED_PREFIXES):
            return await call_next(request)

        # Извлекаем токен из заголовка Authorization
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # Нет токена — пропускаем, роутер сам вернёт 401
            return await call_next(request)

        token = auth_header[len("Bearer "):]
        user_id_str = get_subject_from_token(token)

        if not user_id_str:
            # Невалидный токен — роутер разберётся
            return await call_next(request)

        # Загружаем пользователя и проверяем лимиты
        try:
            error_response = await self._check_subscription(user_id_str)
        except Exception as e:
            # Не ломаем сервис из-за ошибки middleware — логируем и пускаем дальше
            logger.error("subscription_middleware_error", user_id=user_id_str, error=str(e))
            return await call_next(request)

        if error_response is not None:
            return error_response

        return await call_next(request)

    async def _check_subscription(self, user_id_str: str) -> JSONResponse | None:
        """
        Возвращает JSONResponse с 402 если подписка истекла или превышен лимит.
        Возвращает None если всё в порядке.
        """
        try:
            user_uuid = uuid.UUID(user_id_str)
        except ValueError:
            return None

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_uuid)
            if not user:
                return None

            now = datetime.now(timezone.utc)

            # ── Проверка 1: подписка не истекла ──────────────────────────────
            if user.subscription_expires_at is not None:
                expires = user.subscription_expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)

                if expires < now:
                    plan_info = PLAN_DETAILS.get(user.subscription_plan, PLAN_DETAILS["start"])
                    return JSONResponse(
                        status_code=402,
                        content={
                            "detail": (
                                f"Подписка истекла {expires.strftime('%d.%m.%Y')}. "
                                f"Продлите тариф «{plan_info['name']}» для продолжения работы."
                            ),
                            "code": "subscription_expired",
                        },
                    )

            # ── Проверка 2: лимит промптов за текущий месяц ──────────────────
            plan_info = PLAN_DETAILS.get(user.subscription_plan, PLAN_DETAILS["start"])
            monthly_limit: int = plan_info["prompts_per_month"]

            # Начало текущего месяца (UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            stmt = (
                select(func.count(MonitoringResult.id))
                .join(Project, MonitoringResult.project_id == Project.id)
                .where(Project.user_id == user_uuid)
                .where(MonitoringResult.checked_at >= month_start)
            )
            result = await session.execute(stmt)
            monthly_used: int = result.scalar_one_or_none() or 0

            if monthly_used >= monthly_limit:
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": (
                            f"Достигнут лимит: использовано {monthly_used} из {monthly_limit} "
                            f"проверок в месяц для тарифа «{plan_info['name']}». "
                            f"Перейдите на более высокий тариф чтобы продолжить."
                        ),
                        "code": "prompts_limit_exceeded",
                        "used": monthly_used,
                        "limit": monthly_limit,
                        "plan": user.subscription_plan,
                    },
                )

        return None
