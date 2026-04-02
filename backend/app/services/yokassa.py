"""
Клиент ЮKassa API для создания платежей и подписок.

Документация: https://yookassa.ru/developers/api
Аутентификация: HTTP Basic (shop_id : secret_key)
Верификация вебхука: после получения события делаем GET /payments/{id}
чтобы подтвердить статус сервер-к-серверу (ЮKassa не подписывает тело HMAC).
"""

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

YOKASSA_BASE_URL = "https://api.yookassa.ru/v3"

# ─── Тарифные планы (единственный источник истины) ────────────────────────────

PLAN_DETAILS: dict[str, dict[str, Any]] = {
    "start": {
        "name": "Старт",
        "price_rub": 990,
        "prompts_per_month": 10,
        "max_projects": 1,
        "features": ["GEO мониторинг", "AI Краулер трекер"],
        "description": "Для начинающих — 1 проект, 10 проверок в месяц",
    },
    "business": {
        "name": "Бизнес",
        "price_rub": 2990,
        "prompts_per_month": 50,
        "max_projects": 3,
        "features": ["GEO мониторинг", "AI Краулер трекер", "Агент + план", "Автоконтент"],
        "description": "Для растущего бизнеса — 3 проекта, 50 проверок в месяц",
    },
    "agency": {
        "name": "Агентство",
        "price_rub": 7990,
        "prompts_per_month": 200,
        "max_projects": 10,
        "features": ["GEO мониторинг", "AI Краулер трекер", "Агент + план", "Автоконтент", "White label"],
        "description": "Для агентств — 10 проектов, 200 проверок в месяц",
    },
}


@dataclass
class YookassaPaymentResult:
    """Результат создания платежа в ЮKassa."""
    payment_id: str
    status: str
    confirmation_url: str
    amount_rub: str


def _make_client() -> httpx.AsyncClient:
    """Создаёт httpx-клиент с Basic auth и таймаутом 30 сек."""
    return httpx.AsyncClient(
        base_url=YOKASSA_BASE_URL,
        auth=(settings.yokassa_shop_id, settings.yokassa_secret_key),
        timeout=30.0,
        headers={"Content-Type": "application/json"},
    )


async def create_payment(
    user_id: str,
    plan: str,
    return_url: str,
) -> YookassaPaymentResult:
    """
    Создаёт платёж в ЮKassa для выбранного тарифа.

    Args:
        user_id: UUID пользователя (сохраняем в metadata)
        plan: 'start' | 'business' | 'agency'
        return_url: URL куда редиректнуть после оплаты

    Returns:
        YookassaPaymentResult с confirmation_url для редиректа

    Raises:
        ValueError: если план неизвестен
        RuntimeError: если ЮKassa вернула ошибку
    """
    if plan not in PLAN_DETAILS:
        raise ValueError(f"Неизвестный тариф: {plan}")

    plan_info = PLAN_DETAILS[plan]
    amount = str(plan_info["price_rub"])

    payload = {
        "amount": {
            "value": f"{amount}.00",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "capture": True,
        "description": f"Подписка GEO Analytics — тариф «{plan_info['name']}»",
        # save_payment_method для рекуррентных платежей (будущие списания)
        "save_payment_method": True,
        "metadata": {
            "user_id": user_id,
            "plan": plan,
        },
    }

    # Idempotence-Key — уникальный ключ для предотвращения дублей
    idempotence_key = str(uuid.uuid4())

    async with _make_client() as client:
        response = await client.post(
            "/payments",
            json=payload,
            headers={"Idempotence-Key": idempotence_key},
        )

    if response.status_code not in (200, 201):
        error_body = response.text
        logger.error("yokassa_create_payment_failed", status=response.status_code, body=error_body)
        raise RuntimeError(f"ЮKassa вернула ошибку {response.status_code}: {error_body}")

    data = response.json()

    confirmation_url = data.get("confirmation", {}).get("confirmation_url", "")
    if not confirmation_url:
        raise RuntimeError("ЮKassa не вернула confirmation_url")

    logger.info(
        "yokassa_payment_created",
        payment_id=data["id"],
        user_id=user_id,
        plan=plan,
        amount=amount,
    )

    return YookassaPaymentResult(
        payment_id=data["id"],
        status=data["status"],
        confirmation_url=confirmation_url,
        amount_rub=amount,
    )


async def get_payment(payment_id: str) -> dict[str, Any]:
    """
    Получает данные платежа из ЮKassa по ID.
    Используется для верификации вебхука.

    Returns:
        Объект платежа как dict (status, metadata, amount, ...)
    """
    async with _make_client() as client:
        response = await client.get(f"/payments/{payment_id}")

    if response.status_code == 404:
        raise ValueError(f"Платёж {payment_id} не найден в ЮKassa")

    if not response.is_success:
        raise RuntimeError(f"ЮKassa GET /payments/{payment_id} → {response.status_code}")

    return response.json()


async def create_recurring_payment(
    user_id: str,
    plan: str,
    payment_method_id: str,
    return_url: str,
) -> YookassaPaymentResult:
    """
    Создаёт автоматическое рекуррентное списание по сохранённому payment_method_id.
    Вызывается при продлении подписки без участия пользователя.
    """
    if plan not in PLAN_DETAILS:
        raise ValueError(f"Неизвестный тариф: {plan}")

    plan_info = PLAN_DETAILS[plan]
    amount = str(plan_info["price_rub"])

    payload = {
        "amount": {
            "value": f"{amount}.00",
            "currency": "RUB",
        },
        "payment_method_id": payment_method_id,
        "capture": True,
        "description": f"Автопродление GEO Analytics — тариф «{plan_info['name']}»",
        "metadata": {
            "user_id": user_id,
            "plan": plan,
            "recurring": "true",
        },
    }

    idempotence_key = str(uuid.uuid4())

    async with _make_client() as client:
        response = await client.post(
            "/payments",
            json=payload,
            headers={"Idempotence-Key": idempotence_key},
        )

    if not response.is_success:
        raise RuntimeError(f"ЮKassa recurring payment failed: {response.status_code}")

    data = response.json()

    return YookassaPaymentResult(
        payment_id=data["id"],
        status=data["status"],
        confirmation_url=data.get("confirmation", {}).get("confirmation_url", return_url),
        amount_rub=amount,
    )
