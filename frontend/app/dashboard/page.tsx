"use client";

/**
 * Главная страница дашборда.
 * Метрики: видимость Алисы, видимость ГигаЧата, визиты краулера, задачи плана.
 * График видимости по дням, последние события краулера, кнопка запуска мониторинга.
 * Если у пользователя нет проектов — редирект на /dashboard/onboarding.
 */
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { useSession } from "next-auth/react";
import Link from "next/link";
import {
  monitoringApi,
  crawlerApi,
  agentApi,
  projectsApi,
  type MonitoringStats,
  type CrawlerStats,
  type CrawlerEvent,
  type Project,
} from "@/lib/api";

// ─── Хук для получения токена из сессии ──────────────────────────────────────

function useToken(): string | null {
  const { data: session } = useSession();
  return (session as { accessToken?: string })?.accessToken ?? null;
}

// ─── Метрика ─────────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  color = "indigo",
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: "indigo" | "green" | "blue" | "purple";
}) {
  const colors = {
    indigo: "bg-indigo-50 text-indigo-700",
    green: "bg-green-50 text-green-700",
    blue: "bg-blue-50 text-blue-700",
    purple: "bg-purple-50 text-purple-700",
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className={`text-3xl font-bold ${colors[color].split(" ")[1]}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

// ─── Мини-график видимости ────────────────────────────────────────────────────

function VisibilityChart({ data }: { data: Array<{ date: string; count: number }> }) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
        Нет данных для графика
      </div>
    );
  }

  const max = Math.max(...data.map((d) => d.count), 1);
  const last30 = data.slice(-30);

  return (
    <div className="flex items-end gap-1 h-24">
      {last30.map((d) => (
        <div key={d.date} className="flex-1 flex flex-col items-center gap-1" title={`${d.date}: ${d.count}`}>
          <div
            className="w-full bg-indigo-400 rounded-sm"
            style={{ height: `${Math.max((d.count / max) * 80, 4)}px` }}
          />
        </div>
      ))}
    </div>
  );
}

// ─── Главный компонент ────────────────────────────────────────────────────────

export default function DashboardPage() {
  const token = useToken();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [runningMonitoring, setRunningMonitoring] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  // Баннер «первый мониторинг запущен» после онбординга
  const [showOnboardingBanner, setShowOnboardingBanner] = useState(
    searchParams.get("onboarding") === "1"
  );

  // Получаем первый проект пользователя
  const { data: projects } = useSWR(
    token ? ["projects", token] : null,
    ([, t]) => projectsApi.list(t)
  );

  // Редирект на онбординг если нет ни одного проекта
  useEffect(() => {
    if (projects && projects.length === 0) {
      router.replace("/dashboard/onboarding");
    }
  }, [projects, router]);

  const project: Project | undefined = projects?.[0];
  const projectId = project?.id;

  // Данные мониторинга
  const { data: monStats } = useSWR<MonitoringStats>(
    token && projectId ? ["monitoring-stats", token, projectId] : null,
    ([, t, pid]) => monitoringApi.stats(t, pid)
  );

  // Данные краулера
  const { data: crawlerStats } = useSWR<CrawlerStats>(
    token && projectId ? ["crawler-stats", token, projectId] : null,
    ([, t, pid]) => crawlerApi.stats(t, pid)
  );

  // Последние события краулера
  const { data: recentEvents } = useSWR<CrawlerEvent[]>(
    token && projectId ? ["crawler-events", token, projectId] : null,
    ([, t, pid]) => crawlerApi.events(t, pid, { limit: 5 })
  );

  // Последний план
  const { data: latestPlan } = useSWR(
    token && projectId ? ["latest-plan", token, projectId] : null,
    ([, t, pid]) => agentApi.latestPlan(t, pid).catch(() => null)
  );

  // Метрики
  const aliceRate = monStats?.by_platform?.alice?.mention_rate
    ? `${(monStats.by_platform.alice.mention_rate * 100).toFixed(0)}%`
    : "—";

  const gigachatRate = monStats?.by_platform?.gigachat?.mention_rate
    ? `${(monStats.by_platform.gigachat.mention_rate * 100).toFixed(0)}%`
    : "—";

  const totalVisits = crawlerStats?.total_visits ?? 0;

  const tasksCount =
    latestPlan?.plan?.tasks_json?.filter((t) => !("_summary" in t)).length ?? 0;

  // Запуск мониторинга
  async function handleRunMonitoring() {
    if (!token || !projectId) return;
    setRunningMonitoring(true);
    setRunMessage(null);
    try {
      const result = await monitoringApi.run(token, projectId);
      setRunMessage(result.message);
    } catch {
      setRunMessage("Ошибка при запуске мониторинга");
    } finally {
      setRunningMonitoring(false);
    }
  }

  // Пока данные не загружены или идёт редирект
  if (!projects || projects.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!project) return null;

  return (
    <div className="space-y-8">
      {/* Шапка */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
          <p className="text-sm text-gray-500 mt-0.5">{project.domain}</p>
        </div>
        <button
          onClick={handleRunMonitoring}
          disabled={runningMonitoring}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {runningMonitoring ? (
            <>
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Запускаем...
            </>
          ) : (
            "▶ Запустить мониторинг"
          )}
        </button>
      </div>

      {/* Баннер после онбординга */}
      {showOnboardingBanner && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3 flex items-start gap-3">
          <span className="text-2xl flex-shrink-0">🚀</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-indigo-900">
              Первый мониторинг запущен!
            </p>
            <p className="text-sm text-indigo-700 mt-0.5">
              Результаты появятся через 2–5 минут — Алиса и ГигаЧат проверяются по очереди.
              Обновите страницу чтобы увидеть данные.
            </p>
          </div>
          <button
            onClick={() => setShowOnboardingBanner(false)}
            className="text-indigo-400 hover:text-indigo-600 flex-shrink-0 text-lg leading-none"
          >
            ✕
          </button>
        </div>
      )}

      {/* Сообщение о запуске */}
      {runMessage && (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded-lg px-4 py-3 text-sm">
          {runMessage}
        </div>
      )}

      {/* 4 метрики */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Видимость в Алисе"
          value={aliceRate}
          sub={`из ${monStats?.by_platform?.alice?.total ?? 0} проверок`}
          color="indigo"
        />
        <MetricCard
          label="Видимость в ГигаЧате"
          value={gigachatRate}
          sub={`из ${monStats?.by_platform?.gigachat?.total ?? 0} проверок`}
          color="green"
        />
        <MetricCard
          label="Визиты AI ботов"
          value={totalVisits}
          sub={`верифицировано: ${crawlerStats?.verified_visits ?? 0}`}
          color="blue"
        />
        <MetricCard
          label="Задач в плане"
          value={tasksCount}
          sub={latestPlan ? `статус: ${latestPlan.plan.status}` : "план не создан"}
          color="purple"
        />
      </div>

      {/* График и события */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* График визитов краулера */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-900">Визиты AI ботов по дням</h2>
            <Link href="/dashboard/crawler" className="text-xs text-indigo-600 hover:underline">
              Все события →
            </Link>
          </div>
          <VisibilityChart data={crawlerStats?.by_day ?? []} />
          {crawlerStats && (
            <div className="flex gap-4 mt-4">
              {Object.entries(crawlerStats.by_bot)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 4)
                .map(([bot, count]) => (
                  <div key={bot} className="text-center">
                    <p className="text-lg font-bold text-gray-900">{count}</p>
                    <p className="text-xs text-gray-500">{bot}</p>
                  </div>
                ))}
            </div>
          )}
        </div>

        {/* Последние события краулера */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-900">Последние события</h2>
            <Link href="/dashboard/crawler" className="text-xs text-indigo-600 hover:underline">
              Все события →
            </Link>
          </div>
          {recentEvents && recentEvents.length > 0 ? (
            <div className="space-y-3">
              {recentEvents.map((event) => (
                <div key={event.id} className="flex items-center gap-3 text-sm">
                  <span className="w-6 h-6 bg-gray-100 rounded-full flex items-center justify-center text-xs">
                    🤖
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-900 truncate">{event.bot_name}</p>
                    <p className="text-gray-500 text-xs truncate">{event.url_path}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    {event.verified && (
                      <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                        ✓
                      </span>
                    )}
                    <p className="text-xs text-gray-400 mt-1">
                      {new Date(event.visited_at).toLocaleString("ru-RU", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-6">
              Ещё нет событий.<br />
              Установите сниппет на сайт →{" "}
              <Link href="/dashboard/crawler" className="text-indigo-600 underline">
                AI Краулер
              </Link>
            </p>
          )}
        </div>
      </div>

      {/* Быстрые ссылки */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link
          href="/dashboard/monitoring"
          className="bg-white border border-gray-200 rounded-xl p-4 hover:border-indigo-300 hover:shadow-sm transition group"
        >
          <span className="text-2xl">🔍</span>
          <h3 className="font-medium text-gray-900 mt-2 group-hover:text-indigo-700">
            Результаты мониторинга
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            {monStats?.total ?? 0} проверок, {monStats?.mentioned ?? 0} упоминаний
          </p>
        </Link>

        <Link
          href="/dashboard/crawler"
          className="bg-white border border-gray-200 rounded-xl p-4 hover:border-indigo-300 hover:shadow-sm transition group"
        >
          <span className="text-2xl">🤖</span>
          <h3 className="font-medium text-gray-900 mt-2 group-hover:text-indigo-700">
            AI Краулер
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            {totalVisits} визитов AI ботов
          </p>
        </Link>

        <Link
          href="/dashboard/plan"
          className="bg-white border border-gray-200 rounded-xl p-4 hover:border-indigo-300 hover:shadow-sm transition group"
        >
          <span className="text-2xl">📋</span>
          <h3 className="font-medium text-gray-900 mt-2 group-hover:text-indigo-700">
            Plan действий
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            {tasksCount > 0 ? `${tasksCount} задач от AI агента` : "Сгенерировать план"}
          </p>
        </Link>
      </div>
    </div>
  );
}
