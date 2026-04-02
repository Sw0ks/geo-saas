"""
Celery-задачи для автоматической генерации планов действий.

generate_daily_plan(project_id)
    Проверяет свежесть плана проекта. Если план старше 7 дней
    или отсутствует — генерирует новый через claude_agent.py.

generate_daily_plans_for_all()
    Celery Beat entry point — 04:00 МСК ежедневно.
    Находит проекты без свежего плана и запускает generate_daily_plan
    для каждого.

Celery задачи синхронные — asyncio.run() служит мостом к async коду.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import or_, select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.project import Project
from app.models.subscription import ActionPlan
from app.models.user import User

logger = structlog.get_logger(__name__)

# Порог свежести плана — если план старше этого, генерируем новый
_PLAN_FRESHNESS_DAYS = 7


# ─── Async реализация ─────────────────────────────────────────────────────────

async def _generate_daily_plan(project_id: str) -> dict:
    """
    Async-реализация генерации плана для одного проекта.

    Алгоритм:
    1. Загружаем проект из БД
    2. Проверяем дату последнего плана
    3. Если план свежее 7 дней — пропускаем
    4. Загружаем последние результаты мониторинга
    5. Вызываем Claude API через claude_agent.generate_action_plan()
    6. Сохраняем план в БД
    """
    # Импортируем здесь — не загружаем Anthropic клиент при старте beat
    from app.models.monitoring_result import MonitoringResult
    from app.services.claude_agent import build_agent_input, generate_action_plan

    log = logger.bind(project_id=project_id)

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(project_id))
        if not project:
            await log.aerror("content_task_project_not_found")
            return {"error": "project_not_found", "project_id": project_id}

        # Проверяем свежесть последнего плана
        latest_plan = await db.scalar(
            select(ActionPlan)
            .where(ActionPlan.project_id == project.id)
            .order_by(ActionPlan.generated_at.desc())
            .limit(1)
        )

        now = datetime.now(timezone.utc)
        freshness_threshold = now - timedelta(days=_PLAN_FRESHNESS_DAYS)

        if latest_plan is not None:
            plan_age = latest_plan.generated_at
            # Нормализуем timezone awareness
            if plan_age.tzinfo is None:
                plan_age = plan_age.replace(tzinfo=timezone.utc)

            if plan_age > freshness_threshold:
                age_days = (now - plan_age).days
                await log.ainfo(
                    "content_task_plan_fresh_skip",
                    plan_age_days=age_days,
                    threshold_days=_PLAN_FRESHNESS_DAYS,
                )
                return {
                    "skipped": True,
                    "reason": f"plan_is_fresh ({age_days} дней)",
                    "project_id": project_id,
                }

        # Загружаем последние результаты мониторинга для агента
        monitoring_rows = await db.scalars(
            select(MonitoringResult)
            .where(MonitoringResult.project_id == project.id)
            .order_by(MonitoringResult.checked_at.desc())
            .limit(30)
        )
        monitoring_results = [
            {
                "prompt": r.prompt,
                "platform": r.platform,
                "mentioned": r.mentioned,
                "position": r.position,
                "sentiment": r.sentiment,
                "response_text": r.response_text,
            }
            for r in monitoring_rows
        ]

        await log.ainfo(
            "content_task_generating_plan",
            monitoring_results_count=len(monitoring_results),
            has_previous_plan=latest_plan is not None,
        )

        # Строим входные данные для агента
        agent_input = build_agent_input(
            project_id=project.id,
            project_name=project.name,
            project_domain=project.domain,
            project_competitors=project.competitors or [],
            project_prompts=project.prompts or [],
            monitoring_results=monitoring_results,
        )

        # Генерируем план через Claude API
        plan_result = await generate_action_plan(agent_input)

        # Сохраняем в БД
        new_plan = ActionPlan(
            id=uuid.uuid4(),
            project_id=project.id,
            # tasks_json[0] — метаданные с summary, остальные — задачи
            tasks_json=[
                {"_summary": plan_result.summary},
                *plan_result.to_tasks_json(),
            ],
            generated_at=now,
            status="new",
        )
        db.add(new_plan)
        await db.commit()

        await log.ainfo(
            "content_task_plan_saved",
            plan_id=str(new_plan.id),
            tasks_count=len(plan_result.tasks),
        )

        return {
            "project_id": project_id,
            "project_name": project.name,
            "plan_id": str(new_plan.id),
            "tasks_count": len(plan_result.tasks),
        }


async def _generate_daily_plans_for_all() -> dict:
    """
    Находит все проекты без свежего плана (старше 7 дней или без плана)
    и диспатчит для каждого задачу generate_daily_plan.
    """
    now = datetime.now(timezone.utc)
    freshness_threshold = now - timedelta(days=_PLAN_FRESHNESS_DAYS)

    async with AsyncSessionLocal() as db:
        # Активные проекты с подпиской и промптами
        stmt = (
            select(Project)
            .join(User, Project.user_id == User.id)
            .where(
                or_(
                    User.subscription_expires_at.is_(None),
                    User.subscription_expires_at > now,
                )
            )
        )
        rows = await db.scalars(stmt)
        all_projects = list(rows)

        # Фильтруем: только проекты с промптами
        projects_with_prompts = [p for p in all_projects if p.prompts]

        # Для каждого проекта проверяем свежесть плана
        needs_plan: list[Project] = []
        for project in projects_with_prompts:
            latest = await db.scalar(
                select(ActionPlan)
                .where(ActionPlan.project_id == project.id)
                .order_by(ActionPlan.generated_at.desc())
                .limit(1)
            )

            if latest is None:
                # Планов нет вообще
                needs_plan.append(project)
            else:
                plan_date = latest.generated_at
                if plan_date.tzinfo is None:
                    plan_date = plan_date.replace(tzinfo=timezone.utc)
                if plan_date <= freshness_threshold:
                    # План устарел
                    needs_plan.append(project)

    logger.info(
        "content_daily_plans_all_start",
        total_projects=len(projects_with_prompts),
        needs_plan=len(needs_plan),
    )

    dispatched: list[str] = []
    for project in needs_plan:
        generate_daily_plan.apply_async(
            args=[str(project.id)],
            queue="content",
        )
        dispatched.append(str(project.id))

    logger.info("content_daily_plans_dispatched", count=len(dispatched))
    return {"dispatched": len(dispatched), "project_ids": dispatched}


# ─── Celery задачи (sync обёртки) ─────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.content_tasks.generate_daily_plan",
    bind=True,
    max_retries=2,
    default_retry_delay=300,   # повтор через 5 минут (Claude API перегрузка)
    queue="content",
    time_limit=120,            # hard kill через 2 минуты
    soft_time_limit=100,
)
def generate_daily_plan(self, project_id: str) -> dict:
    """
    Генерирует план действий для проекта если текущий устарел (> 7 дней).

    Args:
        project_id: UUID проекта в виде строки

    Returns:
        dict со статусом выполнения

    Retries:
        До 2 раз при ошибках Claude API (rate limit, connection error).
    """
    try:
        return asyncio.run(_generate_daily_plan(project_id))

    except Exception as exc:
        logger.error(
            "content_task_failed",
            project_id=project_id,
            attempt=self.request.retries + 1,
            error=str(exc),
        )
        raise self.retry(
            exc=exc,
            countdown=300 * (2 ** self.request.retries),
        )


@celery_app.task(
    name="app.tasks.content_tasks.generate_daily_plans_for_all",
    queue="default",
    time_limit=120,
)
def generate_daily_plans_for_all() -> dict:
    """
    Celery Beat entry point для ежедневной генерации планов.
    Расписание: каждый день в 04:00 МСК (настроено в celery_app.py).

    Только диспатчит задачи — не выполняет генерацию напрямую.
    """
    try:
        return asyncio.run(_generate_daily_plans_for_all())
    except Exception as exc:
        logger.error("content_all_plans_failed", error=str(exc))
        raise
