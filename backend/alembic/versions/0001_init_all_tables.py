"""Создание всех таблиц: users, projects, monitoring_results, crawler_events, action_plans, generated_content

Revision ID: 0001
Revises:
Create Date: 2026-04-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("subscription_plan", sa.String(20), nullable=False, server_default="start"),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("competitors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("prompts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)

    # --- monitoring_results ---
    op.create_table(
        "monitoring_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("mentioned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_monitoring_results_project_id"),
        "monitoring_results",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_monitoring_results_platform"),
        "monitoring_results",
        ["platform"],
        unique=False,
    )
    op.create_index(
        op.f("ix_monitoring_results_checked_at"),
        "monitoring_results",
        ["checked_at"],
        unique=False,
    )

    # --- crawler_events ---
    op.create_table(
        "crawler_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bot_name", sa.String(50), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("url_path", sa.String(2048), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "visited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crawler_events_project_id"),
        "crawler_events",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawler_events_bot_name"),
        "crawler_events",
        ["bot_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawler_events_visited_at"),
        "crawler_events",
        ["visited_at"],
        unique=False,
    )

    # --- action_plans ---
    op.create_table(
        "action_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tasks_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_action_plans_project_id"),
        "action_plans",
        ["project_id"],
        unique=False,
    )

    # --- generated_content ---
    op.create_table(
        "generated_content",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_generated_content_project_id"),
        "generated_content",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_content_type"),
        "generated_content",
        ["type"],
        unique=False,
    )


def downgrade() -> None:
    # Удаляем в обратном порядке (учитываем FK)
    op.drop_table("generated_content")
    op.drop_table("action_plans")
    op.drop_table("crawler_events")
    op.drop_table("monitoring_results")
    op.drop_table("projects")
    op.drop_table("users")
