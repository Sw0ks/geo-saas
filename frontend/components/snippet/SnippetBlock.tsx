"use client";

/**
 * Компонент блока с кодом трекер-сниппета.
 * Показывает код для PHP или Python с кнопкой копирования.
 * Подставляет уникальный токен клиента в код.
 */
import { useState } from "react";
import clsx from "clsx";

interface SnippetBlockProps {
  trackerToken: string;
  trackerEndpoint?: string;
}

type Language = "python" | "php" | "django" | "flask";

const LANG_LABELS: Record<Language, string> = {
  python: "FastAPI",
  django: "Django",
  flask: "Flask",
  php: "PHP",
};

function buildPythonSnippet(token: string, endpoint: string): string {
  return `# FastAPI / Starlette middleware
# Установите: pip install httpx
# Вставьте в main.py перед запуском приложения

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

TRACKER_TOKEN = "${token}"
TRACKER_ENDPOINT = "${endpoint}"

AI_BOT_KEYWORDS = [
    "alicebot", "yandexgpt", "yandexbot",
    "gigabot", "gigachat", "gptbot", "claudebot",
    "perplexitybot",
]

class AICrawlerTrackerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ua = request.headers.get("user-agent", "").lower()
        if any(kw in ua for kw in AI_BOT_KEYWORDS):
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    await client.get(TRACKER_ENDPOINT, params={
                        "token": TRACKER_TOKEN,
                        "url": str(request.url.path),
                        "bot": request.headers.get("user-agent", ""),
                        "host": request.headers.get("host", ""),
                    })
            except Exception:
                pass  # Никогда не ломаем сайт клиента
        return await call_next(request)

# app.add_middleware(AICrawlerTrackerMiddleware)`;
}

function buildDjangoSnippet(token: string, endpoint: string): string {
  return `# Django middleware
# Установите: pip install requests
# Добавьте в settings.py в MIDDLEWARE (последним):
#   'myapp.middleware.AICrawlerTrackerMiddleware'

import threading
import requests

TRACKER_TOKEN = "${token}"
TRACKER_ENDPOINT = "${endpoint}"

AI_BOT_KEYWORDS = [
    "alicebot", "yandexgpt", "yandexbot",
    "gigabot", "gigachat", "gptbot", "claudebot",
    "perplexitybot",
]

class AICrawlerTrackerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ua = request.META.get("HTTP_USER_AGENT", "").lower()
        if any(kw in ua for kw in AI_BOT_KEYWORDS):
            threading.Thread(target=self._track, args=(request,), daemon=True).start()
        return self.get_response(request)

    def _track(self, request):
        try:
            requests.get(TRACKER_ENDPOINT, params={
                "token": TRACKER_TOKEN,
                "url": request.path,
                "bot": request.META.get("HTTP_USER_AGENT", ""),
                "host": request.get_host(),
            }, timeout=1.0)
        except Exception:
            pass`;
}

function buildFlaskSnippet(token: string, endpoint: string): string {
  return `# Flask
# Установите: pip install requests
# Вставьте в app.py

import threading
import requests
from flask import Flask, request as flask_request

TRACKER_TOKEN = "${token}"
TRACKER_ENDPOINT = "${endpoint}"

AI_BOT_KEYWORDS = [
    "alicebot", "yandexgpt", "yandexbot",
    "gigabot", "gigachat", "gptbot", "claudebot",
    "perplexitybot",
]

def track_if_bot(app: Flask):
    @app.before_request
    def _track():
        ua = flask_request.headers.get("User-Agent", "").lower()
        if any(kw in ua for kw in AI_BOT_KEYWORDS):
            def _send():
                try:
                    requests.get(TRACKER_ENDPOINT, params={
                        "token": TRACKER_TOKEN,
                        "url": flask_request.path,
                        "bot": flask_request.headers.get("User-Agent", ""),
                        "host": flask_request.host,
                    }, timeout=1.0)
                except Exception:
                    pass
            threading.Thread(target=_send, daemon=True).start()

# track_if_bot(app)`;
}

function buildPhpSnippet(token: string, endpoint: string): string {
  return `<?php
// PHP трекер для WordPress / Bitrix / любого PHP-сайта
// Вставьте в начало index.php или functions.php (WordPress)

define('GEO_TRACKER_TOKEN', '${token}');
define('GEO_TRACKER_ENDPOINT', '${endpoint}');

$ai_bot_keywords = [
    'alicebot', 'yandexgpt', 'yandexbot',
    'gigabot', 'gigachat', 'gptbot', 'claudebot',
    'perplexitybot',
];

function geo_track_ai_bot() {
    global $ai_bot_keywords;
    $ua = strtolower($_SERVER['HTTP_USER_AGENT'] ?? '');
    $is_bot = false;
    foreach ($ai_bot_keywords as $kw) {
        if (str_contains($ua, $kw)) { $is_bot = true; break; }
    }
    if (!$is_bot) return;

    $url = GEO_TRACKER_ENDPOINT . '?' . http_build_query([
        'token' => GEO_TRACKER_TOKEN,
        'url'   => $_SERVER['REQUEST_URI'] ?? '/',
        'bot'   => $_SERVER['HTTP_USER_AGENT'] ?? '',
        'host'  => $_SERVER['HTTP_HOST'] ?? '',
    ]);

    // Неблокирующий запрос через curl
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 1,
        CURLOPT_NOSIGNAL       => 1,
    ]);
    curl_exec($ch);
    curl_close($ch);
}

geo_track_ai_bot();
?>`;
}

function getSnippet(lang: Language, token: string, endpoint: string): string {
  switch (lang) {
    case "python": return buildPythonSnippet(token, endpoint);
    case "django": return buildDjangoSnippet(token, endpoint);
    case "flask":  return buildFlaskSnippet(token, endpoint);
    case "php":    return buildPhpSnippet(token, endpoint);
  }
}

export function SnippetBlock({ trackerToken, trackerEndpoint }: SnippetBlockProps) {
  const endpoint = trackerEndpoint ?? `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/v1/track`;
  const [lang, setLang] = useState<Language>("python");
  const [copied, setCopied] = useState(false);

  const code = getSnippet(lang, trackerToken, endpoint);

  async function handleCopy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-4">
      {/* Инструкция по установке */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-900 mb-3">Как установить трекер</h3>
        <ol className="space-y-3">
          <li className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center">1</span>
            <div>
              <p className="text-sm font-medium text-gray-900">Скопируйте ваш токен</p>
              <p className="text-xs text-gray-500 mt-0.5">Он уже подставлен в код ниже. Можно скопировать отдельно из строки «Ваш токен».</p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center">2</span>
            <div>
              <p className="text-sm font-medium text-gray-900">Вставьте код на свой сайт</p>
              <p className="text-xs text-gray-500 mt-0.5">Выберите вкладку с вашим фреймворком (FastAPI, Django, Flask или PHP) и вставьте код согласно комментарию в начале сниппета.</p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center">3</span>
            <div>
              <p className="text-sm font-medium text-gray-900">Проверьте в разделе «AI Краулер»</p>
              <p className="text-xs text-gray-500 mt-0.5">После деплоя зайдите на эту страницу — первые визиты AI ботов появятся в таблице ниже.</p>
            </div>
          </li>
        </ol>
      </div>

    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Шапка */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
        <div className="flex gap-1">
          {(Object.keys(LANG_LABELS) as Language[]).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={clsx(
                "px-3 py-1 rounded text-xs font-medium transition-colors",
                lang === l
                  ? "bg-indigo-600 text-white"
                  : "text-gray-600 hover:bg-gray-100"
              )}
            >
              {LANG_LABELS[l]}
            </button>
          ))}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-600 transition-colors"
        >
          {copied ? (
            <>✓ Скопировано</>
          ) : (
            <>📋 Копировать</>
          )}
        </button>
      </div>

      {/* Токен */}
      <div className="px-4 py-2 bg-indigo-50 border-b border-indigo-100 flex items-center gap-2">
        <span className="text-xs text-indigo-600 font-medium">Ваш токен:</span>
        <code className="text-xs font-mono text-indigo-800 bg-indigo-100 px-2 py-0.5 rounded select-all">
          {trackerToken}
        </code>
      </div>

      {/* Код */}
      <div className="overflow-x-auto">
        <pre className="p-4 text-xs font-mono text-gray-800 leading-relaxed whitespace-pre">
          {code}
        </pre>
      </div>
    </div>
    </div>
  );
}
