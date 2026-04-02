"""
Роутер проектов.

Эндпоинты:
  GET  /projects            — список проектов текущего пользователя
  POST /projects            — создать проект (с проверкой лимита тарифа)
  GET  /projects/{id}       — получить проект
  PATCH /projects/{id}      — обновить проект
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.yokassa import PLAN_DETAILS

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


async def _get_project_owned(
    project_id: uuid.UUID,
    user_id: str,
    db: AsyncSession,
) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    if str(project.user_id) != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к проекту")
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    """Список всех проектов текущего пользователя."""
    rows = await db.scalars(
        select(Project)
        .where(Project.user_id == uuid.UUID(user_id))
        .order_by(Project.created_at.asc())
    )
    return [ProjectResponse.model_validate(p) for p in rows]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Создаёт новый проект.
    Проверяет лимит проектов для тарифа пользователя.
    """
    # Получаем пользователя чтобы знать тариф
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    # Считаем текущее количество проектов
    count = await db.scalar(
        select(func.count(Project.id)).where(Project.user_id == uuid.UUID(user_id))
    )

    plan_info = PLAN_DETAILS.get(user.subscription_plan, PLAN_DETAILS["start"])
    max_projects: int = plan_info["max_projects"]

    if (count or 0) >= max_projects:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Достигнут лимит проектов ({max_projects}) для тарифа «{plan_info['name']}». "
                f"Перейдите на более высокий тариф."
            ),
        )

    project = Project(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        name=body.name,
        domain=body.domain,
        competitors=body.competitors,
        prompts=body.prompts,
    )
    db.add(project)
    await db.flush()

    await logger.ainfo(
        "project_created",
        project_id=str(project.id),
        user_id=user_id,
        domain=project.domain,
    )

    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Получить проект по ID."""
    project = await _get_project_owned(project_id, user_id, db)
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Обновить название, домен, конкурентов или промпты проекта."""
    project = await _get_project_owned(project_id, user_id, db)

    if body.name is not None:
        project.name = body.name
    if body.domain is not None:
        project.domain = body.domain
    if body.competitors is not None:
        project.competitors = body.competitors
    if body.prompts is not None:
        project.prompts = body.prompts

    await db.flush()
    return ProjectResponse.model_validate(project)
