"use client";

/**
 * Страница мониторинга GEO.
 * Таблица результатов проверок промптов через Алису и ГигаЧат.
 * Фильтры по платформе и дате. Статистика сверху.
 */
import { useState } from "react";
import useSWR from "swr";
import { useSession } from "next-auth/react";
import clsx from "clsx";
import { monitoringApi, projectsApi, type MonitoringResult, type MonitoringStats } from "@/lib/api";

function useToken(): string | null {
  const { data: session } = useSession();
  return (session as { accessToken?: string })?.accessToken ?? null;
}

// ─── Бейдж тональности ───────────────────────────────────────────────────────

function SentimentBadge({ sentiment }: { sentiment: string | null }) {
  if (!sentiment) return <span className="text-gray-400 text-xs">—</span>;

  const styles: Record<string, string> = {
    positive: "bg-green-100 text-green-700",
    neutral: "bg-gray-100 text-gray-600",
    negative: "bg-red-100 text-red-700",
  };

  const labels: Record<string, string> = {
    positive: "позитивная",
    neutral: "нейтральная",
    negative: "негативная",
  };

  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", styles[sentiment])}>
      {labels[sentiment] ?? sentiment}
    </span>
  );
}

// ─── Бейдж платформы ─────────────────────────────────────────────────────────

function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded font-medium",
        platform === "alice"
          ? "bg-yellow-100 text-yellow-800"
          : "bg-blue-100 text-blue-800"
      )}
    >
      {platform === "alice" ? "Алиса" : "ГигаЧат"}
    </span>
  );
}

// ─── Строка таблицы ──────────────────────────────────────────────────────────

function ResultRow({ result }: { result: MonitoringResult }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-4 py-3 text-sm text-gray-900 max-w-xs">
          <span className="line-clamp-2">{result.prompt}</span>
        </td>
        <td className="px-4 py-3">
          <PlatformBadge platform={result.platform} />
        </td>
        <td className="px-4 py-3 text-center">
          {result.mentioned ? (
            <span className="text-green-600 font-medium text-sm">✓ Да</span>
          ) : (
            <span className="text-red-500 text-sm">✗ Нет</span>
          )}
        </td>
        <td className="px-4 py-3 text-sm text-center text-gray-600">
          {result.position ?? "—"}
        </td>
        <td className="px-4 py-3">
          <SentimentBadge sentiment={result.sentiment} />
        </td>
        <td className="px-4 py-3 text-xs text-gray-400">
          {new Date(result.checked_at).toLocaleString("ru-RU", {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </td>
      </tr>
      {expanded && result.response_text && (
        <tr className="bg-indigo-50">
          <td colSpan={6} className="px-4 py-3">
            <p className="text-xs font-medium text-indigo-700 mb-1">Ответ AI:</p>
            <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
              {result.response_text}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

// ─── Карточка статистики ──────────────────────────────────────────────────────

function StatBlock({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="text-center">
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

// ─── Основной компонент ───────────────────────────────────────────────────────

export default function MonitoringPage() {
  const token = useToken();
  const [platform, setPlatform] = useState<"all" | "alice" | "gigachat">("all");

  // Получаем первый проект
  const { data: projects } = useSWR(
    token ? ["projects", token] : null,
    ([, t]) => projectsApi.list(t)
  );

  const projectId = projects?.[0]?.id;

  // Результаты мониторинга
  const { data: results, isLoading } = useSWR<MonitoringResult[]>(
    token && projectId ? ["monitoring-results", token, projectId] : null,
    ([, t, pid]) => monitoringApi.results(t, pid)
  );

  // Статистика
  const { data: stats } = useSWR<MonitoringStats>(
    token && projectId ? ["monitoring-stats", token, projectId] : null,
    ([, t, pid]) => monitoringApi.stats(t, pid)
  );

  // Фильтрация
  const filtered = results?.filter((r) =>
    platform === "all" ? true : r.platform === platform
  );

  const mentionRate = stats
    ? `${(stats.mention_rate * 100).toFixed(0)}%`
    : "—";

  const avgPos = stats?.avg_position
    ? `${stats.avg_position.toFixed(1)}`
    : "—";

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">GEO Мониторинг</h1>
        <p className="text-sm text-gray-500 mt-1">
          Проверки упоминаний бренда в Алисе и ГигаЧате
        </p>
      </div>

      {/* Статистика */}
      {stats && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 divide-x divide-gray-100">
            <StatBlock label="Всего проверок" value={stats.total} />
            <StatBlock
              label="С упоминанием"
              value={stats.mentioned}
              sub={`${mentionRate} от всех`}
            />
            <StatBlock
              label="Алиса"
              value={`${((stats.by_platform?.alice?.mention_rate ?? 0) * 100).toFixed(0)}%`}
              sub={`${stats.by_platform?.alice?.total ?? 0} проверок`}
            />
            <StatBlock
              label="ГигаЧат"
              value={`${((stats.by_platform?.gigachat?.mention_rate ?? 0) * 100).toFixed(0)}%`}
              sub={`${stats.by_platform?.gigachat?.total ?? 0} проверок`}
            />
          </div>
          {stats.avg_position !== null && (
            <p className="text-xs text-gray-400 text-center mt-4">
              Средняя позиция упоминания: {avgPos}-е предложение в ответе
            </p>
          )}
        </div>
      )}

      {/* Фильтры */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-gray-500">Платформа:</span>
        {(["all", "alice", "gigachat"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setPlatform(p)}
            className={clsx(
              "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              platform === p
                ? "bg-indigo-600 text-white"
                : "bg-white text-gray-600 border border-gray-200 hover:border-indigo-300"
            )}
          >
            {p === "all" ? "Все" : p === "alice" ? "Алиса" : "ГигаЧат"}
          </button>
        ))}
        {filtered && (
          <span className="ml-auto text-xs text-gray-400">
            {filtered.length} записей
          </span>
        )}
      </div>

      {/* Таблица */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-40 text-gray-400">
            Загрузка...
          </div>
        ) : !filtered || filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <p className="text-sm">Нет данных мониторинга</p>
            <p className="text-xs mt-1">
              Запустите мониторинг на главной странице
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Промпт
                  </th>
                  <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Платформа
                  </th>
                  <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-center">
                    Упомянут
                  </th>
                  <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-center">
                    Позиция
                  </th>
                  <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Тональность
                  </th>
                  <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Дата
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((result) => (
                  <ResultRow key={result.id} result={result} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-400 text-center">
        Кликните на строку чтобы увидеть полный ответ AI
      </p>
    </div>
  );
}
