# CLAUDE.md — GEO Analytics SaaS (Russian Market)

## Что это за проект

SaaS-платформа для малого бизнеса в России. Помогает владельцам магазинов и сайтов
появляться в ответах Алисы AI и ГигаЧата — и понимать что для этого делать.

Аналоги: peec.ai + tryprofound — но для русского рынка (Яндекс Алиса, ГигаЧат).

Целевой клиент: владелец малого бизнеса, не технарь, платит подписку.

---

## Стек

### Бэкенд
- **Python 3.12** + **FastAPI** (async)
- **PostgreSQL** (Timeweb Cloud managed)
- **Redis** (очереди задач через Celery)
- **Playwright** (scraping Алисы — UI scraping, не API)
- **Httpx** (async HTTP запросы к API)
- Деплой: **Timeweb Cloud VPS** (Ubuntu 24), Docker + docker-compose

### Фронтенд
- **Next.js 14** (App Router)
- **TypeScript**
- **Tailwind CSS**
- **NextAuth.js** (авторизация)
- **SWR** (data fetching)
- Деплой: тот же VPS через Nginx reverse proxy

### Внешние API
- **Claude API** (`claude-sonnet-4-6`) — агент, анализ, план действий, генерация контента
- **YandexGPT API** (через Yandex Cloud) — мониторинг ответов Алисы
- **GigaChat API** (Сбер) — мониторинг ГигаЧата
- **ЮKassa** — приём платежей (подписки)

---

## Структура проекта

```
/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── projects.py
│   │   │       ├── monitoring.py
│   │   │       ├── crawler.py
│   │   │       ├── agent.py
│   │   │       └── billing.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── monitoring_result.py
│   │   │   ├── crawler_event.py
│   │   │   └── subscription.py
│   │   ├── services/
│   │   │   ├── alice_scraper.py
│   │   │   ├── yandexgpt.py
│   │   │   ├── gigachat.py
│   │   │   ├── claude_agent.py
│   │   │   └── yokassa.py
│   │   ├── tasks/
│   │   │   ├── monitoring_tasks.py
│   │   │   └── content_tasks.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── security.py
│   │   └── schemas/
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   └── dashboard/
│   │       ├── page.tsx
│   │       ├── projects/page.tsx
│   │       ├── monitoring/page.tsx
│   │       ├── crawler/page.tsx
│   │       ├── plan/page.tsx
│   │       └── content/page.tsx
│   ├── components/
│   │   ├── ui/
│   │   ├── charts/
│   │   └── snippet/
│   ├── lib/
│   │   ├── api.ts
│   │   └── auth.ts
│   └── package.json
├── snippets/
│   ├── tracker_fastapi.py
│   ├── tracker_django.py
│   ├── tracker_flask.py
│   └── tracker.php
├── docker-compose.yml
├── nginx.conf
└── CLAUDE.md
```

---

## Модули продукта

### Модуль 1 — GEO мониторинг
Ежедневно прогоняем промпты через Алису (Playwright) и ГигаЧат (API).
Фиксируем: упоминается ли бренд, на какой позиции, тональность.
Сравниваем с конкурентами которых указал клиент.

**AI боты которые отслеживаем:**
- `AliceBot` — Яндекс Алиса
- `YandexBot` — Яндекс индексация
- `GigaBot` — ГигаЧат Сбера
- `GPTBot` — OpenAI
- `ClaudeBot` / `anthropic-ai` — Anthropic
- `PerplexityBot` — Perplexity

### Модуль 2 — AI краулер трекер
Клиент вставляет сниппет на сайт (Python middleware или PHP).
Фиксируем каждый визит AI бота: какой бот, когда, какую страницу.
Верифицируем IP по официальным диапазонам Яндекса.

**Сниппеты в папке `/snippets/`:**
- `tracker_fastapi.py` — FastAPI/Starlette middleware
- `tracker_django.py` — Django middleware
- `tracker_flask.py` — Flask хук + универсальная функция `track_if_bot()`
- `tracker.php` — PHP для WordPress / Bitrix / самописных сайтов

Все сниппеты отправляют данные на `GET /v1/track` нашего бэкенда.
Timeout всегда 1 секунда — не замедляем сайт клиента.
Ошибки глотаются молча (`except Exception: pass`) — не ломаем сайт клиента.

**Эндпоинт трекера:**
```
GET /v1/track?token=CLIENT_TOKEN&url=/path&bot=AliceBot&host=site.ru
```
Принимает данные, верифицирует токен, сохраняет в `crawler_events`.

### Модуль 3 — Агент (план действий)
Claude API (`claude-sonnet-4-6`) получает данные мониторинга и выдаёт конкретный план:
- Какие статьи написать (темы + структура)
- Какие FAQ добавить на сайт
- Где разместить упоминания бренда
- Что улучшить технически (schema.org, скорость)
- Как исправить тональность если AI говорит о бренде нейтрально/негативно

Промпт агента всегда на русском. Результат — пронумерованный список задач.

### Модуль 4 — Автоконтент
На основе плана агент пишет готовые тексты:
- Статьи для блога (SEO + GEO оптимизированные под Алису)
- FAQ блоки (вопрос-ответ — формат который Алиса цитирует чаще всего)
- Описания товаров/услуг

Клиент получает черновик → редактирует → публикует сам.

---

## База данных — ключевые таблицы

```sql
users (
    id, email, name, password_hash,
    subscription_plan,          -- 'start' | 'business' | 'agency'
    subscription_expires_at,
    created_at
)

projects (
    id, user_id, name, domain,
    competitors,   -- JSONB массив доменов конкурентов
    prompts,       -- JSONB массив промптов для мониторинга
    created_at
)

monitoring_results (
    id, project_id, prompt,
    platform,      -- 'alice' | 'gigachat'
    mentioned,     -- boolean
    position,      -- int или null
    sentiment,     -- 'positive' | 'neutral' | 'negative'
    response_text,
    checked_at
)

crawler_events (
    id, project_id,
    bot_name,      -- 'AliceBot' | 'GigaBot' | 'GPTBot' | ...
    user_agent,
    url_path,
    ip,
    verified,      -- boolean: IP совпал с официальными диапазонами
    visited_at
)

action_plans (
    id, project_id,
    tasks_json,    -- JSONB список задач от агента
    generated_at,
    status         -- 'new' | 'in_progress' | 'done'
)

generated_content (
    id, project_id,
    type,          -- 'article' | 'faq' | 'description'
    title, body,
    status,        -- 'draft' | 'published'
    created_at
)
```

---

## Тарифы

| Тариф | Цена | Промпты/мес | Проекты | Модули |
|-------|------|-------------|---------|--------|
| Старт | 990 ₽/мес | 10 | 1 | GEO + Краулер |
| Бизнес | 2 990 ₽/мес | 50 | 3 | Всё + Контент |
| Агентство | 7 990 ₽/мес | 200 | 10 | Всё + White label |

Лимиты проверяются в middleware бэкенда перед каждым запросом к внешним API.

---

## Соглашения по коду

### Python / FastAPI
- Всегда async/await
- Pydantic v2 для схем
- SQLAlchemy 2.0 async для БД
- Логирование через `structlog`
- Настройки через `pydantic-settings` (класс `Settings` в `core/config.py`)
- Никогда не хранить секреты в коде — только в `.env`
- Timeout для всех внешних запросов — не более 30 секунд
- Timeout для трекер-эндпоинта — не более 1 секунды (критично!)

### Next.js / TypeScript
- App Router (не Pages Router)
- Server Components по умолчанию
- Client Components только при необходимости интерактивности
- Tailwind для всех стилей
- Все запросы к бэку через `lib/api.ts`

### Общие правила
- Комментарии на русском языке
- Имена переменных и функций на английском
- Каждый модуль — отдельный роутер в FastAPI
- Ошибки логируются, никогда не глотаются (кроме трекер-сниппетов на стороне клиента)
- Перед вызовом внешних API — проверка лимитов тарифа пользователя

---

## Переменные окружения (.env)

```bash
# База данных
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/geo_db
REDIS_URL=redis://localhost:6379

# AI API
ANTHROPIC_API_KEY=sk-ant-...
YANDEX_GPT_API_KEY=...
YANDEX_CLOUD_FOLDER_ID=...
GIGACHAT_API_KEY=...

# Оплата
YOKASSA_SHOP_ID=...
YOKASSA_SECRET_KEY=...

# Auth
JWT_SECRET=...
NEXTAUTH_SECRET=...
NEXTAUTH_URL=https://yourdomain.ru

# App
DOMAIN=yourdomain.ru
TRACKER_ENDPOINT=https://api.yourdomain.ru/v1/track
```

---

## Порядок работы в новой сессии Claude Code

При старте новой сессии всегда читай этот файл первым.
Затем работай в таком порядке (Фаза 1):

1. Создать структуру папок проекта
2. `backend/` — FastAPI проект, core/, config, database
3. `backend/app/models/` — все SQLAlchemy модели
4. `backend/alembic/` — настроить миграции
5. `backend/app/services/alice_scraper.py` — Playwright scraper
6. `backend/app/services/yandexgpt.py` — YandexGPT клиент
7. `backend/app/services/gigachat.py` — GigaChat клиент
8. `backend/app/api/routes/monitoring.py` — эндпоинты мониторинга
9. `backend/app/api/routes/crawler.py` — эндпоинт `/v1/track`
10. `backend/app/services/claude_agent.py` — агент плана действий
11. `frontend/` — Next.js проект с Tailwind + NextAuth
12. `frontend/app/dashboard/` — основные страницы дашборда
13. `snippets/` — все трекер сниппеты

---

## Полезные ссылки

- YandexGPT API: https://cloud.yandex.ru/docs/yandexgpt/
- GigaChat API: https://developers.sber.ru/portal/products/gigachat
- ЮKassa документация: https://yookassa.ru/developers/
- IP диапазоны Яндекса (для верификации ботов): https://yandex.ru/ips
