"use client";

/**
 * Страница автоконтента.
 * Генерация статей, FAQ и описаний через Claude AI.
 * Список сгенерированного контента с фильтрами, копированием и сменой статуса.
 */
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { useSession } from "next-auth/react";
import clsx from "clsx";
import {
  contentApi,
  projectsApi,
  type ContentType,
  type ContentStatus,
  type GeneratedContent,
} from "@/lib/api";

function useToken(): string | null {
  const { data: session } = useSession();
  return (session as { accessToken?: string })?.accessToken ?? null;
}

// ─── Константы ────────────────────────────────────────────────────────────────

const CONTENT_TYPES: { key: ContentType; label: string; icon: string; description: string }[] = [
  {
    key: "article",
    label: "Статья",
    icon: "📝",
    description: "800–1200 слов, структурирована под Алису",
  },
  {
    key: "faq",
    label: "FAQ блок",
    icon: "❓",
    description: "5–10 вопросов-ответов, Алиса цитирует FAQ охотнее всего",
  },
  {
    key: "description",
    label: "Описание",
    icon: "🏷",
    description: "150–200 слов, идеально для карточки товара/услуги",
  },
];

const STATUS_LABELS: Record<ContentStatus, string> = {
  draft: "Черновик",
  published: "Опубликован",
};

// ─── Бейдж типа контента ──────────────────────────────────────────────────────

const TYPE_STYLES: Record<ContentType, string> = {
  article: "bg-blue-100 text-blue-800",
  faq: "bg-purple-100 text-purple-800",
  description: "bg-amber-100 text-amber-800",
};

const TYPE_LABELS: Record<ContentType, string> = {
  article: "Статья",
  faq: "FAQ",
  description: "Описание",
};

function TypeBadge({ type }: { type: ContentType }) {
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded font-medium", TYPE_STYLES[type])}>
      {TYPE_LABELS[type]}
    </span>
  );
}

// ─── Карточка контента ────────────────────────────────────────────────────────

function ContentCard({
  item,
  onStatusChange,
}: {
  item: GeneratedContent;
  onStatusChange: (id: string, status: ContentStatus) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [updating, setUpdating] = useState(false);

  async function handleCopy() {
    const text = `# ${item.title}\n\n${item.body}`;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleToggleStatus() {
    setUpdating(true);
    try {
      const next: ContentStatus = item.status === "draft" ? "published" : "draft";
      await onStatusChange(item.id, next);
    } finally {
      setUpdating(false);
    }
  }

  // Примерное количество слов
  const wordCount = item.body.split(/\s+/).length;

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Шапка карточки */}
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <TypeBadge type={item.type} />
              <span
                className={clsx(
                  "text-xs px-2 py-0.5 rounded-full font-medium",
                  item.status === "published"
                    ? "bg-green-100 text-green-700"
                    : "bg-gray-100 text-gray-500"
                )}
              >
                {STATUS_LABELS[item.status]}
              </span>
              <span className="text-xs text-gray-400 ml-auto">
                {wordCount} слов ·{" "}
                {new Date(item.created_at).toLocaleDateString("ru-RU", {
                  day: "numeric",
                  month: "short",
                })}
              </span>
            </div>
            <h3
              className="font-semibold text-gray-900 cursor-pointer hover:text-indigo-700"
              onClick={() => setExpanded((v) => !v)}
            >
              {item.title}
            </h3>
          </div>
        </div>

        {/* Превью первых двух строк */}
        {!expanded && (
          <p className="text-sm text-gray-500 mt-2 line-clamp-2 leading-relaxed">
            {item.body.replace(/[#*_]/g, "").slice(0, 200)}…
          </p>
        )}

        {/* Кнопки */}
        <div className="flex items-center gap-2 mt-3">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-indigo-600 hover:underline"
          >
            {expanded ? "Свернуть ▲" : "Читать полностью ▼"}
          </button>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-indigo-600 transition-colors px-2 py-1 rounded border border-gray-200 hover:border-indigo-300"
            >
              {copied ? "✓ Скопировано" : "📋 Копировать"}
            </button>
            <button
              onClick={handleToggleStatus}
              disabled={updating}
              className={clsx(
                "text-xs px-2.5 py-1 rounded border font-medium transition-colors disabled:opacity-60",
                item.status === "draft"
                  ? "border-green-300 text-green-700 hover:bg-green-50"
                  : "border-gray-300 text-gray-500 hover:bg-gray-50"
              )}
            >
              {updating
                ? "..."
                : item.status === "draft"
                ? "Опубликовать"
                : "Снять с публикации"}
            </button>
          </div>
        </div>
      </div>

      {/* Развёрнутый текст */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-4 bg-gray-50">
          <div className="prose prose-sm max-w-none">
            <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800 leading-relaxed">
              {item.body}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Форма генерации ──────────────────────────────────────────────────────────

function GenerateForm({
  projectId,
  token,
  onGenerated,
}: {
  projectId: string;
  token: string;
  onGenerated: () => void;
}) {
  const [selectedType, setSelectedType] = useState<ContentType>("article");
  const [topic, setTopic] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!topic.trim()) {
      setError("Введите тему для генерации");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      await contentApi.generate(token, {
        project_id: projectId,
        type: selectedType,
        topic: topic.trim(),
      });
      setTopic("");
      onGenerated();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка генерации";
      setError(msg);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
      <h2 className="font-semibold text-gray-900">Сгенерировать контент</h2>

      {/* Выбор типа */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {CONTENT_TYPES.map((ct) => (
          <button
            key={ct.key}
            onClick={() => setSelectedType(ct.key)}
            className={clsx(
              "text-left p-3 rounded-lg border-2 transition-all",
              selectedType === ct.key
                ? "border-indigo-500 bg-indigo-50"
                : "border-gray-200 hover:border-indigo-200"
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xl">{ct.icon}</span>
              <span className="font-medium text-sm text-gray-900">{ct.label}</span>
            </div>
            <p className="text-xs text-gray-500 leading-relaxed">{ct.description}</p>
          </button>
        ))}
      </div>

      {/* Поле темы */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Тема
          <span className="font-normal text-gray-400 ml-1">
            {selectedType === "article" && "— заголовок или вопрос для статьи"}
            {selectedType === "faq" && "— тема, по которой нужны вопросы и ответы"}
            {selectedType === "description" && "— название товара или услуги"}
          </span>
        </label>
        <div className="flex gap-2">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !generating && handleGenerate()}
            placeholder={
              selectedType === "article"
                ? "Например: Как выбрать пластиковые окна для квартиры"
                : selectedType === "faq"
                ? "Например: установка пластиковых окон"
                : "Например: Двухкамерный стеклопакет 70мм"
            }
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          <button
            onClick={handleGenerate}
            disabled={generating || !topic.trim()}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {generating ? (
              <>
                <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                Генерируем...
              </>
            ) : (
              "✨ Создать"
            )}
          </button>
        </div>
      </div>

      {/* Ошибка */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg px-3 py-2 text-sm">
          {error}
        </div>
      )}

      {/* Подсказка */}
      {generating && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2 text-sm text-indigo-700 flex items-center gap-2">
          <span className="w-4 h-4 border-2 border-indigo-300 border-t-indigo-600 rounded-full animate-spin flex-shrink-0" />
          Claude генерирует контент... обычно 10–20 секунд
        </div>
      )}
    </div>
  );
}

// ─── Основной компонент ───────────────────────────────────────────────────────

export default function ContentPage() {
  const token = useToken();
  const { mutate } = useSWRConfig();
  const [typeFilter, setTypeFilter] = useState<ContentType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<ContentStatus | "all">("all");

  // Первый проект
  const { data: projects } = useSWR(
    token ? ["projects", token] : null,
    ([, t]) => projectsApi.list(t)
  );

  const project = projects?.[0];
  const projectId = project?.id;

  const contentKey = token && projectId ? ["content", token, projectId, typeFilter, statusFilter] : null;

  // Список контента
  const { data: contentList, isLoading } = useSWR<GeneratedContent[]>(
    contentKey,
    ([, t, pid, tf, sf]) =>
      contentApi.list(t, pid, {
        type: tf === "all" ? undefined : (tf as ContentType),
        status: sf === "all" ? undefined : (sf as ContentStatus),
      })
  );

  // Счётчики по типам для фильтра
  const { data: allContent } = useSWR<GeneratedContent[]>(
    token && projectId ? ["content-all", token, projectId] : null,
    ([, t, pid]) => contentApi.list(t, pid)
  );

  const countByType = allContent?.reduce(
    (acc, item) => ({ ...acc, [item.type]: (acc[item.type] ?? 0) + 1 }),
    {} as Record<string, number>
  );

  async function handleStatusChange(contentId: string, status: ContentStatus) {
    if (!token) return;
    await contentApi.updateStatus(token, contentId, status);
    await mutate(contentKey);
    await mutate(["content-all", token, projectId]);
  }

  function handleGenerated() {
    mutate(contentKey);
    mutate(["content-all", token, projectId]);
  }

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Автоконтент</h1>
        <p className="text-sm text-gray-500 mt-1">
          Claude генерирует GEO-оптимизированный контент — статьи, FAQ и описания,
          которые Алиса и ГигаЧат охотно цитируют
        </p>
      </div>

      {/* Форма генерации */}
      {token && projectId ? (
        <GenerateForm
          projectId={projectId}
          token={token}
          onGenerated={handleGenerated}
        />
      ) : (
        <div className="bg-gray-50 border border-dashed border-gray-300 rounded-xl p-6 text-center text-gray-400 text-sm">
          Загрузка проекта...
        </div>
      )}

      {/* Статистика */}
      {allContent && allContent.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {CONTENT_TYPES.map((ct) => (
            <div key={ct.key} className="bg-white rounded-lg border border-gray-200 p-3 text-center">
              <span className="text-2xl">{ct.icon}</span>
              <p className="text-xl font-bold text-gray-900 mt-1">
                {countByType?.[ct.key] ?? 0}
              </p>
              <p className="text-xs text-gray-500">{ct.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Фильтры */}
      {allContent && allContent.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-500">Тип:</span>
          {(["all", "article", "faq", "description"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                typeFilter === t
                  ? "bg-indigo-600 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:border-indigo-300"
              )}
            >
              {t === "all" ? "Все" : TYPE_LABELS[t]}
              {t !== "all" && countByType?.[t] ? (
                <span className="ml-1 opacity-60">({countByType[t]})</span>
              ) : null}
            </button>
          ))}

          <div className="ml-4 flex items-center gap-2">
            <span className="text-sm text-gray-500">Статус:</span>
            {(["all", "draft", "published"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={clsx(
                  "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                  statusFilter === s
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-600 border border-gray-200 hover:border-indigo-300"
                )}
              >
                {s === "all" ? "Все" : STATUS_LABELS[s]}
              </button>
            ))}
          </div>

          {contentList && (
            <span className="ml-auto text-xs text-gray-400">
              {contentList.length} материалов
            </span>
          )}
        </div>
      )}

      {/* Список контента */}
      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-gray-400">
          Загрузка...
        </div>
      ) : !contentList || contentList.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
          <p className="text-4xl mb-4">✍️</p>
          <h3 className="font-medium text-gray-900 mb-2">Контент ещё не создан</h3>
          <p className="text-sm text-gray-500 max-w-sm mx-auto">
            Выберите тип контента, введите тему и нажмите «Создать».
            Claude напишет текст оптимизированный под Алису и ГигаЧат.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {contentList.map((item) => (
            <ContentCard
              key={item.id}
              item={item}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}

      {/* Советы */}
      {contentList && contentList.length > 0 && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4">
          <p className="text-xs font-semibold text-indigo-700 mb-2 uppercase tracking-wide">
            Как использовать контент
          </p>
          <ul className="text-xs text-indigo-800 space-y-1">
            <li>• <strong>Статьи</strong>: опубликуйте в блоге сайта и добавьте schema.org Article разметку</li>
            <li>• <strong>FAQ</strong>: разместите на отдельной странице с schema.org FAQPage разметкой — Алиса цитирует FAQ лучше всего</li>
            <li>• <strong>Описания</strong>: используйте в карточках товаров/услуг, Алиса берёт первое предложение</li>
          </ul>
        </div>
      )}
    </div>
  );
}
