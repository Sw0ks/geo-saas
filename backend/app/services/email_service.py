"""
Email-сервис через SMTP (стандартная библиотека, без зависимостей).

Поддерживает:
  - SSL (порт 465) через smtplib.SMTP_SSL
  - STARTTLS (порт 587) через smtplib.SMTP + starttls()

Экспортируемые функции:
  send_welcome_email(to_email, name)
      Приветственное письмо после регистрации.

  send_weekly_report(to_email, name, data)
      Еженедельный отчёт по AI-видимости.

Обе функции — async обёртки над sync SMTP через asyncio.to_thread().
При отсутствии SMTP-настроек (пустой SMTP_USER) — тихо пропускают отправку.
"""
import asyncio
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Название продукта — используется в письмах
PRODUCT_NAME = "GEO Analytics"


# ─── Структура данных для еженедельного отчёта ────────────────────────────────

@dataclass
class WeeklyReportData:
    project_name: str
    alice_mention_rate: float       # 0–100 %
    gigachat_mention_rate: float    # 0–100 %
    crawler_visits: int
    top_tasks: list[dict] = field(default_factory=list)  # до 3 задач из плана


# ─── Вспомогательные HTML-блоки ───────────────────────────────────────────────

def _base_wrapper(content_html: str) -> str:
    """Оборачивает HTML-контент в общий контейнер письма."""
    dashboard_url = f"https://{settings.domain}/dashboard"
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="background:#ffffff;border-radius:12px;overflow:hidden;
                      box-shadow:0 2px 8px rgba(0,0,0,0.08);">
          <!-- Шапка -->
          <tr>
            <td style="background:#4f46e5;padding:28px 40px;">
              <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">
                {PRODUCT_NAME}
              </h1>
              <p style="margin:4px 0 0;color:#c7d2fe;font-size:13px;">
                AI-видимость вашего бизнеса
              </p>
            </td>
          </tr>
          <!-- Контент -->
          <tr>
            <td style="padding:36px 40px;">
              {content_html}
            </td>
          </tr>
          <!-- Подвал -->
          <tr>
            <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">
                © 2025 {PRODUCT_NAME} · Для малого бизнеса России<br>
                <a href="{dashboard_url}" style="color:#6366f1;text-decoration:none;">
                  Перейти в дашборд
                </a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _cta_button(url: str, label: str) -> str:
    return (
        f'<div style="text-align:center;margin:28px 0;">'
        f'<a href="{url}" style="background:#4f46e5;color:#ffffff;text-decoration:none;'
        f'font-size:15px;font-weight:600;padding:14px 36px;border-radius:8px;display:inline-block;">'
        f'{label}</a></div>'
    )


# ─── Шаблоны писем ────────────────────────────────────────────────────────────

def _build_welcome_html(name: str) -> str:
    dashboard_url = f"https://{settings.domain}/dashboard"
    content = f"""
      <h2 style="margin:0 0 8px;font-size:22px;color:#1e293b;">
        Добро пожаловать, {name}!
      </h2>
      <p style="margin:0 0 24px;font-size:15px;color:#64748b;line-height:1.6;">
        Спасибо за регистрацию в <strong>{PRODUCT_NAME}</strong> — сервисе для мониторинга
        вашего бизнеса в ответах Яндекс Алисы и ГигаЧата.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#f1f5f9;border-radius:8px;padding:24px;margin-bottom:28px;">
        <tr>
          <td>
            <p style="margin:0 0 16px;font-size:14px;font-weight:700;color:#475569;">
              Что вы можете делать прямо сейчас:
            </p>
            <table cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="vertical-align:top;padding-right:12px;font-size:18px;">📍</td>
                <td style="padding-bottom:12px;">
                  <p style="margin:0;font-size:14px;color:#334155;font-weight:600;">
                    Создать первый проект
                  </p>
                  <p style="margin:2px 0 0;font-size:13px;color:#64748b;">
                    Укажите домен вашего сайта и конкурентов
                  </p>
                </td>
              </tr>
              <tr>
                <td style="vertical-align:top;padding-right:12px;font-size:18px;">🔍</td>
                <td style="padding-bottom:12px;">
                  <p style="margin:0;font-size:14px;color:#334155;font-weight:600;">
                    Запустить GEO мониторинг
                  </p>
                  <p style="margin:2px 0 0;font-size:13px;color:#64748b;">
                    Увидеть как Алиса и ГигаЧат говорят о вас сейчас
                  </p>
                </td>
              </tr>
              <tr>
                <td style="vertical-align:top;padding-right:12px;font-size:18px;">📋</td>
                <td>
                  <p style="margin:0;font-size:14px;color:#334155;font-weight:600;">
                    Получить план действий
                  </p>
                  <p style="margin:2px 0 0;font-size:13px;color:#64748b;">
                    AI-агент подскажет конкретные шаги для улучшения позиций
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      {_cta_button(dashboard_url, "Открыть дашборд →")}

      <p style="margin:24px 0 0;font-size:13px;color:#94a3b8;text-align:center;">
        Если у вас возникнут вопросы — просто ответьте на это письмо.
      </p>
    """
    return _base_wrapper(content)


def _build_weekly_report_html(name: str, data: WeeklyReportData) -> str:
    dashboard_url = f"https://{settings.domain}/dashboard"

    def _rate_color(rate: float) -> str:
        if rate >= 50:
            return "#16a34a"   # зелёный
        if rate >= 20:
            return "#d97706"   # жёлтый
        return "#dc2626"       # красный

    alice_color = _rate_color(data.alice_mention_rate)
    gigachat_color = _rate_color(data.gigachat_mention_rate)

    # Блок задач
    tasks_html = ""
    if data.top_tasks:
        tasks_rows = ""
        category_labels = {
            "content": "Контент",
            "faq": "FAQ",
            "technical": "Техническое",
            "mentions": "Упоминания",
            "tone": "Тональность",
        }
        for i, task in enumerate(data.top_tasks[:3], start=1):
            cat = task.get("category", "")
            cat_label = category_labels.get(cat, cat)
            tasks_rows += f"""
            <tr>
              <td style="padding:12px 0;border-bottom:1px solid #f1f5f9;">
                <div style="display:inline-block;font-size:11px;font-weight:600;
                            color:#6366f1;background:#eff0ff;border-radius:4px;
                            padding:2px 8px;margin-bottom:4px;">
                  #{i} · {cat_label}
                </div>
                <p style="margin:4px 0 0;font-size:14px;color:#1e293b;font-weight:600;">
                  {task.get('title', '—')}
                </p>
                <p style="margin:2px 0 0;font-size:13px;color:#64748b;">
                  {task.get('description', '')[:120]}
                </p>
              </td>
            </tr>"""

        tasks_html = f"""
        <h3 style="margin:28px 0 12px;font-size:15px;color:#1e293b;font-weight:700;">
          📋 Топ задачи из плана действий
        </h3>
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          {tasks_rows}
        </table>"""

    content = f"""
      <h2 style="margin:0 0 4px;font-size:20px;color:#1e293b;">
        Ваш еженедельный отчёт
      </h2>
      <p style="margin:0 0 28px;font-size:14px;color:#64748b;">
        Проект: <strong>{data.project_name}</strong>
      </p>

      <!-- Статистика -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="margin-bottom:24px;">
        <tr>
          <!-- Алиса -->
          <td width="33%" style="padding-right:8px;">
            <div style="background:#f8fafc;border-radius:8px;padding:16px;text-align:center;
                        border-left:3px solid {alice_color};">
              <p style="margin:0;font-size:28px;font-weight:800;color:{alice_color};">
                {data.alice_mention_rate:.0f}%
              </p>
              <p style="margin:4px 0 0;font-size:12px;color:#64748b;font-weight:600;">
                Алиса
              </p>
            </div>
          </td>
          <!-- ГигаЧат -->
          <td width="33%" style="padding:0 4px;">
            <div style="background:#f8fafc;border-radius:8px;padding:16px;text-align:center;
                        border-left:3px solid {gigachat_color};">
              <p style="margin:0;font-size:28px;font-weight:800;color:{gigachat_color};">
                {data.gigachat_mention_rate:.0f}%
              </p>
              <p style="margin:4px 0 0;font-size:12px;color:#64748b;font-weight:600;">
                ГигаЧат
              </p>
            </div>
          </td>
          <!-- Краулеры -->
          <td width="33%" style="padding-left:8px;">
            <div style="background:#f8fafc;border-radius:8px;padding:16px;text-align:center;
                        border-left:3px solid #6366f1;">
              <p style="margin:0;font-size:28px;font-weight:800;color:#6366f1;">
                {data.crawler_visits}
              </p>
              <p style="margin:4px 0 0;font-size:12px;color:#64748b;font-weight:600;">
                Визитов AI
              </p>
            </div>
          </td>
        </tr>
      </table>

      {tasks_html}

      {_cta_button(dashboard_url, "Открыть дашборд →")}
    """
    return _base_wrapper(content)


# ─── Синхронная отправка ──────────────────────────────────────────────────────

def _smtp_send(to_email: str, subject: str, html_body: str) -> None:
    """
    Синхронная отправка письма через SMTP.
    Поддерживает SSL (465) и STARTTLS (587).
    Не вызывает при пустых настройках.
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("email_skipped_no_smtp_config", to=to_email, subject=subject)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()

    try:
        if settings.smtp_port == 465:
            # SSL-соединение
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as smtp:
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.sendmail(msg["From"], to_email, msg.as_bytes())
        else:
            # STARTTLS (587 и др.)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.sendmail(msg["From"], to_email, msg.as_bytes())

        logger.info("email_sent", to=to_email, subject=subject)

    except smtplib.SMTPException as exc:
        # Логируем, не поднимаем — не ломаем основной поток приложения
        logger.error("email_send_failed", to=to_email, subject=subject, error=str(exc))


# ─── Async API ────────────────────────────────────────────────────────────────

async def send_welcome_email(to_email: str, name: str) -> None:
    """Отправляет приветственное письмо после регистрации."""
    subject = f"Добро пожаловать в {PRODUCT_NAME}"
    html = _build_welcome_html(name)
    await asyncio.to_thread(_smtp_send, to_email, subject, html)


async def send_weekly_report(to_email: str, name: str, data: WeeklyReportData) -> None:
    """Отправляет еженедельный отчёт по AI-видимости."""
    subject = "Ваш еженедельный отчёт по AI-видимости"
    html = _build_weekly_report_html(name, data)
    await asyncio.to_thread(_smtp_send, to_email, subject, html)


# ─── Sync-версии для вызова из Celery (нет event loop) ───────────────────────

def send_welcome_email_sync(to_email: str, name: str) -> None:
    subject = f"Добро пожаловать в {PRODUCT_NAME}"
    _smtp_send(to_email, subject, _build_welcome_html(name))


def send_weekly_report_sync(to_email: str, name: str, data: WeeklyReportData) -> None:
    subject = "Ваш еженедельный отчёт по AI-видимости"
    _smtp_send(to_email, subject, _build_weekly_report_html(name, data))
