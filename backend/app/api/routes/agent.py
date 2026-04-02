"""
Роутер агента GEO-оптимизации.

Эндпоинты:
  POST /agent/generate-plan        — запустить агента, получить план действий
  GET  /agent/plan/{project_id}    — последний план для проекта
  GET  /agent/plans/{project_id}   — история всех планов проекта
  PATCH /agent/plan/{plan_id}/status — обновить статус задачи
"""
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.monitoring_result import MonitoringResult
from app.models.project import Project
from app.models.subscription import ActionPlan, GeneratedContent
from app.schemas.content import (
    ActionPlanResponse,
    ActionPlanUpdateStatus,
    ContentGenerateRequest,
    ContentUpdateStatus,
    GeneratedContentResponse,
)
from app.services.claude_agent import (
    ContentInput,
    build_agent_input,
    generate_action_plan,
    generate_content,
    suggest_prompts,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ─── Вспомогательные схемы ────────────────────────────────────────────────────

class GeneratePlanRequest(BaseModel):
    """Запрос на генерацию плана действий."""
    project_id: uuid.UUID


class GeneratePlanResponse(BaseModel):
    """Ответ с готовым планом действий."""
    plan: ActionPlanResponse
    tasks_count: int
    summary: str
    message: str


# ─── Вспомогательные функции ─────────────────────────────────────────────────

async def _get_project_or_403(
    project_id: uuid.UUID,
    user_id: str,
    db: AsyncSession,
) -> Project:
    """Возвращает проект если он принадлежит пользователю."""
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


async def _get_recent_monitoring(
    project_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 30,
) -> list[dict]:
    """
    Загружает последние результаты мониторинга для передачи агенту.
    Берём последние N результатов — достаточно для анализа.
    """
    rows = await db.scalars(
        select(MonitoringResult)
        .where(MonitoringResult.project_id == project_id)
        .order_by(MonitoringResult.checked_at.desc())
        .limit(limit)
    )
    return [
        {
            "prompt": r.prompt,
            "platform": r.platform,
            "mentioned": r.mentioned,
            "position": r.position,
            "sentiment": r.sentiment,
            "response_text": r.response_text,
        }
        for r in rows
    ]


# ─── Эндпоинты ────────────────────────────────────────────────────────────────

@router.post(
    "/generate-plan",
    response_model=GeneratePlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Сгенерировать план GEO-оптимизации через Claude AI",
)
async def generate_plan(
    body: GeneratePlanRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GeneratePlanResponse:
    """
    Запускает Claude-агента, который анализирует данные мониторинга
    и составляет конкретный план действий для улучшения GEO-позиций.

    Алгоритм:
    1. Загружает последние результаты мониторинга проекта
    2. Передаёт данные в Claude API (claude-sonnet-4-6)
    3. Получает JSON с задачами (максимум 7, по приоритету)
    4. Сохраняет план в таблицу action_plans
    5. Возвращает готовый план

    **Время выполнения:** 5–15 секунд (запрос к Claude API).

    Требует данных мониторинга — сначала запустите
    POST /monitoring/run или POST /monitoring/check-alice.
    """
    project = await _get_project_or_403(body.project_id, user_id, db)

    log = logger.bind(project_id=str(project.id), user_id=user_id)
    await log.ainfo("generate_plan_start")

    # Загружаем данные мониторинга
    monitoring_data = await _get_recent_monitoring(project.id, db)

    # Предупреждаем если данных нет — план всё равно генерируем (общие рекомендации)
    if not monitoring_data:
        await log.awarning("generate_plan_no_monitoring_data")

    # Собираем входные данные для агента
    agent_input = build_agent_input(
        project_id=project.id,
        project_name=project.name,
        project_domain=project.domain,
        project_competitors=project.competitors or [],
        project_prompts=project.prompts or [],
        monitoring_results=monitoring_data,
    )

    # Запускаем агента
    try:
        plan_result = await generate_action_plan(agent_input)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка Claude API: {e}",
        )

    # Сохраняем план в БД
    action_plan = ActionPlan(
        id=uuid.uuid4(),
        project_id=project.id,
        tasks_json=plan_result.to_tasks_json(),
        generated_at=datetime.now(timezone.utc),
        status="new",
    )
    # Кладём summary в первый элемент tasks_json как мета-поле
    # (или можно добавить отдельную колонку в следующей миграции)
    action_plan.tasks_json = [
        {"_summary": plan_result.summary},
        *plan_result.to_tasks_json(),
    ]
    db.add(action_plan)
    await db.flush()

    await log.ainfo(
        "generate_plan_done",
        plan_id=str(action_plan.id),
        tasks_count=len(plan_result.tasks),
    )

    return GeneratePlanResponse(
        plan=ActionPlanResponse.model_validate(action_plan),
        tasks_count=len(plan_result.tasks),
        summary=plan_result.summary,
        message=f"План сгенерирован: {len(plan_result.tasks)} задач для «{project.name}»",
    )


@router.get(
    "/plan/{project_id}",
    response_model=GeneratePlanResponse,
    summary="Получить последний план действий для проекта",
)
async def get_latest_plan(
    project_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GeneratePlanResponse:
    """
    Возвращает последний сгенерированный план для проекта.
    Планы сортируются по дате генерации — возвращается самый свежий.
    """
    await _get_project_or_403(project_id, user_id, db)

    plan = await db.scalar(
        select(ActionPlan)
        .where(ActionPlan.project_id == project_id)
        .order_by(ActionPlan.generated_at.desc())
        .limit(1)
    )

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="План ещё не сгенерирован. Запустите POST /agent/generate-plan",
        )

    # Извлекаем summary из tasks_json
    tasks = plan.tasks_json or []
    summary = ""
    task_items = []
    for item in tasks:
        if "_summary" in item:
            summary = item["_summary"]
        else:
            task_items.append(item)

    return GeneratePlanResponse(
        plan=ActionPlanResponse.model_validate(plan),
        tasks_count=len(task_items),
        summary=summary,
        message="Последний план действий",
    )


@router.get(
    "/plans/{project_id}",
    response_model=list[ActionPlanResponse],
    summary="История всех планов проекта",
)
async def get_plan_history(
    project_id: uuid.UUID,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[ActionPlanResponse]:
    """
    Возвращает историю всех сгенерированных планов для проекта.
    Отсортировано от новых к старым.
    """
    await _get_project_or_403(project_id, user_id, db)

    plans = await db.scalars(
        select(ActionPlan)
        .where(ActionPlan.project_id == project_id)
        .order_by(ActionPlan.generated_at.desc())
        .limit(limit)
    )
    return [ActionPlanResponse.model_validate(p) for p in plans]


@router.patch(
    "/plan/{plan_id}/status",
    response_model=ActionPlanResponse,
    summary="Обновить статус плана (new → in_progress → done)",
)
async def update_plan_status(
    plan_id: uuid.UUID,
    body: ActionPlanUpdateStatus,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ActionPlanResponse:
    """
    Обновляет статус плана действий.
    Используется дашбордом когда клиент начинает/завершает работу над планом.
    """
    plan = await db.get(ActionPlan, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="План не найден",
        )

    # Проверяем доступ через проект
    await _get_project_or_403(plan.project_id, user_id, db)

    plan.status = body.status
    await db.flush()

    await logger.ainfo(
        "plan_status_updated",
        plan_id=str(plan_id),
        new_status=body.status,
    )

    return ActionPlanResponse.model_validate(plan)


# ════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ КОНТЕНТА
# ════════════════════════════════════════════════════════════════════════════

@router.post(
    "/generate-content",
    response_model=GeneratedContentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Сгенерировать контент (статья / FAQ / описание) через Claude AI",
)
async def generate_content_endpoint(
    body: ContentGenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GeneratedContentResponse:
    """
    Генерирует SEO/GEO-оптимизированный контент через Claude API.

    Типы:
    - **article** — статья для блога 800–1200 слов, с FAQ-блоком в конце
    - **faq** — 5–10 пар вопрос/ответ в формате который Алиса цитирует
    - **description** — описание товара/услуги 150–200 слов

    Передайте `task_id` чтобы агент учёл контекст задачи из плана действий.

    **Время выполнения:** 5–20 секунд.
    """
    project = await _get_project_or_403(body.project_id, user_id, db)

    log = logger.bind(
        project_id=str(project.id),
        content_type=body.type,
        topic=body.topic,
    )
    await log.ainfo("generate_content_start")

    # Если передан task_id — загружаем текст задачи для контекста
    task_context: str | None = None
    if body.task_id is not None:
        plan = await db.scalar(
            select(ActionPlan)
            .where(ActionPlan.project_id == project.id)
            .order_by(ActionPlan.generated_at.desc())
            .limit(1)
        )
        if plan and plan.tasks_json:
            # Ищем задачу по priority (используем task_id как число через int())
            for task in plan.tasks_json:
                if isinstance(task, dict) and not task.get("_summary"):
                    task_context = (
                        f"{task.get('title', '')}\n{task.get('description', '')}"
                    ).strip()
                    break

    content_inp = ContentInput(
        project_name=project.name,
        project_domain=project.domain,
        content_type=body.type,
        topic=body.topic,
        task_context=task_context,
        additional_context=body.additional_context,
    )

    try:
        result = await generate_content(content_inp)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка Claude API: {e}",
        )

    # Сохраняем в generated_content
    content_record = GeneratedContent(
        id=uuid.uuid4(),
        project_id=project.id,
        type=body.type,
        title=result.title,
        body=result.body,
        status="draft",
    )
    db.add(content_record)
    await db.flush()

    await log.ainfo(
        "generate_content_done",
        content_id=str(content_record.id),
        word_count=result.word_count,
    )

    return GeneratedContentResponse.model_validate(content_record)


@router.get(
    "/content/{project_id}",
    response_model=list[GeneratedContentResponse],
    summary="Список сгенерированного контента для проекта",
)
async def list_content(
    project_id: uuid.UUID,
    type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[GeneratedContentResponse]:
    """
    Возвращает весь контент проекта с опциональными фильтрами по type и status.

    - `type`: article | faq | description
    - `status`: draft | published
    """
    await _get_project_or_403(project_id, user_id, db)

    query = (
        select(GeneratedContent)
        .where(GeneratedContent.project_id == project_id)
        .order_by(GeneratedContent.created_at.desc())
        .limit(limit)
    )

    if type is not None:
        query = query.where(GeneratedContent.type == type)
    if status is not None:
        query = query.where(GeneratedContent.status == status)

    rows = await db.scalars(query)
    return [GeneratedContentResponse.model_validate(r) for r in rows]


@router.patch(
    "/content/{content_id}/status",
    response_model=GeneratedContentResponse,
    summary="Сменить статус контента (draft → published)",
)
async def update_content_status(
    content_id: uuid.UUID,
    body: ContentUpdateStatus,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GeneratedContentResponse:
    """
    Переключает статус контента между draft и published.
    Используется когда клиент опубликовал материал на сайте.
    """
    content = await db.get(GeneratedContent, content_id)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Контент не найден",
        )

    # Проверяем доступ через проект
    await _get_project_or_403(content.project_id, user_id, db)

    content.status = body.status
    await db.flush()

    return GeneratedContentResponse.model_validate(content)


# ════════════════════════════════════════════════════════════════════════════
# ПРЕДЛОЖЕНИЕ ПРОМПТОВ (онбординг)
# ════════════════════════════════════════════════════════════════════════════

class SuggestPromptsRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Название бизнеса")
    description: str = Field(..., min_length=5, max_length=1000, description="Описание бизнеса (1-2 предложения)")


class SuggestPromptsResponse(BaseModel):
    prompts: list[str]


@router.post(
    "/suggest-prompts",
    response_model=SuggestPromptsResponse,
    summary="Предложить промпты для мониторинга на основе описания бизнеса",
)
async def suggest_monitoring_prompts(
    body: SuggestPromptsRequest,
    user_id: str = Depends(get_current_user_id),
) -> SuggestPromptsResponse:
    """
    Генерирует 5 промптов для мониторинга через Claude AI.
    Используется в онбординге — помогает новому пользователю
    сразу получить релевантные запросы для своего бизнеса.

    Возвращает список из 5 реалистичных поисковых запросов на русском языке.
    **Время выполнения:** 3–8 секунд.
    """
    try:
        prompts = await suggest_prompts(
            business_name=body.name,
            business_description=body.description,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка Claude API: {e}",
        )

    return SuggestPromptsResponse(prompts=prompts)
