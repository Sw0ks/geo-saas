"""
Celery-задачи для email-уведомлений.

send_weekly_reports()
    Celery Beat entry point — каждый понедельник 09:00 МСК.
    Для каждого пользователя с активной подпиской и email:
      1. Собирает статистику за прошедшую неделю по всем его проектам
      2. Берёт топ-3 задачи из последнего плана действий
      3. Отправляет HTML-письмо через email_service

Celery задача синхронная — asyncio.run() служит мостом к async коду.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, or_, select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.crawler_event import CrawlerEvent
from app.models.monitoring_result import MonitoringResult
from app.models.project import Project
from app.models.subscription import ActionPlan
from app.models.user import User
from app.services.email_service import WeeklyReportData, send_weekly_report_sync

logger = structlog.get_logger(__name__)


# ─── Async реализация ─────────────────────────────────────────────────────────

async def _collect_user_report_data(
    user: User,
    db,
    week_ago: datetime,
) -> WeeklyReportData | None:
    """
    Собирает статистику за неделю для одного пользователя по всем его проектам.
    Возвращает None если у пользователя нет проектов с данными.
    """
    # Получаем все проекты пользователя
    rows = await db.scalars(select(Project).where(Project.user_id == user.id))
    projects = list(rows)

    if not projects:
        return None

    project_ids = [p.id for p in projects]

    # ── Мониторинг за неделю ─────────────────────────────────────────────────
    monitoring_rows = await db.scalars(
        select(MonitoringResult).where(
            MonitoringResult.project_id.in_(project_ids),
            MonitoringResult.checked_at >= week_ago,
        )
    )
    results = list(monitoring_rows)

    alice_results = [r for r in results if r.platform == "alice"]
    gigachat_results = [r for r in results if r.platform == "gigachat"]

    def _mention_rate(rs: list) -> float:
        if not rs:
            return 0.0
        return round(sum(1 for r in rs if r.mentioned) / len(rs) * 100, 1)

    alice_rate = _mention_rate(alice_results)
    gigachat_rate = _mention_rate(gigachat_results)

    # ── Краулер за неделю ────────────────────────────────────────────────────
    crawler_count = await db.scalar(
        select(func.count()).where(
            CrawlerEvent.project_id.in_(project_ids),
            CrawlerEvent.visited_at >= week_ago,
        )
    )

    # ── Топ-3 задачи из последнего плана действий ────────────────────────────
    top_tasks: list[dict] = []
    plan = await db.scalar(
        select(ActionPlan)
        .where(ActionPlan.project_id.in_(project_ids))
        .order_by(ActionPlan.generated_at.desc())
        .limit(1)
    )
    if plan and plan.tasks_json:
        # Задачи уже отсортированы по приоритету (1 = важнейший)
        raw_tasks = plan.tasks_json
        if isinstance(raw_tasks, list):
            top_tasks = raw_tasks[:3]

    # Название: имя первого проекта (или количество проектов)
    project_name = projects[0].name if len(projects) == 1 else f"{len(projects)} проектов"

    return WeeklyReportData(
        project_name=project_name,
        alice_mention_rate=alice_rate,
        gigachat_mention_rate=gigachat_rate,
        crawler_visits=crawler_count or 0,
        top_tasks=top_tasks,
    )


async def _send_weekly_reports_for_all() -> dict:
    """
    Основная логика еженедельной рассылки.
    Запускает отправку для всех пользователей с активными подписками.
    """
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        # Выбираем пользователей с активной подпиской и непустым email
        stmt = select(User).where(
            User.email.isnot(None),
            or_(
                User.subscription_expires_at.is_(None),
                User.subscription_expires_at > now,
            ),
        )
        rows = await db.scalars(stmt)
        users = list(rows)

    logger.info("weekly_report_start", users_count=len(users))

    sent = 0
    skipped = 0
    errors = 0

    for user in users:
        try:
            async with AsyncSessionLocal() as db:
                data = await _collect_user_report_data(user, db, week_ago)

            if data is None:
                skipped += 1
                continue

            # Отправка синхронная — SMTP блокирует, поэтому await to_thread не нужен
            # (мы уже в asyncio.run() контексте, из Celery)
            send_weekly_report_sync(
                to_email=user.email,
                name=user.name,
                data=data,
            )
            sent += 1

        except Exception as exc:
            errors += 1
            logger.error(
                "weekly_report_user_error",
                user_id=str(user.id),
                email=user.email,
                error=str(exc),
            )

    logger.info(
        "weekly_report_done",
        sent=sent,
        skipped=skipped,
        errors=errors,
    )
    return {"sent": sent, "skipped": skipped, "errors": errors}


# ─── Celery задача ─────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.email_tasks.send_weekly_reports",
    queue="default",
    time_limit=600,   # не более 10 минут на всю рассылку
)
def send_weekly_reports() -> dict:
    """
    Celery Beat entry point для еженедельной рассылки.
    Расписание: каждый понедельник в 09:00 МСК (настроено в celery_app.py).
    """
    try:
        return asyncio.run(_send_weekly_reports_for_all())
    except Exception as exc:
        logger.error("weekly_report_task_failed", error=str(exc))
        raise
