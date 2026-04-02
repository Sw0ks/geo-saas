# GEO Analytics SaaS

Сервис мониторинга AI-видимости для малого бизнеса в России.
Отслеживает упоминания бренда в ответах Яндекс Алисы и ГигаЧата,
генерирует план действий и контент через Claude API.

---

## Стек

| Слой | Технология |
|------|-----------|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 async |
| База данных | PostgreSQL 16 |
| Очереди | Redis 7 · Celery |
| Мониторинг | Playwright (Алиса) · GigaChat API · YandexGPT API |
| AI-агент | Claude API (`claude-sonnet-4-6`) |
| Frontend | Next.js 14 · TypeScript · Tailwind CSS · NextAuth.js |
| Proxy | Nginx |
| Деплой | Docker · docker-compose |

---

## Локальный запуск

### 1. Требования

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) ≥ 24
- Git

### 2. Клонирование и настройка

```bash
git clone https://github.com/your-org/geo-saas.git
cd geo-saas
```

Заполните переменные окружения:

```bash
cp .env .env.local   # или отредактируйте .env напрямую
```

Минимальный набор для локального запуска:

```env
DATABASE_URL=postgresql+asyncpg://geo_user:geo_pass@postgres/geo_db
REDIS_URL=redis://redis:6379

ANTHROPIC_API_KEY=sk-ant-...
YANDEX_GPT_API_KEY=...
YANDEX_CLOUD_FOLDER_ID=...
GIGACHAT_API_KEY=...

JWT_SECRET=any-random-32-char-string
NEXTAUTH_SECRET=any-random-32-char-string
NEXTAUTH_URL=http://localhost:3000
```

### 3. Запуск

```bash
docker-compose up -d --build
```

Первый запуск занимает 3–5 минут (скачивание образов, установка зависимостей).

### 4. Применение миграций

```bash
docker-compose exec backend alembic upgrade head
```

### 5. Проверка

| Сервис | URL |
|--------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/docs |
| Backend health | http://localhost:8000/health |

### 6. Остановка

```bash
docker-compose down          # остановить, сохранить данные
docker-compose down -v       # остановить + удалить volumes (сброс БД)
```

### Полезные команды

```bash
# Логи конкретного сервиса
docker-compose logs -f backend
docker-compose logs -f celery-worker

# Запустить shell внутри backend-контейнера
docker-compose exec backend bash

# Создать новую миграцию после изменения моделей
docker-compose exec backend alembic revision --autogenerate -m "описание"

# Статус всех сервисов
docker-compose ps
```

---

## Деплой на сервер

### Требования к серверу

- Ubuntu 22.04 / 24.04
- CPU: 2 ядра минимум (4 рекомендуется)
- RAM: 4 GB минимум (8 GB рекомендуется — Playwright потребляет ~500 MB)
- Диск: 20 GB
- Открытые порты: 80, 443

### 1. Подготовка сервера

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER
newgrp docker

# Установка docker-compose
apt install -y docker-compose-plugin
# или старая версия:
# curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
#   -o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose

# Установка git и certbot
apt install -y git certbot python3-certbot-nginx
```

### 2. Клонирование проекта

```bash
cd /opt
git clone https://github.com/your-org/geo-saas.git
cd geo-saas
```

### 3. Настройка окружения

```bash
nano .env
```

Заполните все переменные, особенно:
- `DATABASE_URL` — используйте `postgres` как hostname (имя сервиса в Docker)
- `REDIS_URL` — используйте `redis` как hostname
- `DOMAIN` — реальный домен сервера
- `NEXTAUTH_URL` — `https://yourdomain.ru`
- `JWT_SECRET` и `NEXTAUTH_SECRET` — случайные строки (минимум 32 символа)

```bash
# Генерация случайного секрета
openssl rand -hex 32
```

### 4. Запуск деплоя

```bash
chmod +x deploy.sh
./deploy.sh
```

Скрипт выполнит: git pull → docker-compose down → up --build → alembic upgrade head → ps.

### 5. Настройка домена

Укажите A-запись домена на IP вашего сервера, затем дождитесь распространения DNS (обычно 5–30 минут).

Проверьте:

```bash
curl http://yourdomain.ru/health
```

---

## SSL-сертификат через Certbot

### 1. Получение сертификата

Certbot должен временно остановить Nginx, чтобы занять порт 80:

```bash
# Остановить nginx-контейнер
docker-compose stop nginx

# Получить сертификат (standalone режим)
certbot certonly --standalone \
  -d yourdomain.ru \
  -d www.yourdomain.ru \
  --email your@email.ru \
  --agree-tos \
  --non-interactive

# Сертификат будет в /etc/letsencrypt/live/yourdomain.ru/
```

### 2. Прокинуть сертификаты в контейнер

В `docker-compose.yml` у сервиса `nginx` уже есть volume `nginx_certs:/etc/nginx/certs`.
Скопируйте сертификаты туда:

```bash
# Найти путь к volume
VOLUME_PATH=$(docker volume inspect geo-saas_nginx_certs --format '{{ .Mountpoint }}')

cp /etc/letsencrypt/live/yourdomain.ru/fullchain.pem  "$VOLUME_PATH/"
cp /etc/letsencrypt/live/yourdomain.ru/privkey.pem    "$VOLUME_PATH/"
chmod 600 "$VOLUME_PATH/privkey.pem"
```

### 3. Включить HTTPS в nginx.conf

Раскомментируйте блок HTTPS в `nginx.conf`:

```nginx
# Редирект HTTP → HTTPS
server {
    listen 80;
    server_name yourdomain.ru;
    return 301 https://$host$request_uri;
}

# HTTPS-сервер
server {
    listen 443 ssl http2;
    server_name yourdomain.ru;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ...
}
```

Обновите `.env`:
```env
NEXTAUTH_URL=https://yourdomain.ru
DOMAIN=yourdomain.ru
```

Перезапустите:
```bash
./deploy.sh
```

### 4. Автообновление сертификата

Let's Encrypt выдаёт сертификаты на 90 дней. Настройте cron для автообновления:

```bash
crontab -e
```

Добавьте строку:

```cron
0 3 * * 1 certbot renew --pre-hook "docker-compose -f /opt/geo-saas/docker-compose.yml stop nginx" \
           --post-hook "cp /etc/letsencrypt/live/yourdomain.ru/*.pem $(docker volume inspect geo-saas_nginx_certs --format '{{ .Mountpoint }}')/ && docker-compose -f /opt/geo-saas/docker-compose.yml start nginx" \
           --quiet
```

Проверьте что обновление работает:

```bash
certbot renew --dry-run
```

---

## Мониторинг и обслуживание

### Просмотр логов

```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f celery-worker
docker-compose logs -f backend
```

### Перезапуск одного сервиса

```bash
docker-compose restart backend
docker-compose restart celery-worker
```

### Резервное копирование БД

```bash
docker-compose exec postgres pg_dump -U geo_user geo_db > backup_$(date +%Y%m%d).sql
```

### Восстановление БД

```bash
docker-compose exec -T postgres psql -U geo_user geo_db < backup_20250101.sql
```

---

## Структура проекта

```
geo-saas/
├── backend/              # FastAPI приложение
│   ├── app/
│   │   ├── api/routes/  # Эндпоинты (auth, projects, monitoring, agent, billing, crawler)
│   │   ├── models/      # SQLAlchemy модели
│   │   ├── schemas/     # Pydantic v2 схемы
│   │   ├── services/    # Бизнес-логика (alice, gigachat, claude, email, yokassa)
│   │   ├── tasks/       # Celery задачи (monitoring, content, email)
│   │   └── core/        # Config, DB, Security, Celery, Middleware
│   ├── alembic/         # Миграции БД
│   └── Dockerfile
├── frontend/             # Next.js 14 приложение
│   ├── app/             # App Router (dashboard, auth, landing)
│   ├── components/      # UI компоненты
│   └── Dockerfile
├── snippets/             # Трекер-сниппеты для клиентских сайтов
│   ├── tracker_fastapi.py
│   ├── tracker_django.py
│   ├── tracker_flask.py
│   └── tracker.php
├── docker-compose.yml
├── nginx.conf
├── deploy.sh
└── .env
```
