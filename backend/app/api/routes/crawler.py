"""
Роутер трекера AI-краулеров.

Эндпоинты:

  ТРЕКЕР (без авторизации — вызывается сниппетом на сайте клиента):
    GET /v1/track               — принять визит бота, сохранить событие

  API (с JWT авторизацией — для дашборда):
    GET /api/v1/crawler/{project_id}/token   — получить tracker_token проекта
    GET /api/v1/crawler/{project_id}/events  — список событий (с фильтром)
    GET /api/v1/crawler/{project_id}/stats   — статистика по ботам и страницам

КРИТИЧНО: /v1/track должен отвечать за < 1 секунды.
Сниппет клиента ставит timeout=1s — если не успеем, он всё равно "проглотит" ошибку,
но мы хотим успеть сохранить данные.
Решение: принимаем запрос → сразу 200 → сохраняем в БД в фоне (BackgroundTasks).
"""
import ipaddress
import re
import uuid
from collections import Counter
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.core.security import get_current_user_id
from app.models.crawler_event import CrawlerEvent
from app.models.project import Project
from app.schemas.crawler import CrawlerEventResponse, CrawlerStats

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["crawler"])


# ─── Диапазоны IP Яндекса ─────────────────────────────────────────────────────
# Источник: https://yandex.ru/ips (обновлено 2025-04)
# Включает краулеры Яндекс.Поиска, Алисы, YandexBot, и др.
# При обновлении диапазонов — обновить этот список и перезапустить сервис.

YANDEX_IP_RANGES: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # IPv4 диапазоны Яндекса
    ipaddress.ip_network("5.45.192.0/18"),
    ipaddress.ip_network("5.255.192.0/18"),
    ipaddress.ip_network("37.9.64.0/18"),
    ipaddress.ip_network("37.140.128.0/18"),
    ipaddress.ip_network("77.88.0.0/18"),
    ipaddress.ip_network("84.201.128.0/18"),
    ipaddress.ip_network("87.250.224.0/19"),
    ipaddress.ip_network("90.156.176.0/22"),
    ipaddress.ip_network("93.158.128.0/18"),
    ipaddress.ip_network("95.108.128.0/17"),
    ipaddress.ip_network("100.43.64.0/19"),
    ipaddress.ip_network("130.193.0.0/17"),
    ipaddress.ip_network("141.8.128.0/18"),
    ipaddress.ip_network("178.154.128.0/18"),
    ipaddress.ip_network("185.32.187.0/24"),
    ipaddress.ip_network("199.21.99.0/24"),
    ipaddress.ip_network("213.180.192.0/19"),
    # IPv6 диапазоны Яндекса
    ipaddress.ip_network("2001:678:384::/48"),
    ipaddress.ip_network("2620:10f:d000::/44"),
    ipaddress.ip_network("2a02:6b8::/32"),
]


# ─── Сигнатуры ботов ─────────────────────────────────────────────────────────
# Маппинг подстроки User-Agent → каноническое имя бота.
# Порядок важен: более специфичные паттерны — выше.

BOT_SIGNATURES: list[tuple[str, str]] = [
    # Яндекс Алиса / YandexGPT
    ("alicebot",        "AliceBot"),
    ("yandexgpt",       "AliceBot"),
    ("alice/",          "AliceBot"),
    # Яндекс краулер (индексация)
    ("yandexbot",       "YandexBot"),
    ("yandex.com/bots", "YandexBot"),
    # ГигаЧат (Сбер) — официального UA пока нет, используем предположительный
    ("gigabot",         "GigaBot"),
    ("gigachat",        "GigaBot"),
    ("sberbot",         "GigaBot"),
    # OpenAI GPTBot
    ("gptbot",          "GPTBot"),
    ("chatgpt-user",    "GPTBot"),
    ("openai",          "GPTBot"),
    # Anthropic Claude
    ("claudebot",       "ClaudeBot"),
    ("claude-web",      "ClaudeBot"),
    ("anthropic-ai",    "ClaudeBot"),
    ("anthropic",       "ClaudeBot"),
    # Perplexity
    ("perplexitybot",   "PerplexityBot"),
    ("perplexity",      "PerplexityBot"),
]


# ─── Утилиты ─────────────────────────────────────────────────────────────────

def detect_bot_name(user_agent: str) -> str:
    """
    Определяет каноническое имя бота по строке User-Agent.

    Returns:
        Имя бота из BOT_SIGNATURES или "Other" если не распознан.
    """
    ua_lower = user_agent.lower()
    for signature, bot_name in BOT_SIGNATURES:
        if signature in ua_lower:
            return bot_name
    return "Other"


def is_yandex_ip(ip_str: str) -> bool:
    """
    Проверяет входит ли IP в официальные диапазоны Яндекса.

    Args:
        ip_str: строка IP-адреса (IPv4 или IPv6)

    Returns:
        True если IP принадлежит Яндексу.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    return any(ip in network for network in YANDEX_IP_RANGES)


def extract_client_ip(request: Request) -> str | None:
    """
    Извлекает реальный IP клиента из запроса.
    Учитывает заголовки прокси: X-Forwarded-For, X-Real-IP.
    В продакшене за Nginx — IP приходит в X-Real-IP.
    """
    # X-Real-IP — Nginx передаёт напрямую
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # X-Forwarded-For — цепочка прокси, берём первый (исходный) IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # Прямое подключение
    if request.client:
        return request.client.host

    return None


# ─── Фоновое сохранение события ──────────────────────────────────────────────

async def _save_crawler_event(
    project_id: uuid.UUID,
    bot_name: str,
    user_agent: str | None,
    url_path: str,
    ip: str | None,
    verified: bool,
) -> None:
    """
    Сохраняет событие краулера в БД.
    Вызывается через BackgroundTasks — не блокирует ответ клиенту.
    Ошибки логируются, не бросаются наружу — чтобы не влиять на ответ.
    """
    try:
        async with AsyncSessionLocal() as db:
            event = CrawlerEvent(
                id=uuid.uuid4(),
                project_id=project_id,
                bot_name=bot_name,
                user_agent=user_agent,
                url_path=url_path or "/",
                ip=ip,
                verified=verified,
                visited_at=datetime.now(timezone.utc),
            )
            db.add(event)
            await db.commit()

            await logger.ainfo(
                "crawler_event_saved",
                project_id=str(project_id),
                bot=bot_name,
                url=url_path,
                verified=verified,
            )
    except Exception as e:
        # Глотаем ошибку — критично не ломать сайт клиента
        await logger.aerror(
            "crawler_event_save_failed",
            project_id=str(project_id),
            error=str(e),
        )


# ─── /v1/track ───────────────────────────────────────────────────────────────

@router.get(
    "/v1/track",
    status_code=status.HTTP_200_OK,
    summary="Трекер визитов AI-ботов (вызывается сниппетом клиента)",
    include_in_schema=True,
)
async def track_bot_visit(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str,
    url: str = "/",
    bot: str = "",
    host: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Принимает данные о визите AI-бота от трекер-сниппета.

    **КРИТИЧНО**: отвечает за < 1 секунды.
    Сниппет на сайте клиента ставит timeout=1s.

    Алгоритм:
    1. Ищем проект по tracker_token → 200 даже если токен не найден (молча игнорируем)
    2. Определяем bot_name из параметра bot (User-Agent)
    3. Проверяем IP по диапазонам Яндекса
    4. Сохраняем в БД через BackgroundTask (не ждём завершения)
    5. Сразу возвращаем 200

    Пример вызова от сниппета:
        GET /v1/track?token=abc123&url=/products&bot=YandexBot/3.0&host=myshop.ru
    """
    # Быстро находим проект по токену
    project = await db.scalar(
        select(Project).where(Project.tracker_token == token)
    )

    # Неизвестный токен — отвечаем 200 молча (не раскрываем существование проекта)
    if not project:
        await logger.awarning("tracker_unknown_token", token=token[:8] + "...")
        return {"ok": True}

    # Определяем бота
    bot_name = detect_bot_name(bot) if bot else "Other"

    # Верифицируем IP (только для Яндекс-ботов имеет смысл проверять диапазоны)
    client_ip = extract_client_ip(request)
    verified = is_yandex_ip(client_ip) if client_ip else False

    # Сохраняем в фоне — не блокируем ответ
    background_tasks.add_task(
        _save_crawler_event,
        project_id=project.id,
        bot_name=bot_name,
        user_agent=bot or None,
        url_path=url,
        ip=client_ip,
        verified=verified,
    )

    # Возвращаем немедленно — до завершения фоновой задачи
    return {"ok": True}


# ─── /api/v1/crawler/* — защищённые эндпоинты дашборда ──────────────────────

def _get_dashboard_router() -> APIRouter:
    """Роутер для защищённых эндпоинтов дашборда."""
    dashboard = APIRouter(prefix="/api/v1/crawler", tags=["crawler"])

    @dashboard.get(
        "/{project_id}/token",
        summary="Получить tracker_token проекта для сниппета",
    )
    async def get_tracker_token(
        project_id: uuid.UUID,
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        """
        Возвращает tracker_token проекта.
        Токен вставляется в сниппет на сайте клиента.

        Пример сниппета (FastAPI):
            TRACKER_TOKEN = "полученный_токен"
        """
        project = await _get_project_or_403(project_id, user_id, db)
        return {
            "project_id": str(project.id),
            "tracker_token": project.tracker_token,
            "snippet_url": f"GET /v1/track?token={project.tracker_token}&url=<path>&bot=<ua>&host={project.domain}",
        }

    @dashboard.get(
        "/{project_id}/events",
        response_model=list[CrawlerEventResponse],
        summary="История визитов AI-ботов по проекту",
    )
    async def get_crawler_events(
        project_id: uuid.UUID,
        bot_name: str | None = None,
        verified_only: bool = False,
        limit: int = 100,
        offset: int = 0,
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
    ) -> list[CrawlerEventResponse]:
        """
        Возвращает историю визитов AI-ботов для проекта.

        Фильтры:
        - ?bot_name=AliceBot — только визиты конкретного бота
        - ?verified_only=true — только верифицированные IP
        - ?limit=50&offset=0 — пагинация
        """
        await _get_project_or_403(project_id, user_id, db)

        query = (
            select(CrawlerEvent)
            .where(CrawlerEvent.project_id == project_id)
            .order_by(CrawlerEvent.visited_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if bot_name:
            query = query.where(CrawlerEvent.bot_name == bot_name)
        if verified_only:
            query = query.where(CrawlerEvent.verified == True)  # noqa: E712

        rows = await db.scalars(query)
        return [CrawlerEventResponse.model_validate(r) for r in rows]

    @dashboard.get(
        "/{project_id}/stats",
        response_model=CrawlerStats,
        summary="Статистика визитов AI-ботов",
    )
    async def get_crawler_stats(
        project_id: uuid.UUID,
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
    ) -> CrawlerStats:
        """
        Агрегированная статистика:
        - Всего визитов и верифицированных
        - Разбивка по ботам: {'AliceBot': 42, 'GPTBot': 17, ...}
        - Топ-10 страниц по количеству визитов
        - Визиты по дням (последние 30 дней)
        """
        await _get_project_or_403(project_id, user_id, db)

        # Получаем все события
        all_events = list(await db.scalars(
            select(CrawlerEvent)
            .where(CrawlerEvent.project_id == project_id)
            .order_by(CrawlerEvent.visited_at.desc())
        ))

        total_visits = len(all_events)
        verified_visits = sum(1 for e in all_events if e.verified)

        # Разбивка по ботам
        bot_counter: Counter = Counter(e.bot_name for e in all_events)
        by_bot = dict(bot_counter.most_common())

        # Топ-10 страниц
        page_counter: Counter = Counter(e.url_path for e in all_events)
        top_pages = [
            {"url": url, "visits": count}
            for url, count in page_counter.most_common(10)
        ]

        # Визиты по дням (группируем по дате visited_at)
        day_counter: Counter = Counter(
            e.visited_at.strftime("%Y-%m-%d") for e in all_events
            if e.visited_at is not None
        )
        by_day = [
            {"date": date, "count": count}
            for date, count in sorted(day_counter.items())
        ]

        return CrawlerStats(
            project_id=project_id,
            total_visits=total_visits,
            verified_visits=verified_visits,
            by_bot=by_bot,
            by_day=by_day,
            top_pages=top_pages,
        )

    return dashboard


# Создаём и регистрируем dashboard-роутер как атрибут модуля
dashboard_router = _get_dashboard_router()


# ─── Вспомогательная функция ─────────────────────────────────────────────────

async def _get_project_or_403(
    project_id: uuid.UUID,
    user_id: str,
    db: AsyncSession,
) -> Project:
    """Получает проект и проверяет владельца. Бросает 404/403."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Проект не найден",
        )
    if str(project.user_id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому проекту",
        )
    return project
