"use client";

/**
 * Страница списка проектов пользователя.
 * Активный проект сохраняется в localStorage под ключом geo_active_project_id.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import useSWR from "swr";
import { projectsApi, type Project } from "@/lib/api";

const LS_KEY = "geo_active_project_id";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default function ProjectsPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const token = (session as { accessToken?: string })?.accessToken ?? "";

  const { data: projects, isLoading, error } = useSWR(
    token ? ["projects", token] : null,
    ([, t]) => projectsApi.list(t),
  );

  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    setActiveId(localStorage.getItem(LS_KEY));
  }, []);

  function activate(id: string) {
    localStorage.setItem(LS_KEY, id);
    setActiveId(id);
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-gray-400 text-sm">Загрузка проектов…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-sm text-red-700">
        Не удалось загрузить проекты: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Проекты</h1>
          <p className="text-sm text-gray-500 mt-1">
            {projects?.length ?? 0} {projects?.length === 1 ? "проект" : "проектов"}
          </p>
        </div>
        <Link
          href="/dashboard/onboarding"
          className="bg-indigo-600 text-white text-sm font-semibold px-4 py-2.5 rounded-xl hover:bg-indigo-700 transition-colors"
        >
          + Добавить проект
        </Link>
      </div>

      {/* Пустое состояние */}
      {(!projects || projects.length === 0) && (
        <div className="bg-white border border-gray-200 rounded-2xl p-12 text-center">
          <p className="text-5xl mb-4">🗂</p>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Проектов пока нет</h2>
          <p className="text-sm text-gray-500 mb-6">
            Создайте первый проект чтобы начать мониторинг в Алисе и ГигаЧате
          </p>
          <Link
            href="/dashboard/onboarding"
            className="inline-block bg-indigo-600 text-white text-sm font-semibold px-6 py-2.5 rounded-xl hover:bg-indigo-700 transition-colors"
          >
            Создать первый проект
          </Link>
        </div>
      )}

      {/* Сетка карточек */}
      {projects && projects.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project: Project) => {
            const isActive = activeId === project.id;
            return (
              <div
                key={project.id}
                className={`bg-white rounded-2xl border p-5 flex flex-col gap-4 transition-shadow hover:shadow-md ${
                  isActive ? "border-indigo-400 ring-1 ring-indigo-400" : "border-gray-200"
                }`}
              >
                {/* Шапка карточки */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 truncate">{project.name}</h3>
                      {isActive && (
                        <span className="flex-shrink-0 text-xs font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                          активный
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5 truncate">{project.domain}</p>
                  </div>
                </div>

                {/* Метаданные */}
                <div className="space-y-1.5 text-xs text-gray-500">
                  <div className="flex items-center gap-1.5">
                    <span>📅</span>
                    <span>Создан {formatDate(project.created_at)}</span>
                  </div>
                  {project.competitors.length > 0 && (
                    <div className="flex items-center gap-1.5">
                      <span>⚔️</span>
                      <span>{project.competitors.length} конкурент{project.competitors.length > 1 ? "а" : ""}</span>
                    </div>
                  )}
                  {project.prompts.length > 0 && (
                    <div className="flex items-center gap-1.5">
                      <span>💬</span>
                      <span>{project.prompts.length} промпт{project.prompts.length > 1 ? "а" : ""}</span>
                    </div>
                  )}
                </div>

                {/* Кнопки */}
                <div className="flex gap-2 mt-auto">
                  <button
                    onClick={() => activate(project.id)}
                    className={`flex-1 text-xs font-medium py-2 rounded-lg border transition-colors ${
                      isActive
                        ? "border-indigo-200 text-indigo-600 bg-indigo-50"
                        : "border-gray-200 text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    {isActive ? "✓ Активный" : "Выбрать"}
                  </button>
                  <button
                    onClick={() => {
                      activate(project.id);
                      router.push("/dashboard");
                    }}
                    className="flex-1 text-xs font-semibold py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
                  >
                    Открыть →
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
