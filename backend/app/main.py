"""
Точка входа FastAPI приложения.
Подключает все роутеры, настраивает CORS, middleware и логирование.
"""
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, monitoring, agent
from app.api.routes.billing import router as billing_router
from app.api.routes.projects import router as projects_router
from app.api.routes.crawler import router as crawler_track_router
from app.api.routes.crawler import dashboard_router as crawler_dashboard_router
from app.core.config import settings
from app.core.subscription_middleware import SubscriptionMiddleware

# Настройка structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.debug else structlog.processors.JSONRenderer(),
    ]
)

app = FastAPI(
    title="GEO Analytics SaaS",
    description="Мониторинг упоминаний бизнеса в Алисе и ГигаЧате",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,    # Swagger только в debug
    redoc_url="/redoc" if settings.debug else None,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"https://{settings.domain}",
        "http://localhost:3000",   # Next.js dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Middleware проверки подписки ---
# Срабатывает на /api/v1/monitoring/* и /api/v1/agent/* — возвращает 402 при нарушении
app.add_middleware(SubscriptionMiddleware)

# --- Роутеры ---
app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(monitoring.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")

# Трекер: GET /v1/track — без префикса /api (вызывается сниппетом клиента)
app.include_router(crawler_track_router)
# Дашборд краулера: GET /api/v1/crawler/* — с JWT авторизацией
app.include_router(crawler_dashboard_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Проверка работоспособности сервера."""
    return {"status": "ok", "version": "0.1.0"}
