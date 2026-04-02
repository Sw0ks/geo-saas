"use client";

/**
 * Страница настроек пользователя:
 *  — редактирование имени
 *  — просмотр email
 *  — информация о тарифе
 *  — выход из аккаунта
 */
import { useState } from "react";
import Link from "next/link";
import { signOut, useSession } from "next-auth/react";
import useSWR from "swr";
import { authApi, type AuthUser } from "@/lib/api";

const PLAN_LABELS: Record<string, string> = {
  start: "Старт",
  business: "Бизнес",
  agency: "Агентство",
};

const PLAN_PRICES: Record<string, string> = {
  start: "990 ₽/мес",
  business: "2 990 ₽/мес",
  agency: "7 990 ₽/мес",
};

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function isExpired(iso: string | null | undefined): boolean {
  if (!iso) return false;
  return new Date(iso) < new Date();
}

export default function SettingsPage() {
  const { data: session, update: updateSession } = useSession();
  const token = (session as { accessToken?: string })?.accessToken ?? "";

  const { data: user, mutate } = useSWR<AuthUser>(
    token ? ["me", token] : null,
    ([, t]) => authApi.me(t as string),
  );

  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Инициализируем инпут именем из API (один раз)
  const displayName = name || user?.name || "";

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || name.trim() === user?.name) return;
    setSaving(true);
    setSaveError("");
    setSaveSuccess(false);
    try {
      const updated = await authApi.updateMe(token, { name: name.trim() });
      await mutate(updated, false);
      await updateSession({ name: updated.name });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  }

  const plan = user?.subscription_plan ?? "start";
  const expiresAt = user?.subscription_expires_at;
  const expired = isExpired(expiresAt);

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Настройки</h1>
        <p className="text-sm text-gray-500 mt-1">Управление аккаунтом и подпиской</p>
      </div>

      {/* ── Профиль ─────────────────────────────────────────────────── */}
      <section className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-5">Профиль</h2>

        <form onSubmit={handleSave} className="space-y-4">
          {/* Имя */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Имя
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setName(e.target.value)}
              placeholder={user?.name ?? "Ваше имя"}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Email — только отображение */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Email
            </label>
            <div className="w-full border border-gray-100 rounded-xl px-4 py-2.5 text-sm bg-gray-50 text-gray-500 select-all">
              {user?.email ?? "—"}
            </div>
            <p className="text-xs text-gray-400 mt-1">Email изменить нельзя</p>
          </div>

          {/* Сообщения */}
          {saveError && (
            <p className="text-sm text-red-600 bg-red-50 px-4 py-2 rounded-lg">{saveError}</p>
          )}
          {saveSuccess && (
            <p className="text-sm text-green-700 bg-green-50 px-4 py-2 rounded-lg">✓ Имя сохранено</p>
          )}

          <button
            type="submit"
            disabled={saving || !name.trim() || name.trim() === user?.name}
            className="bg-indigo-600 text-white text-sm font-semibold px-5 py-2.5 rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? "Сохраняю…" : "Сохранить"}
          </button>
        </form>
      </section>

      {/* ── Подписка ────────────────────────────────────────────────── */}
      <section className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-5">Подписка</h2>

        <div className="flex items-center justify-between py-3 border-b border-gray-100">
          <span className="text-sm text-gray-600">Текущий тариф</span>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-900">
              {PLAN_LABELS[plan] ?? plan}
            </span>
            <span className="text-xs text-gray-400">{PLAN_PRICES[plan]}</span>
          </div>
        </div>

        <div className="flex items-center justify-between py-3 border-b border-gray-100">
          <span className="text-sm text-gray-600">Действует до</span>
          <span className={`text-sm font-medium ${expired ? "text-red-600" : "text-gray-900"}`}>
            {expiresAt ? formatDate(expiresAt) : "Бессрочно"}
            {expired && " — истёк"}
          </span>
        </div>

        <div className="pt-4">
          <Link
            href="/#pricing"
            className="inline-block text-sm font-semibold text-indigo-600 border border-indigo-200 px-5 py-2.5 rounded-xl hover:bg-indigo-50 transition-colors"
          >
            Сменить тариф →
          </Link>
        </div>
      </section>

      {/* ── Аккаунт ─────────────────────────────────────────────────── */}
      <section className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-5">Аккаунт</h2>
        <p className="text-sm text-gray-500 mb-4">
          После выхода потребуется заново войти в систему.
        </p>
        <button
          onClick={() => signOut({ callbackUrl: "/login" })}
          className="text-sm font-semibold text-red-600 border border-red-200 px-5 py-2.5 rounded-xl hover:bg-red-50 transition-colors"
        >
          Выйти из аккаунта
        </button>
      </section>
    </div>
  );
}
