"""
Биллинг: тарифы, создание платежей, вебхук ЮKassa, статус подписки.

Эндпоинты:
  GET  /billing/plans            — список тарифов (публичный)
  GET  /billing/status           — статус подписки текущего пользователя
  POST /billing/create-payment   — создать платёж в ЮKassa
  POST /billing/webhook          — вебхук от ЮKassa (без авторизации)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.user import User
from app.services.yokassa import PLAN_DETAILS, create_payment, get_payment

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ─── Схемы ────────────────────────────────────────────────────────────────────

class PlanInfo(BaseModel):
    key: str
    name: str
    price_rub: int
    prompts_per_month: int
    max_projects: int
    features: list[str]
    description: str


class CreatePaymentRequest(BaseModel):
    plan: str = Field(..., description="Тариф: start | business | agency")
    return_url: str = Field(..., description="URL редиректа после оплаты")


class CreatePaymentResponse(BaseModel):
    payment_id: str
    confirmation_url: str
    amount_rub: str
    plan: str


class SubscriptionStatus(BaseModel):
    plan: str
    plan_name: str
    prompts_per_month: int
    max_projects: int
    expires_at: datetime | None
    is_active: bool
    days_left: int | None


# ─── GET /billing/plans ───────────────────────────────────────────────────────

@router.get("/plans", response_model=list[PlanInfo])
async def get_plans() -> list[PlanInfo]:
    """Возвращает все доступные тарифы с ценами и лимитами. Авторизация не нужна."""
    return [
        PlanInfo(key=key, **details)
        for key, details in PLAN_DETAILS.items()
    ]


# ─── GET /billing/status ──────────────────────────────────────────────────────

@router.get("/status", response_model=SubscriptionStatus)
async def get_subscription_status(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionStatus:
    """Текущий тариф, дата истечения и лимиты для авторизованного пользователя."""
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    plan_info = PLAN_DETAILS.get(user.subscription_plan, PLAN_DETAILS["start"])
    now = datetime.now(timezone.utc)

    is_active: bool
    days_left: int | None = None

    if user.subscription_expires_at is None:
        # Нет активной оплаченной подписки — базовый бесплатный доступ
        is_active = True
    else:
        expires = user.subscription_expires_at
        # Приводим к aware datetime если нужно
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        is_active = expires > now
        if is_active:
            days_left = (expires - now).days

    return SubscriptionStatus(
        plan=user.subscription_plan,
        plan_name=plan_info["name"],
        prompts_per_month=plan_info["prompts_per_month"],
        max_projects=plan_info["max_projects"],
        expires_at=user.subscription_expires_at,
        is_active=is_active,
        days_left=days_left,
    )


# ─── POST /billing/create-payment ─────────────────────────────────────────────

@router.post("/create-payment", response_model=CreatePaymentResponse)
async def create_payment_endpoint(
    body: CreatePaymentRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    """
    Создаёт платёж в ЮKassa для выбранного тарифа.
    Возвращает confirmation_url для редиректа пользователя.
    """
    if body.plan not in PLAN_DETAILS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный тариф «{body.plan}». Доступны: start, business, agency",
        )

    # Проверяем что пользователь существует
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    try:
        result = await create_payment(
            user_id=user_id,
            plan=body.plan,
            return_url=body.return_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        logger.error("create_payment_failed", user_id=user_id, plan=body.plan, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка платёжной системы. Попробуйте позже.",
        )

    return CreatePaymentResponse(
        payment_id=result.payment_id,
        confirmation_url=result.confirmation_url,
        amount_rub=result.amount_rub,
        plan=body.plan,
    )


# ─── POST /billing/webhook ─────────────────────────────────────────────────────

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def yokassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Вебхук от ЮKassa. Не требует авторизации.
    При событии payment.succeeded обновляет подписку пользователя на +30 дней.

    Безопасность: верифицируем каждое событие обратным запросом к API ЮKassa
    (GET /payments/{id}) чтобы исключить подделку вебхука.
    """
    try:
        event_data: dict[str, Any] = await request.json()
    except Exception:
        logger.warning("yokassa_webhook_invalid_json")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    event_type: str = event_data.get("event", "")
    payment_obj: dict[str, Any] = event_data.get("object", {})
    payment_id: str = payment_obj.get("id", "")

    logger.info("yokassa_webhook_received", event=event_type, payment_id=payment_id)

    # Нас интересует только payment.succeeded
    if event_type != "payment.succeeded":
        return {"status": "ignored"}

    if not payment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing payment id")

    # ── Верификация: запрашиваем платёж у ЮKassa, не доверяем телу вебхука ──
    try:
        verified_payment = await get_payment(payment_id)
    except (ValueError, RuntimeError) as e:
        logger.error("yokassa_webhook_verify_failed", payment_id=payment_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось верифицировать платёж")

    verified_status = verified_payment.get("status")
    if verified_status != "succeeded":
        logger.warning(
            "yokassa_webhook_status_mismatch",
            payment_id=payment_id,
            claimed="succeeded",
            actual=verified_status,
        )
        return {"status": "ignored"}

    # ── Читаем metadata ──
    metadata: dict[str, str] = verified_payment.get("metadata", {})
    user_id_str: str | None = metadata.get("user_id")
    plan: str | None = metadata.get("plan")

    if not user_id_str or not plan:
        logger.error(
            "yokassa_webhook_missing_metadata",
            payment_id=payment_id,
            metadata=metadata,
        )
        # Возвращаем 200 чтобы ЮKassa не повторяла запрос
        return {"status": "error_logged"}

    if plan not in PLAN_DETAILS:
        logger.error("yokassa_webhook_unknown_plan", plan=plan, payment_id=payment_id)
        return {"status": "error_logged"}

    # ── Обновляем подписку пользователя ──
    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        logger.error("yokassa_webhook_invalid_user_id", user_id=user_id_str)
        return {"status": "error_logged"}

    user = await db.get(User, user_uuid)
    if not user:
        logger.error("yokassa_webhook_user_not_found", user_id=user_id_str)
        return {"status": "error_logged"}

    now = datetime.now(timezone.utc)

    # Если подписка ещё активна — продлеваем от текущей даты истечения,
    # иначе — от сегодня
    base_date = user.subscription_expires_at
    if base_date is None or base_date < now:
        base_date = now
    elif base_date.tzinfo is None:
        base_date = base_date.replace(tzinfo=timezone.utc)

    new_expires = base_date + timedelta(days=30)

    user.subscription_plan = plan
    user.subscription_expires_at = new_expires

    await db.commit()

    logger.info(
        "yokassa_subscription_updated",
        user_id=user_id_str,
        plan=plan,
        new_expires=new_expires.isoformat(),
        payment_id=payment_id,
    )

    return {"status": "ok"}
