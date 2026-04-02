"""Добавление поля tracker_token в таблицу projects

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-01 00:01:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем колонку — сначала nullable, потом заполняем, потом делаем NOT NULL
    op.add_column(
        "projects",
        sa.Column("tracker_token", sa.String(64), nullable=True),
    )

    # Генерируем уникальные токены для всех существующих проектов
    op.execute(
        """
        UPDATE projects
        SET tracker_token = encode(gen_random_bytes(32), 'base64')
        WHERE tracker_token IS NULL
        """
    )

    # Теперь можно сделать NOT NULL и уникальный индекс
    op.alter_column("projects", "tracker_token", nullable=False)
    op.create_index(
        op.f("ix_projects_tracker_token"),
        "projects",
        ["tracker_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_tracker_token"), table_name="projects")
    op.drop_column("projects", "tracker_token")
