"use client";

/**
 * Страница плана действий от AI агента.
 * Список задач с приоритетами, категориями, описаниями.
 * Кнопка генерации нового плана. Смена статуса плана.
 */
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { useSession } from "next-auth/react";
import clsx from "clsx";
import { agentApi, projectsApi, type ActionTask, type GeneratePlanResponse } from "@/lib/api";

function useToken(): string | null {
  const { data: session } = useSession();
  return (session as { accessToken?: string })?.accessToken ?? null;
}

// ─── Бейдж категории ──────────────────────────────────────────────────────────

const CATEGORY_STYLES: Record<string, { label: string; className: string }> = {
  content:   { label: "Контент",    className: "bg-blue-100 text-blue-800" },
  faq:       { label: "FAQ",        className: "bg-purple-100 text-purple-800" },
  technical: { label: "Технически", className: "bg-orange-100 text-orange-800" },
  mentions:  { label: "Упоминания", className: "bg-green-100 text-green-800" },
  tone:      { label: "Тональность", className: "bg-red-100 text-red-800" },
};

function CategoryBadge({ category }: { category: string }) {
  const style = CATEGORY_STYLES[category] ?? { label: category, className: "bg-gray-100 text-gray-700" };
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded font-medium", style.className)}>
      {style.label}
    </span>
  );
}

// ─── Карточка задачи ─────────────────────────────────────────────────────────

function TaskCard({ task, index }: { task: ActionTask; index: number }) {
  const [expanded, setExpanded] = useState(index === 0); // первая открыта по умолчанию

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-4 p-4 text-left hover:bg-gray-50 transition-colors"
      >
        {/* Номер приоритета */}
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">
          {task.priority}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <CategoryBadge category={task.category} />
          </div>
          <h3 className="font-medium text-gray-900 leading-snug">{task.title}</h3>
        </div>

        <span className="text-gray-400 flex-shrink-0 mt-1">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-50">
          <div className="pt-3">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Что сделать
            </p>
            <p className="text-sm text-gray-700 leading-relaxed">{task.description}</p>
          </div>

          <div className="bg-green-50 rounded-lg px-3 py-2.5">
            <p className="text-xs font-medium text-green-700 uppercase tracking-wide mb-1">
              Ожидаемый результат
            </p>
            <p className="text-sm text-green-800 leading-relaxed">{task.expected_result}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Бейдж статуса ────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  new:         { label: "Новый",       className: "bg-gray-100 text-gray-600" },
  in_progress: { label: "В работе",    className: "bg-blue-100 text-blue-700" },
  done:        { label: "Выполнен",    className: "bg-green-100 text-green-700" },
};

// ─── Основной компонент ───────────────────────────────────────────────────────

export default function PlanPage() {
  const token = useToken();
  const { mutate } = useSWRConfig();
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Первый проект
  const { data: projects } = useSWR(
    token ? ["projects", token] : null,
    ([, t]) => projectsApi.list(t)
  );

  const project = projects?.[0];
  const projectId = project?.id;

  // Последний план
  const { data: planData, isLoading } = useSWR<GeneratePlanResponse | null>(
    token && projectId ? ["latest-plan", token, projectId] : null,
    ([, t, pid]) => agentApi.latestPlan(t, pid).catch(() => null)
  );

  // Извлекаем задачи и summary из tasks_json
  const tasks: ActionTask[] = [];
  let summary = planData?.summary ?? "";

  if (planData?.plan?.tasks_json) {
    for (const item of planData.plan.tasks_json) {
      if ("_summary" in item && item._summary) {
        summary = item._summary as string;
      } else if ("priority" in item) {
        tasks.push(item as ActionTask);
      }
    }
  }

  const planId = planData?.plan?.id;
  const planStatus = planData?.plan?.status ?? "new";

  // Генерация нового плана
  async function handleGenerate() {
    if (!token || !projectId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      await agentApi.generatePlan(token, projectId);
      // Инвалидируем кэш SWR чтобы подтянуть новый план
      await mutate(["latest-plan", token, projectId]);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка генерации плана";
      setGenerateError(msg);
    } finally {
      setGenerating(false);
    }
  }

  // Смена статуса плана
  async function handleStatusChange(newStatus: "new" | "in_progress" | "done") {
    if (!token || !planId) return;
    try {
      await agentApi.updateStatus(token, planId, newStatus);
      await mutate(["latest-plan", token, projectId]);
    } catch {
      // ignore
    }
  }

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">План GEO-оптимизации</h1>
          <p className="text-sm text-gray-500 mt-1">
            AI агент анализирует данные мониторинга и составляет конкретные задачи
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {generating ? (
            <>
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Генерируем план...
            </>
          ) : (
            "✨ Сгенерировать новый план"
          )}
        </button>
      </div>

      {/* Ошибка генерации */}
      {generateError && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 text-sm">
          {generateError}
        </div>
      )}

      {/* Состояние загрузки */}
      {isLoading && (
        <div className="flex items-center justify-center h-40 text-gray-400">
          Загрузка...
        </div>
      )}

      {/* Нет плана */}
      {!isLoading && !planData && (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
          <p className="text-4xl mb-4">📋</p>
          <h3 className="font-medium text-gray-900 mb-2">План ещё не создан</h3>
          <p className="text-sm text-gray-500 mb-6 max-w-sm mx-auto">
            Нажмите «Сгенерировать новый план» — AI агент проанализирует данные мониторинга
            и составит пошаговый план улучшения GEO-позиций вашего бренда.
          </p>
          <p className="text-xs text-gray-400">
            Для лучшего результата сначала запустите мониторинг
          </p>
        </div>
      )}

      {/* Есть план */}
      {planData && (
        <>
          {/* Мета: дата, статус */}
          <div className="flex items-center gap-4 flex-wrap">
            <span className="text-xs text-gray-400">
              Сгенерирован:{" "}
              {new Date(planData.plan.generated_at).toLocaleString("ru-RU", {
                day: "numeric",
                month: "long",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <span className="text-xs text-gray-400">•</span>
            <span className="text-xs text-gray-500">Задач: {tasks.length}</span>

            {/* Переключатель статуса */}
            <div className="ml-auto flex items-center gap-1">
              <span className="text-xs text-gray-500 mr-2">Статус:</span>
              {(["new", "in_progress", "done"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => handleStatusChange(s)}
                  className={clsx(
                    "text-xs px-2.5 py-1 rounded font-medium transition-colors",
                    planStatus === s
                      ? STATUS_STYLES[s].className
                      : "text-gray-400 hover:text-gray-600"
                  )}
                >
                  {STATUS_STYLES[s].label}
                </button>
              ))}
            </div>
          </div>

          {/* Summary от агента */}
          {summary && (
            <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4">
              <p className="text-xs font-medium text-indigo-700 uppercase tracking-wide mb-2">
                Анализ ситуации от AI
              </p>
              <p className="text-sm text-indigo-900 leading-relaxed">{summary}</p>
            </div>
          )}

          {/* Список задач */}
          <div className="space-y-3">
            {tasks.length > 0 ? (
              tasks.map((task, i) => (
                <TaskCard key={`${task.priority}-${task.title}`} task={task} index={i} />
              ))
            ) : (
              <div className="text-center text-gray-400 text-sm py-8">
                Задачи не найдены в плане
              </div>
            )}
          </div>

          {/* Подсказка */}
          <p className="text-xs text-gray-400 text-center">
            Выполните задачи по порядку приоритета (1 — первоочередное).
            После внедрения изменений запустите новый мониторинг.
          </p>
        </>
      )}
    </div>
  );
}
