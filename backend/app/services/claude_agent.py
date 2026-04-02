"""
Claude-агент для генерации плана действий по улучшению GEO-позиций.

Использует claude-sonnet-4-6 через Anthropic SDK.
Промпты — всегда на русском языке.
Максимум 7 задач, отсортированных по приоритету (1 = самый важный).

Основная функция:
    generate_action_plan(project_id, monitoring_data) -> AgentPlanResult

Структура входных данных (AgentInput):
    - project:  название, домен, конкуренты
    - results:  список результатов мониторинга (alice + gigachat)
    - summary:  агрегированная статистика

Структура ответа (AgentPlanResult):
    - tasks:    список AgentTask (до 7 штук)
    - summary:  краткий вывод о текущей ситуации
"""
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import anthropic
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Используемая модель (из CLAUDE.md)
CLAUDE_MODEL = "claude-sonnet-4-6"

# Максимум задач в плане
MAX_TASKS = 7

# Timeout Anthropic SDK — 30 секунд (из CLAUDE.md)
REQUEST_TIMEOUT = 30.0

# Категории задач
CategoryType = Literal["content", "faq", "technical", "mentions", "tone"]


# ─── Структуры данных ─────────────────────────────────────────────────────────

@dataclass
class MonitoringSnapshot:
    """Один результат мониторинга для передачи агенту."""
    prompt: str
    platform: str             # 'alice' | 'gigachat'
    mentioned: bool
    position: int | None
    sentiment: str | None     # 'positive' | 'neutral' | 'negative'
    response_text: str | None = None


@dataclass
class ProjectContext:
    """Контекст проекта для агента."""
    project_id: uuid.UUID
    name: str
    domain: str
    competitors: list[str]
    prompts: list[str]


@dataclass
class AgentInput:
    """Полные входные данные для агента."""
    project: ProjectContext
    monitoring_results: list[MonitoringSnapshot]


@dataclass
class AgentTask:
    """Одна задача в плане действий от агента."""
    priority: int                       # 1 = наивысший приоритет
    category: CategoryType
    title: str
    description: str
    expected_result: str


@dataclass
class AgentPlanResult:
    """Результат работы агента — готовый план действий."""
    tasks: list[AgentTask]
    summary: str

    def to_tasks_json(self) -> list[dict]:
        """Сериализует задачи в JSONB-совместимый список для БД."""
        return [
            {
                "priority": t.priority,
                "category": t.category,
                "title": t.title,
                "description": t.description,
                "expected_result": t.expected_result,
            }
            for t in self.tasks
        ]


# ─── Построение промпта ────────────────────────────────────────────────────────

def _build_monitoring_summary(results: list[MonitoringSnapshot]) -> str:
    """
    Форматирует результаты мониторинга в читаемый блок для промпта.
    """
    if not results:
        return "Данных мониторинга пока нет — проект новый."

    alice_results = [r for r in results if r.platform == "alice"]
    gigachat_results = [r for r in results if r.platform == "gigachat"]

    def _format_platform(items: list[MonitoringSnapshot], name: str) -> str:
        if not items:
            return f"\n{name}: данных нет."
        mentioned = [r for r in items if r.mentioned]
        rate = len(mentioned) / len(items) * 100
        lines = [f"\n{name} ({len(items)} проверок):"]
        lines.append(f"  • Упоминаний: {len(mentioned)} из {len(items)} ({rate:.0f}%)")

        if mentioned:
            avg_pos = sum(r.position for r in mentioned if r.position) / max(
                sum(1 for r in mentioned if r.position), 1
            )
            lines.append(f"  • Средняя позиция упоминания: {avg_pos:.1f}-е предложение")

            sentiments = [r.sentiment for r in mentioned if r.sentiment]
            if sentiments:
                from collections import Counter
                counts = Counter(sentiments)
                lines.append(f"  • Тональность: {dict(counts)}")

        # Показываем примеры промптов где не упомянут
        not_mentioned = [r for r in items if not r.mentioned]
        if not_mentioned:
            lines.append(f"  • Не упомянут в запросах:")
            for r in not_mentioned[:3]:
                lines.append(f"    — «{r.prompt}»")

        return "\n".join(lines)

    return _format_platform(alice_results, "Яндекс Алиса") + "\n" + _format_platform(gigachat_results, "ГигаЧат")


def _build_system_prompt() -> str:
    """Системный промпт агента — описывает роль и формат ответа."""
    return """Ты — эксперт по GEO-оптимизации (Generative Engine Optimization) для российского рынка.
Твоя задача — помогать малому бизнесу появляться в ответах AI-ассистентов: Яндекс Алиса и ГигаЧат.

Ты анализируешь данные мониторинга и составляешь конкретный план действий.

ПРАВИЛА ОТВЕТА:
1. Отвечай ТОЛЬКО на русском языке
2. Возвращай ТОЛЬКО валидный JSON — без markdown, без ```json, без пояснений до/после
3. Максимум 7 задач, отсортированных по приоритету (1 = первоочередное)
4. Каждая задача должна быть конкретной и выполнимой за 1-2 недели
5. Категории задач: content, faq, technical, mentions, tone

КАТЕГОРИИ:
- content: написать статьи, описания, тексты для сайта
- faq: создать блок вопрос-ответ (формат который AI цитирует чаще всего)
- technical: schema.org разметка, скорость сайта, структура страниц
- mentions: разместить упоминания бренда на внешних площадках
- tone: исправить негативный или нейтральный контекст упоминаний

ФОРМАТ JSON (строго соблюдай структуру):
{
  "tasks": [
    {
      "priority": 1,
      "category": "faq",
      "title": "Короткое название задачи (до 80 символов)",
      "description": "Детальное описание: что именно сделать, как, где разместить. Минимум 2-3 предложения.",
      "expected_result": "Конкретный ожидаемый результат: как это повлияет на упоминания в AI"
    }
  ],
  "summary": "Краткий вывод о текущей ситуации и главной проблеме (2-4 предложения)"
}"""


def _build_user_prompt(agent_input: AgentInput) -> str:
    """Строит пользовательский промпт с данными конкретного проекта."""
    p = agent_input.project
    monitoring_text = _build_monitoring_summary(agent_input.monitoring_results)

    competitors_text = (
        ", ".join(p.competitors) if p.competitors
        else "конкуренты не указаны"
    )
    prompts_text = (
        "\n".join(f"  — «{pr}»" for pr in p.prompts[:10]) if p.prompts
        else "промпты не указаны"
    )

    return f"""Проанализируй данные мониторинга и составь план GEO-оптимизации.

ДАННЫЕ ПРОЕКТА:
  Название бизнеса: {p.name}
  Домен сайта: {p.domain}
  Конкуренты: {competitors_text}

ПРОМПТЫ МОНИТОРИНГА (запросы которые проверяются в AI):
{prompts_text}

РЕЗУЛЬТАТЫ МОНИТОРИНГА:
{monitoring_text}

ЗАДАЧА:
Составь пронумерованный план действий для улучшения GEO-позиций.
Сфокусируйся на самых эффективных шагах чтобы AI-ассистенты начали упоминать бренд «{p.name}».
Учти какие промпты дают нулевое упоминание — это приоритет.

Верни JSON строго по указанному формату."""


# ─── Парсинг ответа Claude ────────────────────────────────────────────────────

def _parse_claude_response(raw_text: str, project_name: str) -> AgentPlanResult:
    """
    Парсит JSON из ответа Claude.
    Обрабатывает случаи когда Claude всё-таки обернул JSON в markdown.

    Args:
        raw_text:     сырой текст ответа от Claude
        project_name: для fallback сообщений при ошибке

    Returns:
        AgentPlanResult с распарсенными задачами

    Raises:
        ValueError: если JSON не удалось распарсить
    """
    text = raw_text.strip()

    # Убираем markdown-обёртку если Claude её добавил вопреки инструкции
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if match:
            text = match.group(1).strip()

    # Ищем JSON-объект если есть текст вокруг
    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            text = match.group(0)

    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude вернул невалидный JSON: {e}\nТекст: {text[:500]}") from e

    # Парсим задачи
    raw_tasks: list[dict] = data.get("tasks", [])
    if not isinstance(raw_tasks, list):
        raise ValueError(f"Поле 'tasks' должно быть списком, получено: {type(raw_tasks)}")

    tasks: list[AgentTask] = []
    for i, raw in enumerate(raw_tasks[:MAX_TASKS]):
        # Нормализуем category — приводим к допустимым значениям
        raw_category = str(raw.get("category", "content")).lower()
        valid_categories = {"content", "faq", "technical", "mentions", "tone"}
        category: CategoryType = raw_category if raw_category in valid_categories else "content"  # type: ignore

        tasks.append(AgentTask(
            priority=int(raw.get("priority", i + 1)),
            category=category,
            title=str(raw.get("title", f"Задача {i + 1}")),
            description=str(raw.get("description", "")),
            expected_result=str(raw.get("expected_result", "")),
        ))

    # Сортируем по приоритету на случай если Claude нарушил порядок
    tasks.sort(key=lambda t: t.priority)

    summary = str(data.get("summary", f"План GEO-оптимизации для бренда «{project_name}» сгенерирован."))

    return AgentPlanResult(tasks=tasks, summary=summary)


# ─── Основная функция агента ──────────────────────────────────────────────────

async def generate_action_plan(agent_input: AgentInput) -> AgentPlanResult:
    """
    Генерирует план действий GEO-оптимизации через Claude API.

    Args:
        agent_input: контекст проекта + результаты мониторинга

    Returns:
        AgentPlanResult с задачами и кратким выводом

    Raises:
        RuntimeError: при ошибке Anthropic API
    """
    log = logger.bind(
        project_id=str(agent_input.project.project_id),
        project_name=agent_input.project.name,
        results_count=len(agent_input.monitoring_results),
    )
    await log.ainfo("claude_agent_start")

    # Строим промпты
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(agent_input)

    await log.adebug(
        "claude_agent_prompt_built",
        user_prompt_length=len(user_prompt),
    )

    # Инициализируем клиент Anthropic
    # AsyncAnthropic создаём здесь — не держим синглтон (простота, нет утечек)
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=REQUEST_TIMEOUT,
    )

    try:
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
        )
    except anthropic.APIStatusError as e:
        raise RuntimeError(
            f"Claude API ошибка {e.status_code}: {e.message}"
        ) from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Claude API недоступен: {e}") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Claude API: превышен лимит запросов. Попробуйте позже.") from e

    # Извлекаем текст ответа
    raw_text = message.content[0].text if message.content else ""

    await log.ainfo(
        "claude_agent_response_received",
        response_length=len(raw_text),
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )

    # Парсим ответ
    try:
        result = _parse_claude_response(raw_text, agent_input.project.name)
    except ValueError as e:
        await log.aerror("claude_agent_parse_error", error=str(e), raw_text=raw_text[:300])
        raise RuntimeError(f"Не удалось разобрать ответ Claude: {e}") from e

    await log.ainfo(
        "claude_agent_done",
        tasks_count=len(result.tasks),
        summary_length=len(result.summary),
    )

    return result


# ════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ КОНТЕНТА
# ════════════════════════════════════════════════════════════════════════════

# Типы контента
ContentTypeStr = Literal["article", "faq", "description"]

# Лимит токенов для каждого типа
_CONTENT_MAX_TOKENS: dict[str, int] = {
    "article": 3000,       # ~800–1200 слов
    "faq": 2000,           # 5–10 вопросов-ответов
    "description": 800,    # 150–200 слов
}


@dataclass
class ContentInput:
    """Входные данные для генерации контента."""
    project_name: str
    project_domain: str
    content_type: ContentTypeStr
    topic: str
    task_context: str | None = None       # текст задачи из плана, если передан
    additional_context: str | None = None


@dataclass
class ContentResult:
    """Результат генерации контента."""
    title: str
    body: str
    content_type: ContentTypeStr
    word_count: int


def _extract_title_and_body(raw_text: str, fallback_title: str) -> tuple[str, str]:
    """
    Извлекает заголовок (первая строка `# ...`) и тело из Markdown-текста.
    Если H1 не найден — возвращает fallback_title и весь текст как тело.
    """
    text = raw_text.strip()
    lines = text.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            body = "\n".join(lines[i + 1:]).strip()
            return title, body

    # H1 не найден — используем fallback
    return fallback_title, text


def _build_article_system_prompt() -> str:
    return """Ты — эксперт по контент-маркетингу и GEO-оптимизации (Generative Engine Optimization).
Ты пишешь статьи для российских сайтов, которые хорошо цитируют AI-ассистенты Яндекс Алиса и ГигаЧат.

ПРАВИЛА:
1. Пиши ТОЛЬКО на русском языке
2. Используй Markdown разметку (# H1, ## H2, **жирный**, списки)
3. Начинай с заголовка H1 (одна строка # Заголовок)
4. Структура: H1 → введение → 3-5 разделов H2 → FAQ блок → заключение
5. 800–1200 слов суммарно
6. Стиль: профессиональный, конкретный, без воды

ТРЕБОВАНИЯ ДЛЯ GEO-ОПТИМИЗАЦИИ (чтобы Алиса цитировала статью):
- Прямые ответы на вопросы в начале каждого раздела (не после нескольких предложений)
- Конкретные факты: цифры, даты, характеристики
- Структурированные данные: маркированные и нумерованные списки
- FAQ блок в конце: минимум 3 вопроса в формате **Вопрос:** / **Ответ:**
- Использование точных формулировок из реальных поисковых запросов пользователей
- Упоминание бренда/компании в первом абзаце и в заголовке если уместно"""


def _build_faq_system_prompt() -> str:
    return """Ты — эксперт по GEO-оптимизации и написанию FAQ для AI-ассистентов.
Ты создаёшь блоки вопросов и ответов, которые Яндекс Алиса и ГигаЧат охотно цитируют.

ПРАВИЛА:
1. Пиши ТОЛЬКО на русском языке
2. Используй Markdown разметку
3. Начинай с заголовка H1: # FAQ: [тема]
4. 5–10 вопросов и ответов
5. Формат каждой пары:

**Вопрос:** Текст вопроса?

**Ответ:** Текст ответа. Конкретно и по делу, 2-4 предложения.

---

ТРЕБОВАНИЯ ДЛЯ GEO-ОПТИМИЗАЦИИ:
- Вопросы должны быть точными запросами реальных пользователей («сколько стоит», «как работает», «где найти»)
- Ответы начинаются с прямого ответа на вопрос, затем детали
- Включи числовые данные и конкретные факты
- Упоминай бренд в ответах естественно
- Вопросы охватывают: цены, характеристики, отличия от конкурентов, процесс работы"""


def _build_description_system_prompt() -> str:
    return """Ты — копирайтер для российских сайтов, специализируешься на описаниях товаров и услуг.
Ты пишешь тексты которые AI-ассистенты (Алиса, ГигаЧат) легко цитируют при ответе пользователям.

ПРАВИЛА:
1. Пиши ТОЛЬКО на русском языке
2. Используй Markdown разметку
3. Начинай с заголовка H1: # [Название товара/услуги]: краткое определение
4. 150–200 слов
5. Структура:
   - Первое предложение: что это такое (прямое определение)
   - Ключевые характеристики (маркированный список: 4-6 пунктов)
   - Для кого / когда нужно (1-2 предложения)
   - Призыв к действию (1 предложение)

ТРЕБОВАНИЯ ДЛЯ GEO-ОПТИМИЗАЦИИ:
- Первое предложение — полное определение (AI берёт именно его для ответа)
- Конкретные цифры: цена, размер, срок, мощность и т.д.
- Простые, понятные формулировки без маркетинговых клише
- Естественное упоминание бренда"""


def _build_content_user_prompt(inp: ContentInput) -> str:
    """Строит пользовательский промпт для генерации конкретного контента."""
    context_block = ""
    if inp.task_context:
        context_block += f"\nЗАДАЧА ИЗ ПЛАНА:\n{inp.task_context}\n"
    if inp.additional_context:
        context_block += f"\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:\n{inp.additional_context}\n"

    type_instruction = {
        "article": f"Напиши статью для блога на тему: «{inp.topic}»",
        "faq": f"Создай FAQ блок на тему: «{inp.topic}»",
        "description": f"Напиши описание для: «{inp.topic}»",
    }[inp.content_type]

    return f"""ДАННЫЕ ПРОЕКТА:
  Бизнес: {inp.project_name}
  Сайт: {inp.project_domain}
{context_block}
ЗАДАНИЕ:
{type_instruction}

Контент должен помочь бренду «{inp.project_name}» появляться в ответах Яндекс Алисы и ГигаЧата.
Начни сразу с H1 заголовка — без вступлений и пояснений."""


# ─── Основная функция генерации контента ─────────────────────────────────────

async def generate_content(content_input: ContentInput) -> ContentResult:
    """
    Генерирует контент (статья / FAQ / описание) через Claude API.

    Args:
        content_input: параметры генерации (тип, тема, контекст проекта)

    Returns:
        ContentResult с заголовком, телом и количеством слов

    Raises:
        RuntimeError: при ошибке Anthropic API
    """
    log = logger.bind(
        project_name=content_input.project_name,
        content_type=content_input.content_type,
        topic=content_input.topic,
    )
    await log.ainfo("content_generation_start")

    system_prompts: dict[ContentTypeStr, str] = {
        "article": _build_article_system_prompt(),
        "faq": _build_faq_system_prompt(),
        "description": _build_description_system_prompt(),
    }

    system_prompt = system_prompts[content_input.content_type]
    user_prompt = _build_content_user_prompt(content_input)
    max_tokens = _CONTENT_MAX_TOKENS[content_input.content_type]

    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=REQUEST_TIMEOUT,
    )

    try:
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API ошибка {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Claude API недоступен: {e}") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Claude API: превышен лимит запросов. Попробуйте позже.") from e

    raw_text = message.content[0].text if message.content else ""

    await log.ainfo(
        "content_generation_done",
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
        raw_length=len(raw_text),
    )

    # Определяем fallback-заголовок по типу
    fallback_titles: dict[ContentTypeStr, str] = {
        "article": content_input.topic,
        "faq": f"FAQ: {content_input.topic}",
        "description": f"{content_input.topic}: описание",
    }
    title, body = _extract_title_and_body(raw_text, fallback_titles[content_input.content_type])
    word_count = len(body.split())

    return ContentResult(
        title=title,
        body=body,
        content_type=content_input.content_type,
        word_count=word_count,
    )


# ════════════════════════════════════════════════════════════════════════════
# ПРЕДЛОЖЕНИЕ ПРОМПТОВ ДЛЯ ОНБОРДИНГА
# ════════════════════════════════════════════════════════════════════════════

async def suggest_prompts(business_name: str, business_description: str) -> list[str]:
    """
    Генерирует 5 промптов для мониторинга на основе описания бизнеса.
    Вызывается во время онбординга — помогает пользователю сразу начать.

    Промпты — это реальные запросы, которые пользователи задают Алисе и ГигаЧату
    при поиске подобного бизнеса. Возвращает JSON-список из 5 строк.

    Args:
        business_name:        название бизнеса («Пицца Марио»)
        business_description: описание 1-2 предложения

    Returns:
        list[str] — 5 поисковых запросов на русском языке

    Raises:
        RuntimeError: при ошибке Anthropic API
    """
    system_prompt = """Ты — эксперт по GEO-оптимизации для российского рынка.
Твоя задача: предложить 5 поисковых запросов, которые реальные пользователи вводят в Яндекс Алису
или ГигаЧат когда ищут подобный бизнес или услугу.

ПРАВИЛА:
1. Отвечай ТОЛЬКО на русском языке
2. Возвращай ТОЛЬКО валидный JSON — без markdown, без пояснений
3. Ровно 5 запросов
4. Запросы должны быть как реальные вопросы пользователей (8-20 слов)
5. Охватывай разные аспекты: «лучший», «где найти», «цена», «как выбрать», «отзывы»
6. Включай город или «в Москве» / «в России» где уместно

ФОРМАТ (строго):
{"prompts": ["запрос 1", "запрос 2", "запрос 3", "запрос 4", "запрос 5"]}"""

    user_prompt = (
        f"Бизнес: {business_name}\n"
        f"Описание: {business_description}\n\n"
        f"Предложи 5 промптов для мониторинга упоминаний бренда «{business_name}» в AI-ассистентах."
    )

    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=REQUEST_TIMEOUT,
    )

    try:
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API ошибка {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(f"Claude API недоступен: {e}") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Claude API: превышен лимит запросов. Попробуйте позже.") from e

    raw = message.content[0].text if message.content else ""

    # Парсим JSON с промптами (тот же fallback что и в _parse_claude_response)
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            text = m.group(1).strip()
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            text = m.group(0)

    try:
        data: dict = json.loads(text)
        prompts: list[str] = data.get("prompts", [])
        if not isinstance(prompts, list):
            raise ValueError("prompts не список")
        # Берём максимум 5, фильтруем пустые строки
        return [str(p).strip() for p in prompts if str(p).strip()][:5]
    except (json.JSONDecodeError, ValueError):
        logger.warning("suggest_prompts_parse_error", raw=raw[:200])
        # Fallback: генерируем базовые промпты из названия
        return [
            f"лучший {business_name} в Москве",
            f"где найти {business_name}",
            f"{business_name} цены и отзывы",
            f"как выбрать {business_name}",
            f"{business_name} рекомендации",
        ]


# ─── Вспомогательная функция для сборки AgentInput из БД ────────────────────

def build_agent_input(
    project_id: uuid.UUID,
    project_name: str,
    project_domain: str,
    project_competitors: list[str],
    project_prompts: list[str],
    monitoring_results: list[dict],
) -> AgentInput:
    """
    Собирает AgentInput из данных проекта и результатов мониторинга.
    Вызывается из роутера agent.py перед передачей агенту.

    Args:
        project_id:           UUID проекта
        project_name:         название проекта/бренда
        project_domain:       домен сайта
        project_competitors:  список доменов конкурентов
        project_prompts:      список промптов мониторинга
        monitoring_results:   список dict из MonitoringResult ORM объектов

    Returns:
        AgentInput готовый к передаче в generate_action_plan()
    """
    snapshots = [
        MonitoringSnapshot(
            prompt=r.get("prompt", ""),
            platform=r.get("platform", ""),
            mentioned=r.get("mentioned", False),
            position=r.get("position"),
            sentiment=r.get("sentiment"),
            response_text=r.get("response_text"),
        )
        for r in monitoring_results
    ]

    return AgentInput(
        project=ProjectContext(
            project_id=project_id,
            name=project_name,
            domain=project_domain,
            competitors=project_competitors,
            prompts=project_prompts,
        ),
        monitoring_results=snapshots,
    )
