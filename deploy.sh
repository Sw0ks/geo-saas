#!/usr/bin/env bash
# deploy.sh — деплой GEO Analytics SaaS на сервер
#
# Использование:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Что делает:
#   1. git pull origin main
#   2. docker-compose down
#   3. docker-compose up -d --build
#   4. alembic upgrade head (миграции БД)
#   5. docker-compose ps (статус сервисов)

set -euo pipefail   # прерываем при любой ошибке

# ── Цвета для вывода ──────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'   # No Color

info()    { echo -e "${GREEN}[deploy]${NC} $*"; }
warning() { echo -e "${YELLOW}[deploy]${NC} $*"; }
error()   { echo -e "${RED}[deploy]${NC} $*" >&2; exit 1; }

# ── Проверки окружения ────────────────────────────────────────────────────────
command -v docker        >/dev/null 2>&1 || error "docker не найден"
command -v docker-compose >/dev/null 2>&1 || \
  command -v docker      >/dev/null 2>&1 || error "docker-compose не найден"

# Поддерживаем как отдельный docker-compose, так и плагин docker compose
if command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    DC="docker compose"
fi

[ -f ".env" ]              || error ".env файл не найден. Скопируйте .env.example и заполните."
[ -f "docker-compose.yml" ] || error "docker-compose.yml не найден. Запустите из корня проекта."

info "Начинаем деплой на $(hostname) в $(date '+%Y-%m-%d %H:%M:%S')"
echo "────────────────────────────────────────────────────────────────"

# ── Шаг 1: git pull ───────────────────────────────────────────────────────────
info "Шаг 1/5 — Получаем последние изменения из репозитория..."
git pull origin main
echo ""

# ── Шаг 2: docker-compose down ───────────────────────────────────────────────
info "Шаг 2/5 — Останавливаем текущие контейнеры..."
$DC down --remove-orphans
echo ""

# ── Шаг 3: docker-compose up --build ─────────────────────────────────────────
info "Шаг 3/5 — Собираем образы и запускаем сервисы..."
$DC up -d --build
echo ""

# ── Ждём пока backend станет healthy ─────────────────────────────────────────
info "Ждём готовности backend (до 60 секунд)..."
TIMEOUT=60
ELAPSED=0
until $DC exec -T backend curl -sf http://localhost:8000/health >/dev/null 2>&1; do
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        warning "Таймаут ожидания backend. Проверьте логи: $DC logs backend"
        break
    fi
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    echo -n "."
done
echo ""

# ── Шаг 4: alembic upgrade head ──────────────────────────────────────────────
info "Шаг 4/5 — Применяем миграции базы данных..."
$DC exec -T backend alembic upgrade head
echo ""

# ── Шаг 5: docker-compose ps ─────────────────────────────────────────────────
info "Шаг 5/5 — Статус сервисов:"
echo "────────────────────────────────────────────────────────────────"
$DC ps
echo "────────────────────────────────────────────────────────────────"
echo ""

info "Деплой завершён успешно!"
info "Сайт доступен на: http://$(hostname -I | awk '{print $1}')"
