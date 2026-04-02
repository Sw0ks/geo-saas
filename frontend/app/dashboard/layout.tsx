"use client";

/**
 * Лэйаут дашборда: боковая навигация + переключатель проекта + шапка.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import useSWR from "swr";
import clsx from "clsx";
import { projectsApi, type Project } from "@/lib/api";

const LS_KEY = "geo_active_project_id";

const NAV_LINKS = [
  { href: "/dashboard", label: "Обзор", icon: "📊" },
  { href: "/dashboard/monitoring", label: "Мониторинг", icon: "🔍" },
  { href: "/dashboard/crawler", label: "AI Краулер", icon: "🤖" },
  { href: "/dashboard/plan", label: "План действий", icon: "📋" },
  { href: "/dashboard/content", label: "Автоконтент", icon: "✍️" },
];

const BOTTOM_LINKS = [
  { href: "/dashboard/projects", label: "Проекты", icon: "🗂" },
  { href: "/dashboard/settings", label: "Настройки", icon: "⚙️" },
];

// ─── Переключатель активного проекта ──────────────────────────────────────────

function ProjectSwitcher({ token }: { token: string }) {
  const router = useRouter();
  const [activeId, setActiveId] = useState<string>("");
  const [open, setOpen] = useState(false);

  const { data: projects } = useSWR(
    token ? ["projects-switcher", token] : null,
    ([, t]) => projectsApi.list(t),
  );

  useEffect(() => {
    const stored = localStorage.getItem(LS_KEY) ?? "";
    setActiveId(stored);
  }, []);

  // Если в LS нет проекта — ставим первый
  useEffect(() => {
    if (!activeId && projects && projects.length > 0) {
      const first = projects[0].id;
      localStorage.setItem(LS_KEY, first);
      setActiveId(first);
    }
  }, [activeId, projects]);

  const active = projects?.find((p: Project) => p.id === activeId);

  function select(id: string) {
    localStorage.setItem(LS_KEY, id);
    setActiveId(id);
    setOpen(false);
    // Перезагружаем текущую страницу чтобы SWR подхватил новый проект
    router.refresh();
  }

  if (!projects || projects.length === 0) return null;

  return (
    <div className="relative mx-3 mb-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-gray-50 border border-gray-200 hover:bg-gray-100 transition-colors text-left"
      >
        <div className="w-6 h-6 rounded-md bg-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-600 flex-shrink-0">
          {active?.name?.[0]?.toUpperCase() ?? "?"}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-gray-900 truncate">
            {active?.name ?? "Выберите проект"}
          </p>
          <p className="text-xs text-gray-400 truncate">{active?.domain ?? ""}</p>
        </div>
        <span className="text-gray-400 text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg z-50 overflow-hidden">
          {projects.map((p: Project) => (
            <button
              key={p.id}
              onClick={() => select(p.id)}
              className={clsx(
                "w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 transition-colors",
                p.id === activeId && "bg-indigo-50",
              )}
            >
              <div className="w-5 h-5 rounded bg-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-600 flex-shrink-0">
                {p.name[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-gray-900 truncate">{p.name}</p>
                <p className="text-xs text-gray-400 truncate">{p.domain}</p>
              </div>
              {p.id === activeId && <span className="text-indigo-500 text-xs">✓</span>}
            </button>
          ))}
          <div className="border-t border-gray-100">
            <Link
              href="/dashboard/onboarding"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2.5 text-xs text-indigo-600 hover:bg-indigo-50 transition-colors"
            >
              <span>+</span> Добавить проект
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Лэйаут ───────────────────────────────────────────────────────────────────

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const token = (session as { accessToken?: string })?.accessToken ?? "";

  // Онбординг — полноэкранная страница без боковой панели
  if (pathname === "/dashboard/onboarding") {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Боковая панель */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        {/* Логотип */}
        <div className="h-16 flex items-center px-6 border-b border-gray-200 flex-shrink-0">
          <span className="text-xl font-bold text-indigo-600">GEO Analytics</span>
        </div>

        {/* Переключатель проекта */}
        <div className="pt-3">
          <p className="px-6 text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5">
            Проект
          </p>
          {token && <ProjectSwitcher token={token} />}
        </div>

        {/* Основная навигация */}
        <nav className="flex-1 px-3 py-2 space-y-0.5 overflow-y-auto">
          <p className="px-3 text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5 mt-2">
            Разделы
          </p>
          {NAV_LINKS.map((link) => {
            const isActive =
              link.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(link.href);

            return (
              <Link
                key={link.href}
                href={link.href}
                className={clsx(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
                )}
              >
                <span>{link.icon}</span>
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Нижняя часть: Проекты, Настройки, пользователь */}
        <div className="border-t border-gray-100">
          <nav className="px-3 py-2 space-y-0.5">
            {BOTTOM_LINKS.map((link) => {
              const isActive = pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={clsx(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                    isActive
                      ? "bg-indigo-50 text-indigo-700"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
                  )}
                >
                  <span>{link.icon}</span>
                  {link.label}
                </Link>
              );
            })}
          </nav>

          {/* Пользователь */}
          <div className="p-4 border-t border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-semibold text-sm flex-shrink-0">
                {session?.user?.name?.[0]?.toUpperCase() ?? "?"}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {session?.user?.name ?? "Пользователь"}
                </p>
                <p className="text-xs text-gray-500 capitalize">
                  {(session?.user as { subscriptionPlan?: string })?.subscriptionPlan ?? "start"}
                </p>
              </div>
              <button
                onClick={() => signOut({ callbackUrl: "/login" })}
                title="Выйти"
                className="text-gray-400 hover:text-red-500 transition-colors text-sm"
              >
                ↩
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Основной контент */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-6xl mx-auto px-6 py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
