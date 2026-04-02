"use client";

/**
 * Страница входа.
 * Client Component — нужен signIn() от NextAuth и управление состоянием формы.
 */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface FormState {
  email: string;
  password: string;
}

interface FormErrors {
  email?: string;
  password?: string;
  general?: string;
}

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>({ email: "", password: "" });
  const [errors, setErrors] = useState<FormErrors>({});
  const [isLoading, setIsLoading] = useState(false);

  // Простая клиентская валидация
  function validate(): boolean {
    const newErrors: FormErrors = {};
    if (!form.email) newErrors.email = "Введите email";
    else if (!/\S+@\S+\.\S+/.test(form.email)) newErrors.email = "Некорректный email";
    if (!form.password) newErrors.password = "Введите пароль";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setIsLoading(true);
    setErrors({});

    const result = await signIn("credentials", {
      email: form.email,
      password: form.password,
      redirect: false,
    });

    setIsLoading(false);

    if (result?.error) {
      setErrors({ general: "Неверный email или пароль" });
      return;
    }

    // Успешный вход — редирект в дашборд
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">

        {/* Лого и заголовок */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600">
            <span className="text-xl font-bold text-white">G</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Войти в аккаунт</h1>
          <p className="mt-1 text-sm text-gray-500">
            Нет аккаунта?{" "}
            <Link href="/register" className="font-medium text-brand-600 hover:text-brand-700">
              Зарегистрироваться
            </Link>
          </p>
        </div>

        {/* Форма */}
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>

          {/* Глобальная ошибка */}
          {errors.general && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
              {errors.general}
            </div>
          )}

          <Input
            id="email"
            type="email"
            label="Email"
            placeholder="you@example.com"
            autoComplete="email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            error={errors.email}
            disabled={isLoading}
          />

          <div>
            <Input
              id="password"
              type="password"
              label="Пароль"
              placeholder="••••••••"
              autoComplete="current-password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              error={errors.password}
              disabled={isLoading}
            />
            <div className="mt-1.5 text-right">
              <span className="text-xs text-gray-400">
                {/* TODO: forgot password */}
                Забыли пароль? Напишите в поддержку
              </span>
            </div>
          </div>

          <Button type="submit" isLoading={isLoading} className="w-full">
            {isLoading ? "Входим..." : "Войти"}
          </Button>
        </form>

      </div>
    </main>
  );
}
