"""
Celery-приложение с конфигурацией для GEO Analytics SaaS.

Broker и backend: Redis (REDIS_URL из .env)
Timezone: Europe/Moscow
Beat schedule:
  - 03:00 МСК — ежедневный мониторинг всех активных проектов
  - 04:00 МСК — ежедневная генерация планов для проектов без свежего плана
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "geo_saas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Регистрируем модули с задачами
    include=[
        "app.tasks.monitoring_tasks",
        "app.tasks.content_tasks",
        "app.tasks.email_tasks",
    ],
)

celery_app.conf.update(
    # ── Часовой пояс ──────────────────────────────────────────────────────────
    timezone="Europe/Moscow",
    enable_utc=True,

    # ── Сериализация ──────────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Поведение задач ───────────────────────────────────────────────────────
    task_track_started=True,
    task_acks_late=True,           # подтверждаем задачу только после завершения
    worker_prefetch_multiplier=1,  # не брать следующую задачу пока не закончена текущая
                                   # важно для тяжёлых задач (Playwright, Claude API)

    # ── Хранение результатов ──────────────────────────────────────────────────
    result_expires=60 * 60 * 24,   # хранить результаты 24 часа

    # ── Расписание (Celery Beat) ───────────────────────────────────────────────
    beat_schedule={
        # Мониторинг всех проектов каждый день в 03:00 МСК
        "daily-monitoring-3am-msk": {
            "task": "app.tasks.monitoring_tasks.run_monitoring_for_all_projects",
            "schedule": crontab(hour=3, minute=0),
            "options": {"queue": "monitoring"},
        },
        # Генерация планов для проектов без свежего плана каждый день в 04:00 МСК
        "daily-plans-4am-msk": {
            "task": "app.tasks.content_tasks.generate_daily_plans_for_all",
            "schedule": crontab(hour=4, minute=0),
            "options": {"queue": "content"},
        },
        # Еженедельный отчёт по email — каждый понедельник в 09:00 МСК
        "weekly-email-report-monday-9am-msk": {
            "task": "app.tasks.email_tasks.send_weekly_reports",
            "schedule": crontab(hour=9, minute=0, day_of_week=1),
            "options": {"queue": "default"},
        },
    },

    # ── Очереди ───────────────────────────────────────────────────────────────
    # monitoring — тяжёлые задачи (Playwright + Claude)
    # content    — генерация текстов (только Claude API)
    # default    — всё остальное
    task_default_queue="default",
)
