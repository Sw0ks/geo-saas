"""
Общие утилиты для анализа ответов AI-платформ.
Используется в alice_scraper.py и gigachat.py.

Экспортирует:
    SentimentType          — тип тональности
    MonitoringCheckResult  — унифицированный датакласс результата
    find_brand_in_text()   — поиск бренда и позиции
    analyze_sentiment()    — определение тональности по эвристике
"""
import re
from dataclasses import dataclass
from typing import Literal

# ─── Типы ────────────────────────────────────────────────────────────────────

SentimentType = Literal["positive", "neutral", "negative"]


@dataclass
class MonitoringCheckResult:
    """
    Унифицированный результат одной проверки (Алиса или ГигаЧат).
    Оба сервиса возвращают этот класс — роутер работает с ним одинаково.
    """
    mentioned: bool                   # упомянут ли бренд в ответе
    position: int | None              # номер предложения с упоминанием (1-based)
    sentiment: SentimentType | None   # тональность контекста вокруг бренда
    response_text: str                # полный текст ответа AI
    prompt: str                       # исходный промпт


# ─── Словари тональности ─────────────────────────────────────────────────────

# Позитивные маркеры — расширенный словарь для русскоязычного рынка
POSITIVE_WORDS: frozenset[str] = frozenset({
    "лучший", "лучшая", "лучшее", "лучшие",
    "отличный", "отличная", "отличное", "отличные",
    "рекомендуем", "рекомендует", "рекомендую", "рекомендован",
    "хороший", "хорошая", "хорошее", "хорошие",
    "надёжный", "надёжная", "надёжное", "надёжные",
    "качественный", "качественная", "качественное",
    "популярный", "популярная", "популярен",
    "топ", "лидер", "лидирующий",
    "достойный", "достойная",
    "преимущество", "преимущества",
    "выгодный", "выгодная", "выгодно",
    "удобный", "удобная", "удобно",
    "советует", "советуем",
    "заслуживает", "заслуженно",
    "профессиональный", "профессионально",
    "высокое качество", "высокий рейтинг",
    "положительные отзывы", "хорошие отзывы",
})

# Негативные маркеры
NEGATIVE_WORDS: frozenset[str] = frozenset({
    "плохой", "плохая", "плохое", "плохо",
    "худший", "худшая", "худшее",
    "не рекомендуем", "не советуем", "не рекомендую",
    "проблема", "проблемы",
    "жалоба", "жалобы",
    "негативный", "негативные отзывы",
    "мошенничество", "мошенник",
    "обман", "обманывают",
    "ненадёжный", "ненадёжная",
    "опасный", "опасно",
    "штраф", "претензия",
    "недостаток", "недостатки",
    "разочарование", "разочаровал",
    "некачественный", "некачественно",
    "завышенные цены",
    "плохое обслуживание",
    "отрицательные отзывы",
})


# ─── Основные функции ─────────────────────────────────────────────────────────

def find_brand_in_text(text: str, brand: str) -> tuple[bool, int | None]:
    """
    Ищет упоминание бренда в тексте ответа AI.

    Алгоритм:
    1. Нормализуем текст и бренд к нижнему регистру
    2. Проверяем наличие подстроки
    3. Разбиваем на предложения, ищем номер первого предложения с брендом

    Args:
        text:  полный текст ответа AI
        brand: название бренда (например "Nespresso" или "ПиццаМаша")

    Returns:
        (mentioned, position) где position — номер предложения (1-based) или None
    """
    if not text or not brand:
        return False, None

    brand_lower = brand.lower().strip()
    text_lower = text.lower()

    if brand_lower not in text_lower:
        return False, None

    # Разбиваем на предложения по знакам препинания
    sentences = re.split(r"[.!?\n]+", text)
    for idx, sentence in enumerate(sentences, start=1):
        if brand_lower in sentence.lower():
            return True, idx

    # Бренд есть в тексте, но split не разбил на предложения
    return True, 1


def analyze_sentiment(text: str, brand: str) -> SentimentType:
    """
    Определяет тональность текста вокруг упоминания бренда.

    Подход: берём контекст ±300 символов вокруг первого упоминания бренда
    и считаем позитивные/негативные маркеры. Побеждает тот, кого больше.
    При равенстве — neutral.

    Это простая эвристика. В продакшен-версии заменить на
    claude_agent.analyze_sentiment() для точного анализа через Claude API.

    Args:
        text:  полный текст ответа AI
        brand: название бренда

    Returns:
        'positive' | 'neutral' | 'negative'
    """
    if not text:
        return "neutral"

    brand_lower = brand.lower().strip()
    text_lower = text.lower()

    # Вырезаем контекст вокруг бренда для точности
    pos = text_lower.find(brand_lower)
    if pos == -1:
        # Бренд не найден — анализируем весь текст (например для общей тональности)
        context = text_lower
    else:
        start = max(0, pos - 300)
        end = min(len(text_lower), pos + len(brand_lower) + 300)
        context = text_lower[start:end]

    positive_hits = sum(1 for w in POSITIVE_WORDS if w in context)
    negative_hits = sum(1 for w in NEGATIVE_WORDS if w in context)

    if negative_hits > positive_hits:
        return "negative"
    if positive_hits > negative_hits:
        return "positive"
    return "neutral"


def build_result(
    response_text: str,
    prompt: str,
    brand: str,
) -> MonitoringCheckResult:
    """
    Удобная обёртка: анализирует текст и возвращает готовый MonitoringCheckResult.
    Вызывается из alice_scraper и gigachat после получения ответа AI.
    """
    mentioned, position = find_brand_in_text(response_text, brand)
    sentiment: SentimentType | None = (
        analyze_sentiment(response_text, brand) if mentioned else None
    )
    return MonitoringCheckResult(
        mentioned=mentioned,
        position=position,
        sentiment=sentiment,
        response_text=response_text,
        prompt=prompt,
    )
