"""
Роутер мониторинга GEO-позиций.

Эндпоинты:
  POST /monitoring/check-alice       — разовая проверка одного промпта в Алисе
  POST /monitoring/check-gigachat    — разовая проверка одного промпта в ГигаЧате
  POST /monitoring/run               — запуск полного мониторинга проекта
  GET  /monitoring/{project_id}      — история результатов по проекту
  GET  /monitoring/{project_id}/stats — статистика упоминаний
"""
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.monitoring_result import MonitoringResult
from app.models.project import Project
from app.schemas.monitoring import (
    MonitoringResultResponse,
    MonitoringStats,
)
from app.services.alice_scraper import scrape_alice, scrape_alice_batch
from app.services.gigachat import query_gigachat, query_gigachat_batch

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


# ─── Вспомогательные схемы ────────────────────────────────────────────────────

class CheckAliceRequest(BaseModel):
    """Запрос на разовую проверку одного промпта в Алисе."""
    project_id: uuid.UUID
    prompt: str = Field(min_length=3, max_length=500, description="Промпт для Алисы")


class CheckAliceResponse(BaseModel):
    """Ответ на разовую проверку."""
    result: MonitoringResultResponse
    message: str


class CheckGigaChatRequest(BaseModel):
    """Запрос на разовую проверку одного промпта в ГигаЧате."""
    project_id: uuid.UUID
    prompt: str = Field(min_length=3, max_length=500, description="Промпт для ГигаЧата")


class CheckGigaChatResponse(BaseModel):
    """Ответ на разовую проверку ГигаЧата."""
    result: MonitoringResultResponse
    message: str


class RunMonitoringRequest(BaseModel):
    """Запрос на запуск полного мониторинга всех промптов проекта."""
    project_id: uuid.UUID
    platforms: list[str] = Field(
        default=["alice"],
        description="Платформы для проверки: 'alice', 'gigachat'",
    )


class RunMonitoringResponse(BaseModel):
    message: str
    project_id: uuid.UUID
    prompts_count: int


# ─── Вспомогательные функции ──────────────────────────────────────────────────

async def _get_project_or_404(
    project_id: uuid.UUID,
    user_id: str,
    db: AsyncSession,
) -> Project:
    """Получает проект и проверяет что он принадлежит пользователю."""
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


async def _save_monitoring_result(
    db: AsyncSession,
    project_id: uuid.UUID,
    prompt: str,
    platform: str,
    mentioned: bool,
    position: int | None,
    sentiment: str | None,
    response_text: str,
) -> MonitoringResult:
    """Сохраняет результат мониторинга в БД."""
    result = MonitoringResult(
        id=uuid.uuid4(),
        project_id=project_id,
        prompt=prompt,
        platform=platform,
        mentioned=mentioned,
        position=position,
        sentiment=sentiment,
        response_text=response_text,
        checked_at=datetime.now(timezone.utc),
    )
    db.add(result)
    await db.flush()
    return result


# ─── Фоновая задача полного мониторинга ───────────────────────────────────────

async def _run_full_monitoring_task(
    project_id: uuid.UUID,
    user_id: str,
    platforms: list[str],
) -> None:
    """
    Фоновая задача: прогоняет все промпты проекта через выбранные платформы.
    Запускается через BackgroundTasks FastAPI.
    В продакшене заменить на Celery задачу.
    """
    from app.core.database import AsyncSessionLocal

    log = logger.bind(project_id=str(project_id), platforms=platforms)
    await log.ainfo("full_monitoring_start")

    async with AsyncSessionLocal() as db:
        try:
            project = await db.get(Project, project_id)
            if not project:
                await log.aerror("monitoring_project_not_found")
                return

            prompts: list[str] = project.prompts or []
            if not prompts:
                await log.awarning("monitoring_no_prompts")
                return

            # Определяем бренд из домена проекта
            brand = project.name  # имя проекта как бренд

            # Алиса
            if "alice" in platforms:
                alice_results = await scrape_alice_batch(
                    prompts=prompts,
                    brand=brand,
                    delay_between=4.0,
                )
                for r in alice_results:
                    await _save_monitoring_result(
                        db=db,
                        project_id=project_id,
                        prompt=r.prompt,
                        platform="alice",
                        mentioned=r.mentioned,
                        position=r.position,
                        sentiment=r.sentiment,
                        response_text=r.response_text,
                    )

            # ГигаЧат
            if "gigachat" in platforms:
                gigachat_results = await query_gigachat_batch(
                    prompts=prompts,
                    brand=brand,
                    delay_between=2.0,
                )
                for r in gigachat_results:
                    await _save_monitoring_result(
                        db=db,
                        project_id=project_id,
                        prompt=r.prompt,
                        platform="gigachat",
                        mentioned=r.mentioned,
                        position=r.position,
                        sentiment=r.sentiment,
                        response_text=r.response_text,
                    )

            await db.commit()
            await log.ainfo(
                "full_monitoring_done",
                prompts_count=len(prompts),
            )

        except Exception as e:
            await log.aerror("full_monitoring_error", error=str(e))
            await db.rollback()


# ─── Эндпоинты ────────────────────────────────────────────────────────────────

@router.post(
    "/check-alice",
    response_model=CheckAliceResponse,
    status_code=status.HTTP_200_OK,
    summary="Разовая проверка промпта в Яндекс Алисе",
)
async def check_alice(
    body: CheckAliceRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CheckAliceResponse:
    """
    Отправляет один промпт в Алису и возвращает результат.

    - Проверяет что проект принадлежит пользователю
    - Запускает Playwright scraper
    - Сохраняет результат в БД
    - Возвращает данные мониторинга

    **Внимание:** запрос занимает 15–40 секунд (Playwright headless).
    Для регулярного мониторинга используй POST /monitoring/run.
    """
    project = await _get_project_or_404(body.project_id, user_id, db)

    log = logger.bind(
        project_id=str(project.id),
        user_id=user_id,
        prompt=body.prompt[:50],
    )
    await log.ainfo("check_alice_start")

    # Запускаем scraper
    try:
        scrape_result = await scrape_alice(
            prompt=body.prompt,
            brand=project.name,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Не удалось получить ответ от Алисы: {e}",
        )

    # Сохраняем в БД
    db_result = await _save_monitoring_result(
        db=db,
        project_id=project.id,
        prompt=body.prompt,
        platform="alice",
        mentioned=scrape_result.mentioned,
        position=scrape_result.position,
        sentiment=scrape_result.sentiment,
        response_text=scrape_result.response_text,
    )

    await log.ainfo(
        "check_alice_done",
        mentioned=scrape_result.mentioned,
        sentiment=scrape_result.sentiment,
    )

    mention_msg = (
        f"Бренд «{project.name}» упомянут на позиции {scrape_result.position}"
        if scrape_result.mentioned
        else f"Бренд «{project.name}» не упомянут в ответе Алисы"
    )

    return CheckAliceResponse(
        result=MonitoringResultResponse.model_validate(db_result),
        message=mention_msg,
    )


@router.post(
    "/check-gigachat",
    response_model=CheckGigaChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Разовая проверка промпта в ГигаЧате (Сбер)",
)
async def check_gigachat(
    body: CheckGigaChatRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CheckGigaChatResponse:
    """
    Отправляет один промпт в GigaChat API и возвращает результат.

    - Проверяет что проект принадлежит пользователю
    - Авторизуется через OAuth2 Сбера (токен кэшируется на 30 мин)
    - Сохраняет результат в БД
    - Возвращает данные мониторинга

    Требует заполненных переменных окружения:
        GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET
    """
    project = await _get_project_or_404(body.project_id, user_id, db)

    log = logger.bind(
        project_id=str(project.id),
        user_id=user_id,
        prompt=body.prompt[:50],
    )
    await log.ainfo("check_gigachat_start")

    try:
        gc_result = await query_gigachat(
            prompt=body.prompt,
            brand=project.name,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Не удалось получить ответ от ГигаЧата: {e}",
        )

    # Сохраняем в БД
    db_result = await _save_monitoring_result(
        db=db,
        project_id=project.id,
        prompt=body.prompt,
        platform="gigachat",
        mentioned=gc_result.mentioned,
        position=gc_result.position,
        sentiment=gc_result.sentiment,
        response_text=gc_result.response_text,
    )

    await log.ainfo(
        "check_gigachat_done",
        mentioned=gc_result.mentioned,
        sentiment=gc_result.sentiment,
    )

    mention_msg = (
        f"Бренд «{project.name}» упомянут на позиции {gc_result.position}"
        if gc_result.mentioned
        else f"Бренд «{project.name}» не упомянут в ответе ГигаЧата"
    )

    return CheckGigaChatResponse(
        result=MonitoringResultResponse.model_validate(db_result),
        message=mention_msg,
    )


@router.post(
    "/run",
    response_model=RunMonitoringResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запуск полного мониторинга всех промптов проекта",
)
async def run_monitoring(
    body: RunMonitoringRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> RunMonitoringResponse:
    """
    Запускает полный мониторинг в фоне.
    Прогоняет все промпты проекта через выбранные платформы.

    Возвращает 202 Accepted сразу — результаты появятся в GET /monitoring/{project_id}.
    """
    project = await _get_project_or_404(body.project_id, user_id, db)
    prompts_count = len(project.prompts or [])

    if prompts_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У проекта нет промптов для мониторинга. Добавьте их в настройках проекта.",
        )

    # Запускаем в фоне
    background_tasks.add_task(
        _run_full_monitoring_task,
        project_id=project.id,
        user_id=user_id,
        platforms=body.platforms,
    )

    await logger.ainfo(
        "monitoring_scheduled",
        project_id=str(project.id),
        prompts_count=prompts_count,
        platforms=body.platforms,
    )

    return RunMonitoringResponse(
        message="Мониторинг запущен. Результаты будут доступны через несколько минут.",
        project_id=project.id,
        prompts_count=prompts_count,
    )


@router.get(
    "/{project_id}",
    response_model=list[MonitoringResultResponse],
    summary="История результатов мониторинга по проекту",
)
async def get_monitoring_results(
    project_id: uuid.UUID,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[MonitoringResultResponse]:
    """
    Возвращает историю проверок для проекта.
    Можно фильтровать по платформе (?platform=alice).
    """
    await _get_project_or_404(project_id, user_id, db)

    query = (
        select(MonitoringResult)
        .where(MonitoringResult.project_id == project_id)
        .order_by(MonitoringResult.checked_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if platform:
        query = query.where(MonitoringResult.platform == platform)

    rows = await db.scalars(query)
    return [MonitoringResultResponse.model_validate(r) for r in rows]


@router.get(
    "/{project_id}/stats",
    response_model=MonitoringStats,
    summary="Статистика упоминаний по проекту",
)
async def get_monitoring_stats(
    project_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> MonitoringStats:
    """
    Агрегированная статистика: процент упоминаний, средняя позиция, тональность.
    """
    await _get_project_or_404(project_id, user_id, db)

    # Все результаты
    all_results = await db.scalars(
        select(MonitoringResult).where(MonitoringResult.project_id == project_id)
    )
    results = list(all_results)

    total = len(results)
    if total == 0:
        return MonitoringStats(
            project_id=project_id,
            total_checks=0,
            mentioned_count=0,
            mention_rate=0.0,
            avg_position=None,
            sentiment_breakdown={"positive": 0, "neutral": 0, "negative": 0},
            by_platform={},
        )

    mentioned = [r for r in results if r.mentioned]
    positions = [r.position for r in mentioned if r.position is not None]

    sentiment_breakdown = {"positive": 0, "neutral": 0, "negative": 0}
    for r in mentioned:
        if r.sentiment in sentiment_breakdown:
            sentiment_breakdown[r.sentiment] += 1

    # Статистика по платформам
    by_platform: dict[str, dict] = {}
    for platform in {"alice", "gigachat"}:
        platform_results = [r for r in results if r.platform == platform]
        platform_mentioned = [r for r in platform_results if r.mentioned]
        by_platform[platform] = {
            "total": len(platform_results),
            "mentioned": len(platform_mentioned),
            "mention_rate": (
                round(len(platform_mentioned) / len(platform_results), 3)
                if platform_results
                else 0.0
            ),
        }

    return MonitoringStats(
        project_id=project_id,
        total_checks=total,
        mentioned_count=len(mentioned),
        mention_rate=round(len(mentioned) / total, 3),
        avg_position=round(sum(positions) / len(positions), 1) if positions else None,
        sentiment_breakdown=sentiment_breakdown,
        by_platform=by_platform,
    )
