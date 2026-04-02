"use client";

/**
 * Страница AI Краулер.
 * Таблица событий (бот, страница, время, верифицирован).
 * Статистика по ботам. Блок установки сниппета с токеном клиента.
 */
import { useState } from "react";
import useSWR from "swr";
import { useSession } from "next-auth/react";
import clsx from "clsx";
import { crawlerApi, projectsApi, type CrawlerEvent, type CrawlerStats } from "@/lib/api";
import { SnippetBlock } from "@/components/snippet/SnippetBlock";

function useToken(): string | null {
  const { data: session } = useSession();
  return (session as { accessToken?: string })?.accessToken ?? null;
}

// ─── Бейдж бота ──────────────────────────────────────────────────────────────

const BOT_COLORS: Record<string, string> = {
  AliceBot: "bg-yellow-100 text-yellow-800",
  YandexBot: "bg-orange-100 text-orange-800",
  GigaBot: "bg-green-100 text-green-800",
  GPTBot: "bg-teal-100 text-teal-800",
  ClaudeBot: "bg-purple-100 text-purple-800",
  PerplexityBot: "bg-pink-100 text-pink-800",
  Other: "bg-gray-100 text-gray-600",
};

function BotBadge({ botName }: { botName: string }) {
  const style = BOT_COLORS[botName] ?? BOT_COLORS.Other;
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded font-medium", style)}>
      {botName}
    </span>
  );
}

// ─── Таблица событий ─────────────────────────────────────────────────────────

function EventsTable({ events }: { events: CrawlerEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-gray-400">
        <p className="text-sm">Ещё нет событий</p>
        <p className="text-xs mt-1">Установите сниппет на ваш сайт (см. ниже)</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Бот
            </th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Страница
            </th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              IP
            </th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-center">
              Верифицирован
            </th>
            <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Время
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {events.map((event) => (
            <tr key={event.id} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <BotBadge botName={event.bot_name} />
              </td>
              <td className="px-4 py-3 text-sm text-gray-700 font-mono max-w-xs truncate">
                {event.url_path}
              </td>
              <td className="px-4 py-3 text-xs text-gray-500 font-mono">
                {event.ip ?? "—"}
              </td>
              <td className="px-4 py-3 text-center">
                {event.verified ? (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                    ✓ Да
                  </span>
                ) : (
                  <span className="text-xs text-gray-400">—</span>
                )}
              </td>
              <td className="px-4 py-3 text-xs text-gray-400">
                {new Date(event.visited_at).toLocaleString("ru-RU", {
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Статистика по ботам ──────────────────────────────────────────────────────

function BotStats({ stats }: { stats: CrawlerStats }) {
  const totalBots = Object.values(stats.by_bot).reduce((a, b) => a + b, 0);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {Object.entries(stats.by_bot)
        .sort((a, b) => b[1] - a[1])
        .map(([bot, count]) => {
          const pct = totalBots > 0 ? Math.round((count / totalBots) * 100) : 0;
          return (
            <div key={bot} className="bg-white rounded-lg border border-gray-200 p-3 text-center">
              <p className="text-xl font-bold text-gray-900">{count}</p>
              <BotBadge botName={bot} />
              <p className="text-xs text-gray-400 mt-1">{pct}%</p>
            </div>
          );
        })}
    </div>
  );
}

// ─── Основной компонент ───────────────────────────────────────────────────────

export default function CrawlerPage() {
  const token = useToken();
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [botFilter, setBotFilter] = useState<string>("all");

  // Первый проект
  const { data: projects } = useSWR(
    token ? ["projects", token] : null,
    ([, t]) => projectsApi.list(t)
  );

  const project = projects?.[0];
  const projectId = project?.id;

  // Статистика
  const { data: stats } = useSWR<CrawlerStats>(
    token && projectId ? ["crawler-stats", token, projectId] : null,
    ([, t, pid]) => crawlerApi.stats(t, pid)
  );

  // События
  const { data: events, isLoading } = useSWR<CrawlerEvent[]>(
    token && projectId ? ["crawler-events-full", token, projectId, botFilter, verifiedOnly] : null,
    ([, t, pid, bot, verified]) =>
      crawlerApi.events(t, pid, {
        bot_name: bot === "all" ? undefined : bot,
        verified_only: verified as boolean,
        limit: 100,
      })
  );

  // Токен трекера
  const { data: tokenData } = useSWR(
    token && projectId ? ["crawler-token", token, projectId] : null,
    ([, t, pid]) => crawlerApi.token(t, pid)
  );

  const trackerToken = tokenData?.tracker_token ?? project?.tracker_token ?? "";

  const botNames = stats ? Object.keys(stats.by_bot) : [];

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Краулер</h1>
        <p className="text-sm text-gray-500 mt-1">
          Мониторинг визитов AI-ботов на ваш сайт
        </p>
      </div>

      {/* Метрики */}
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
            <p className="text-3xl font-bold text-gray-900">{stats.total_visits}</p>
            <p className="text-xs text-gray-500 mt-1">Всего визитов</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
            <p className="text-3xl font-bold text-green-700">{stats.verified_visits}</p>
            <p className="text-xs text-gray-500 mt-1">Верифицировано (Яндекс IP)</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
            <p className="text-3xl font-bold text-indigo-700">
              {Object.keys(stats.by_bot).length}
            </p>
            <p className="text-xs text-gray-500 mt-1">Типов ботов</p>
          </div>
        </div>
      )}

      {/* Статистика по ботам */}
      {stats && stats.total_visits > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Визиты по ботам</h2>
          <BotStats stats={stats} />
        </div>
      )}

      {/* Фильтры событий */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-gray-500">Бот:</span>
        <button
          onClick={() => setBotFilter("all")}
          className={clsx(
            "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
            botFilter === "all"
              ? "bg-indigo-600 text-white"
              : "bg-white text-gray-600 border border-gray-200 hover:border-indigo-300"
          )}
        >
          Все
        </button>
        {botNames.map((bot) => (
          <button
            key={bot}
            onClick={() => setBotFilter(bot)}
            className={clsx(
              "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              botFilter === bot
                ? "bg-indigo-600 text-white"
                : "bg-white text-gray-600 border border-gray-200 hover:border-indigo-300"
            )}
          >
            {bot}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={verifiedOnly}
            onChange={(e) => setVerifiedOnly(e.target.checked)}
            className="rounded border-gray-300 text-indigo-600"
          />
          Только верифицированные
        </label>
      </div>

      {/* Таблица событий */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-40 text-gray-400">
            Загрузка...
          </div>
        ) : (
          <EventsTable events={events ?? []} />
        )}
      </div>

      {/* Топ страниц */}
      {stats && stats.top_pages.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-900 mb-4">Топ страниц по визитам</h2>
          <div className="space-y-2">
            {stats.top_pages.map(({ url, visits }) => {
              const maxVisits = stats.top_pages[0]?.visits ?? 1;
              const pct = (visits / maxVisits) * 100;
              return (
                <div key={url} className="flex items-center gap-3">
                  <span className="text-sm font-mono text-gray-700 w-48 truncate">{url}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-2">
                    <div
                      className="bg-indigo-400 h-2 rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-sm text-gray-500 w-8 text-right">{visits}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Сниппет */}
      <div>
        <div className="mb-3">
          <h2 className="font-semibold text-gray-900">Установка на сайт</h2>
          <p className="text-sm text-gray-500 mt-1">
            Вставьте код в ваш сайт чтобы отслеживать визиты AI-ботов.
            Скрипт работает в фоне и не замедляет сайт.
          </p>
        </div>
        {trackerToken ? (
          <SnippetBlock trackerToken={trackerToken} />
        ) : (
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-sm">
            Загрузка токена...
          </div>
        )}
      </div>
    </div>
  );
}
