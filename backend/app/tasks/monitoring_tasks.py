"""
Celery-задачи для GEO-мониторинга.

run_monitoring_for_project(project_id)
    Запускает все промпты проекта через Алису и ГигаЧат последовательно.
    Сохраняет каждый результат в БД сразу после получения.

run_monitoring_for_all_projects()
    Celery Beat entry point — 03:00 МСК ежедневно.
    Загружает все проекты с активной подпиской и запускает
    run_monitoring_for_project для каждого.

Celery задачи синхронные — asyncio.run() служит мостом к async коду.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import structlog
from celery import shared_task
from sqlalchemy import or_, select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.monitoring_result import MonitoringResult
from app.models.project import Project
from app.models.user import User

logger = structlog.get_logger(__name__)

# Задержка между запросами к одной платформе в секундах (не перегружаем сервисы)
_ALICE_DELAY = 5.0
_GIGACHAT_DELAY = 2.0


# ─── Async реализация ─────────────────────────────────────────────────────────

async def _run_monitoring_for_project(project_id: str) -> dict:
    """
    Async-реализация мониторинга одного проекта.
    Вызывается из синхронной Celery-задачи через asyncio.run().

    Алгоритм:
    1. Загружаем проект из БД
    2. Для каждого промпта запускаем Алису, затем ГигаЧат
    3. Каждый результат сохраняем в БД сразу (не ждём все)
    4. Ошибки отдельных платформ логируются, не останавливают всё
    """
    # Импортируем здесь — Playwright не должен импортироваться при запуске beat
    from app.services.alice_scraper import scrape_alice
    from app.services.gigachat import query_gigachat

    log = logger.bind(project_id=project_id)

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(project_id))
        if not project:
            await log.aerror("monitoring_task_project_not_found")
            return {"error": "project_not_found", "project_id": project_id}

        prompts: list[str] = project.prompts or []
        if not prompts:
            await log.awarning("monitoring_task_no_prompts")
            return {"skipped": True, "reason": "no_prompts", "project_id": project_id}

        brand = project.name
        await log.ainfo(
            "monitoring_task_start",
            domain=project.domain,
            prompts_count=len(prompts),
        )

        results_saved = 0
        errors: list[str] = []

        for i, prompt in enumerate(prompts):
            await log.ainfo("monitoring_prompt_start", prompt_index=i, prompt=prompt[:60])

            # ── Алиса (Playwright) ────────────────────────────────────────────
            alice_result = None
            try:
                alice_result = await scrape_alice(
                    prompt=prompt,
                    brand=brand,
                    headless=True,
                )
            except Exception as e:
                error_msg = f"Alice error for prompt {i}: {e}"
                errors.append(error_msg)
                await log.aerror("monitoring_alice_error", prompt_index=i, error=str(e))

            if alice_result is not None:
                db.add(MonitoringResult(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    prompt=prompt,
                    platform="alice",
                    mentioned=alice_result.mentioned,
                    position=alice_result.position,
                    sentiment=alice_result.sentiment,
                    response_text=alice_result.response_text,
                    checked_at=datetime.now(timezone.utc),
                ))
                await db.flush()
                results_saved += 1

            # Пауза между запросами к Алисе чтобы не триггерить rate-limit
            if i < len(prompts) - 1:
                await asyncio.sleep(_ALICE_DELAY)

            # ── ГигаЧат (API) ─────────────────────────────────────────────────
            gigachat_result = None
            try:
                gigachat_result = await query_gigachat(
                    prompt=prompt,
                    brand=brand,
                )
            except Exception as e:
                error_msg = f"GigaChat error for prompt {i}: {e}"
                errors.append(error_msg)
                await log.aerror("monitoring_gigachat_error", prompt_index=i, error=str(e))

            if gigachat_result is not None:
                db.add(MonitoringResult(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    prompt=prompt,
                    platform="gigachat",
                    mentioned=gigachat_result.mentioned,
                    position=gigachat_result.position,
                    sentiment=gigachat_result.sentiment,
                    response_text=gigachat_result.response_text,
                    checked_at=datetime.now(timezone.utc),
                ))
                await db.flush()
                results_saved += 1

            await asyncio.sleep(_GIGACHAT_DELAY)

        # Финальный commit всех изменений
        await db.commit()

        await log.ainfo(
            "monitoring_task_done",
            results_saved=results_saved,
            errors_count=len(errors),
        )

        return {
            "project_id": project_id,
            "project_name": project.name,
            "prompts_count": len(prompts),
            "results_saved": results_saved,
            "errors": errors,
        }


async def _run_monitoring_for_all_projects() -> dict:
    """
    Загружает все проекты с активной подпиской и запускает мониторинг.
    Проекты без промптов пропускаются.
    """
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Выбираем проекты пользователей с:
        # - подпиской которая ещё не истекла
        # - ИЛИ без даты истечения (trial/free пользователи)
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
        projects = list(rows)

    # Фильтруем проекты без промптов в Python
    active_projects = [p for p in projects if p.prompts]

    logger.info(
        "monitoring_all_projects_start",
        total_projects=len(projects),
        projects_with_prompts=len(active_projects),
    )

    dispatched: list[str] = []
    for project in active_projects:
        # Запускаем задачу в очередь — не ждём выполнения
        run_monitoring_for_project.apply_async(
            args=[str(project.id)],
            queue="monitoring",
        )
        dispatched.append(str(project.id))

    logger.info("monitoring_all_projects_dispatched", count=len(dispatched))
    return {"dispatched": len(dispatched), "project_ids": dispatched}


# ─── Celery задачи (sync обёртки) ─────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.monitoring_tasks.run_monitoring_for_project",
    bind=True,
    max_retries=2,
    default_retry_delay=120,   # повтор через 2 минуты
    queue="monitoring",
    time_limit=600,            # hard kill через 10 минут
    soft_time_limit=540,       # SoftTimeLimitExceeded за 9 минут (успеть сохранить)
)
def run_monitoring_for_project(self, project_id: str) -> dict:
    """
    Запускает полный мониторинг одного проекта.

    Args:
        project_id: UUID проекта в виде строки

    Returns:
        dict со статистикой выполнения

    Retries:
        До 2 раз при ошибках. Playwright-ошибки и сетевые сбои — ретраи.
        Если проект не найден — не ретраим (нет смысла).
    """
    log = logger.bind(
        task_id=self.request.id,
        project_id=project_id,
        attempt=self.request.retries + 1,
    )

    try:
        result = asyncio.run(_run_monitoring_for_project(project_id))

        # Не ретраим если проект не найден или нет промптов
        if result.get("error") == "project_not_found":
            return result
        if result.get("skipped"):
            return result

        return result

    except Exception as exc:
        logger.error(
            "monitoring_task_failed",
            project_id=project_id,
            attempt=self.request.retries + 1,
            error=str(exc),
        )
        # Ретраим с экспоненциальной задержкой
        raise self.retry(
            exc=exc,
            countdown=120 * (2 ** self.request.retries),
        )


@celery_app.task(
    name="app.tasks.monitoring_tasks.run_monitoring_for_all_projects",
    queue="default",
    time_limit=120,
)
def run_monitoring_for_all_projects() -> dict:
    """
    Celery Beat entry point для ежедневного мониторинга.
    Расписание: каждый день в 03:00 МСК (настроено в celery_app.py).

    Эта задача только диспатчит — не выполняет мониторинг напрямую.
    Каждый проект получает свою задачу run_monitoring_for_project в очереди.
    """
    try:
        return asyncio.run(_run_monitoring_for_all_projects())
    except Exception as exc:
        logger.error("monitoring_all_projects_failed", error=str(exc))
        raise
