"""
Scraper для Яндекс Алисы (alice.yandex.ru).
Использует Playwright headless-браузер — UI scraping, т.к. официального API нет.

Основная функция:
    scrape_alice(prompt, brand) -> AliceScraperResult

Алгоритм:
    1. Открываем alice.yandex.ru
    2. Ждём загрузки поля ввода
    3. Вводим промпт, жмём Enter
    4. Ждём появления ответа Алисы (polling — ждём пока текст перестанет меняться)
    5. Анализируем текст: упомянут ли бренд, на какой позиции, тональность
    6. Возвращаем структурированный результат
"""
import asyncio
from typing import Literal

import structlog
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from app.services._utils import MonitoringCheckResult, build_result

logger = structlog.get_logger(__name__)

# ─── Алиас для обратной совместимости ───────────────────────────────────────

SentimentType = Literal["positive", "neutral", "negative"]

# AliceScraperResult — алиас MonitoringCheckResult для читаемости кода в этом модуле
AliceScraperResult = MonitoringCheckResult


# ─── Константы селекторов ────────────────────────────────────────────────────

# Поле ввода промпта (textarea или contenteditable div)
INPUT_SELECTORS = [
    "textarea[placeholder]",
    "div[contenteditable='true']",
    "input[type='text']",
    ".Input__control",
    "[data-testid='chat-input']",
    ".alice-input",
]

# Контейнер с ответом Алисы
RESPONSE_SELECTORS = [
    ".alice-message",
    "[data-testid='message']",
    ".MessengerMessages__message",
    ".MessageBubble",
    ".chat-message",
    "[class*='message'][class*='assistant']",
    "[class*='response']",
]

ALICE_URL = "https://alice.yandex.ru"

# Тайм-ауты (мс)
PAGE_LOAD_TIMEOUT = 30_000
INPUT_WAIT_TIMEOUT = 20_000
RESPONSE_WAIT_TIMEOUT = 30_000
TYPING_DELAY_MS = 50     # задержка между символами — имитируем человека


# ─── Playwright helpers ───────────────────────────────────────────────────────

async def _find_input(page: Page) -> object | None:
    """Перебирает селекторы и возвращает первый найденный элемент ввода."""
    for selector in INPUT_SELECTORS:
        try:
            el = await page.wait_for_selector(
                selector, timeout=3_000, state="visible"
            )
            if el:
                logger.debug("alice_input_found", selector=selector)
                return el
        except PlaywrightTimeoutError:
            continue
    return None


async def _get_latest_response(page: Page) -> str | None:
    """
    Возвращает текст последнего ответа Алисы из DOM.
    Перебирает возможные селекторы.
    """
    for selector in RESPONSE_SELECTORS:
        try:
            # Берём все элементы и возвращаем текст последнего
            elements = await page.query_selector_all(selector)
            if elements:
                last = elements[-1]
                text = await last.inner_text()
                if text and text.strip():
                    return text.strip()
        except Exception:
            continue
    return None


async def _wait_for_stable_response(
    page: Page,
    poll_interval: float = 0.8,
    stable_rounds: int = 3,
    max_wait: float = 30.0,
) -> str | None:
    """
    Ждёт пока ответ Алисы "стабилизируется" — перестанет меняться.

    Логика: опрашиваем DOM каждые poll_interval секунд.
    Если текст не изменился stable_rounds раз подряд — считаем ответ готовым.
    """
    previous_text: str | None = None
    stable_count = 0
    elapsed = 0.0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        current_text = await _get_latest_response(page)

        if current_text is None:
            # Ответ ещё не появился
            stable_count = 0
            continue

        if current_text == previous_text:
            stable_count += 1
            if stable_count >= stable_rounds:
                logger.debug(
                    "alice_response_stable",
                    elapsed=elapsed,
                    text_length=len(current_text),
                )
                return current_text
        else:
            stable_count = 0

        previous_text = current_text

    # Возвращаем что есть, даже если не стабилизировалось
    return previous_text


# ─── Основная функция ─────────────────────────────────────────────────────────

async def scrape_alice(
    prompt: str,
    brand: str,
    *,
    headless: bool = True,
    timeout: float = 60.0,
) -> AliceScraperResult:
    """
    Отправляет промпт в Яндекс Алису и анализирует ответ.

    Args:
        prompt:   текст запроса (например "где купить кофемашину в Москве")
        brand:    название бренда для поиска в ответе (например "Nespresso")
        headless: запускать браузер без UI (True в продакшене)
        timeout:  максимальное время ожидания в секундах

    Returns:
        AliceScraperResult с полями mentioned, position, sentiment, response_text

    Raises:
        RuntimeError: если не удалось получить ответ от Алисы
    """
    log = logger.bind(prompt=prompt[:50], brand=brand)
    await log.ainfo("alice_scrape_start")

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",   # важно для Docker
                "--disable-blink-features=AutomationControlled",  # скрываем webdriver
            ],
        )

        context: BrowserContext = await browser.new_context(
            # Имитируем реального пользователя
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )

        # Скрываем признаки автоматизации
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page: Page = await context.new_page()

        try:
            # ── 1. Открываем страницу ────────────────────────────────────────
            await page.goto(ALICE_URL, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            await log.ainfo("alice_page_loaded")

            # Небольшая пауза — даём JS отрисоваться
            await asyncio.sleep(2)

            # ── 2. Находим поле ввода ────────────────────────────────────────
            input_el = await _find_input(page)
            if input_el is None:
                # Делаем скриншот для отладки
                await page.screenshot(path="/tmp/alice_debug.png")
                raise RuntimeError(
                    "Не удалось найти поле ввода на alice.yandex.ru. "
                    "Возможно изменился DOM или требуется авторизация."
                )

            # ── 3. Вводим промпт ─────────────────────────────────────────────
            await input_el.click()
            await asyncio.sleep(0.3)
            # type() имитирует ввод с клавиатуры, delay — задержка между символами
            await input_el.type(prompt, delay=TYPING_DELAY_MS)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")

            await log.ainfo("alice_prompt_sent", prompt_length=len(prompt))

            # ── 4. Ждём ответ ────────────────────────────────────────────────
            response_text = await _wait_for_stable_response(
                page,
                max_wait=timeout - 10,  # оставляем запас на cleanup
            )

            if not response_text:
                await page.screenshot(path="/tmp/alice_no_response.png")
                raise RuntimeError(
                    "Алиса не ответила в отведённое время. "
                    f"Промпт: '{prompt[:100]}'"
                )

            await log.ainfo(
                "alice_response_received",
                response_length=len(response_text),
            )

            # ── 5. Анализируем результат через общие утилиты ─────────────────
            result = build_result(
                response_text=response_text,
                prompt=prompt,
                brand=brand,
            )

            await log.ainfo(
                "alice_scrape_done",
                mentioned=result.mentioned,
                position=result.position,
                sentiment=result.sentiment,
            )
            return result

        except PlaywrightTimeoutError as e:
            await log.aerror("alice_timeout", error=str(e))
            raise RuntimeError(f"Тайм-аут при работе с Алисой: {e}") from e

        except Exception as e:
            await log.aerror("alice_scrape_error", error=str(e))
            raise

        finally:
            await context.close()
            await browser.close()


# ─── Утилита для batch-запросов ───────────────────────────────────────────────

async def scrape_alice_batch(
    prompts: list[str],
    brand: str,
    *,
    delay_between: float = 3.0,
    headless: bool = True,
) -> list[AliceScraperResult]:
    """
    Прогоняет несколько промптов через Алису последовательно.
    Задержка между запросами — чтобы не выглядеть как бот.

    Args:
        prompts:        список промптов
        brand:          бренд для поиска
        delay_between:  пауза между запросами (секунды)
        headless:       запускать без UI

    Returns:
        Список AliceScraperResult в том же порядке что prompts.
        При ошибке на конкретном промпте — возвращает пустой результат.
    """
    results: list[AliceScraperResult] = []

    for i, prompt in enumerate(prompts):
        if i > 0:
            await asyncio.sleep(delay_between)
        try:
            result = await scrape_alice(prompt, brand, headless=headless)
            results.append(result)
        except Exception as e:
            await logger.aerror(
                "alice_batch_item_failed",
                prompt=prompt[:50],
                error=str(e),
            )
            # Возвращаем пустой результат вместо прерывания всего батча
            results.append(
                AliceScraperResult(
                    mentioned=False,
                    position=None,
                    sentiment=None,
                    response_text="",
                    prompt=prompt,
                )
            )

    return results
