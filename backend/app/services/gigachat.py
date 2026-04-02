"""
Клиент GigaChat API (Сбер).
Документация: https://developers.sber.ru/portal/products/gigachat

Поток авторизации:
    1. POST /oauth  →  Bearer access_token (живёт 30 мин)
    2. POST /chat/completions  →  ответ модели

Особенности:
    - Сбер использует собственный TLS-сертификат (Russian Trusted Root CA).
      По умолчанию httpx его не знает → ssl=False.
      В продакшене лучше подложить cert: https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer
    - OAuth endpoint находится на отдельном хосте (ngw.devices.sberbank.ru)
    - Токен кэшируем в памяти — не запрашиваем при каждом вызове
    - Все запросы: timeout 30 секунд (согласно CLAUDE.md)
"""
import asyncio
import base64
import time
import uuid
from dataclasses import dataclass, field

import httpx
import structlog

from app.core.config import settings
from app.services._utils import MonitoringCheckResult, build_result

logger = structlog.get_logger(__name__)

# ─── Константы ───────────────────────────────────────────────────────────────

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

# Модель GigaChat (lite — для экономии, pro — точнее)
GIGACHAT_MODEL = "GigaChat"

# Скоуп для корпоративного использования
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"

# Запас перед истечением токена (секунды)
TOKEN_REFRESH_MARGIN = 60

# Тайм-аут HTTP запросов
REQUEST_TIMEOUT = 30.0


# ─── Кэш токена ──────────────────────────────────────────────────────────────

@dataclass
class _TokenCache:
    """Простой in-memory кэш OAuth токена."""
    access_token: str = ""
    expires_at: float = 0.0          # unix timestamp

    def is_valid(self) -> bool:
        """Токен действителен с запасом TOKEN_REFRESH_MARGIN секунд."""
        return bool(self.access_token) and time.time() < (self.expires_at - TOKEN_REFRESH_MARGIN)

    def update(self, access_token: str, expires_at_ms: int) -> None:
        """
        Сохраняет новый токен.
        GigaChat возвращает expires_at в миллисекундах Unix timestamp.
        """
        self.access_token = access_token
        self.expires_at = expires_at_ms / 1000.0


# Синглтон кэша — один на процесс
_token_cache = _TokenCache()
# Лок для предотвращения параллельного обновления токена
_token_lock = asyncio.Lock()


# ─── Получение токена ────────────────────────────────────────────────────────

def _make_basic_auth() -> str:
    """
    Формирует Basic Auth заголовок из client_id и client_secret.
    GigaChat ожидает: Basic base64(client_id:client_secret)
    """
    credentials = f"{settings.gigachat_client_id}:{settings.gigachat_client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def _fetch_token(client: httpx.AsyncClient) -> str:
    """
    Запрашивает новый OAuth токен у GigaChat.
    Вызывается только если кэшированный токен истёк.

    Returns:
        access_token (str)

    Raises:
        RuntimeError: если авторизация не прошла
    """
    # RqUID — уникальный идентификатор запроса, требуется Сбером
    rq_uid = str(uuid.uuid4())

    try:
        response = await client.post(
            OAUTH_URL,
            headers={
                "Authorization": _make_basic_auth(),
                "RqUID": rq_uid,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"scope": GIGACHAT_SCOPE},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"GigaChat OAuth ошибка {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise RuntimeError(f"GigaChat OAuth сетевая ошибка: {e}") from e

    data = response.json()

    access_token: str | None = data.get("access_token")
    expires_at: int | None = data.get("expires_at")

    if not access_token:
        raise RuntimeError(
            f"GigaChat OAuth: не получен access_token. Ответ: {data}"
        )

    _token_cache.update(access_token, expires_at or int((time.time() + 1800) * 1000))
    await logger.ainfo("gigachat_token_refreshed")
    return access_token


async def _get_token(client: httpx.AsyncClient) -> str:
    """
    Возвращает действующий токен из кэша или запрашивает новый.
    Защищено asyncio.Lock от race condition при параллельных запросах.
    """
    if _token_cache.is_valid():
        return _token_cache.access_token

    async with _token_lock:
        # Двойная проверка: пока ждали лок, другая корутина могла обновить токен
        if _token_cache.is_valid():
            return _token_cache.access_token
        return await _fetch_token(client)


# ─── Запрос к Chat Completions ───────────────────────────────────────────────

async def _chat_completion(
    client: httpx.AsyncClient,
    token: str,
    prompt: str,
) -> str:
    """
    Отправляет промпт в GigaChat и возвращает текст ответа.

    Args:
        client: httpx клиент (уже настроен с ssl=False)
        token:  Bearer access_token
        prompt: текст запроса пользователя

    Returns:
        Текст ответа модели

    Raises:
        RuntimeError: при ошибке API
    """
    payload = {
        "model": GIGACHAT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        response = await client.post(
            CHAT_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        # 401 — токен истёк, нужно обновить
        if status_code == 401:
            raise RuntimeError("gigachat_token_expired") from e
        raise RuntimeError(
            f"GigaChat API ошибка {status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise RuntimeError(f"GigaChat API сетевая ошибка: {e}") from e

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(
            f"GigaChat API: неожиданный формат ответа: {data}"
        ) from e


# ─── Основная функция ─────────────────────────────────────────────────────────

async def query_gigachat(
    prompt: str,
    brand: str,
) -> MonitoringCheckResult:
    """
    Отправляет промпт в GigaChat API и анализирует ответ на упоминание бренда.

    Args:
        prompt: текст запроса (например "где купить кофемашину в Москве")
        brand:  название бренда для поиска в ответе (например "Nespresso")

    Returns:
        MonitoringCheckResult с полями mentioned, position, sentiment, response_text

    Raises:
        RuntimeError: если не удалось получить ответ (сеть, авторизация, API)
    """
    log = logger.bind(prompt=prompt[:50], brand=brand)
    await log.ainfo("gigachat_query_start")

    # ssl=False — GigaChat использует российский TLS-сертификат
    # verify=False безопасно в данном контексте т.к. это известный эндпоинт Сбера
    async with httpx.AsyncClient(verify=False) as client:
        # Получаем токен (из кэша или новый)
        token = await _get_token(client)

        # Отправляем запрос; при 401 — обновляем токен и повторяем один раз
        try:
            response_text = await _chat_completion(client, token, prompt)
        except RuntimeError as e:
            if "gigachat_token_expired" in str(e):
                # Инвалидируем кэш и получаем свежий токен
                _token_cache.access_token = ""
                token = await _get_token(client)
                response_text = await _chat_completion(client, token, prompt)
            else:
                raise

    await log.ainfo(
        "gigachat_query_done",
        response_length=len(response_text),
    )

    # Анализируем ответ через общие утилиты (те же что и для Алисы)
    result = build_result(
        response_text=response_text,
        prompt=prompt,
        brand=brand,
    )

    await log.ainfo(
        "gigachat_analysis_done",
        mentioned=result.mentioned,
        position=result.position,
        sentiment=result.sentiment,
    )

    return result


# ─── Batch запросы ────────────────────────────────────────────────────────────

async def query_gigachat_batch(
    prompts: list[str],
    brand: str,
    *,
    delay_between: float = 2.0,
) -> list[MonitoringCheckResult]:
    """
    Прогоняет несколько промптов через GigaChat последовательно.
    Задержка между запросами — чтобы не упереться в rate limit.

    Args:
        prompts:        список промптов
        brand:          бренд для анализа
        delay_between:  пауза между запросами (секунды)

    Returns:
        Список MonitoringCheckResult в том же порядке что prompts.
        При ошибке на конкретном промпте — возвращает пустой результат.
    """
    results: list[MonitoringCheckResult] = []

    for i, prompt in enumerate(prompts):
        if i > 0:
            await asyncio.sleep(delay_between)
        try:
            result = await query_gigachat(prompt, brand)
            results.append(result)
        except Exception as e:
            await logger.aerror(
                "gigachat_batch_item_failed",
                prompt=prompt[:50],
                error=str(e),
            )
            # Пустой результат — не прерываем весь батч
            results.append(
                MonitoringCheckResult(
                    mentioned=False,
                    position=None,
                    sentiment=None,
                    response_text="",
                    prompt=prompt,
                )
            )

    return results
