"use client";

/**
 * Страница регистрации.
 * Вызывает наш бэкенд напрямую через authApi.register(),
 * затем входит через NextAuth signIn().
 */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi, ApiError } from "@/lib/api";

interface FormState {
  name: string;
  email: string;
  password: string;
  passwordConfirm: string;
}

interface FormErrors {
  name?: string;
  email?: string;
  password?: string;
  passwordConfirm?: string;
  general?: string;
}

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>({
    name: "",
    email: "",
    password: "",
    passwordConfirm: "",
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [isLoading, setIsLoading] = useState(false);

  function validate(): boolean {
    const e: FormErrors = {};
    if (!form.name.trim()) e.name = "Введите ваше имя";
    if (!form.email) e.email = "Введите email";
    else if (!/\S+@\S+\.\S+/.test(form.email)) e.email = "Некорректный email";
    if (!form.password) e.password = "Введите пароль";
    else if (form.password.length < 8) e.password = "Минимум 8 символов";
    else if (!/\d/.test(form.password)) e.password = "Пароль должен содержать цифру";
    if (form.password !== form.passwordConfirm)
      e.passwordConfirm = "Пароли не совпадают";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setIsLoading(true);
    setErrors({});

    try {
      // 1. Регистрация на бэкенде
      await authApi.register({
        name: form.name.trim(),
        email: form.email,
        password: form.password,
      });

      // 2. Автовход через NextAuth после успешной регистрации
      const result = await signIn("credentials", {
        email: form.email,
        password: form.password,
        redirect: false,
      });

      if (result?.error) {
        // Аккаунт создан, но вход не прошёл — шлём на логин
        router.push("/login");
        return;
      }

      // 3. Редирект в дашборд
      router.push("/dashboard");
      router.refresh();

    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrors({ email: "Пользователь с таким email уже существует" });
      } else {
        setErrors({ general: "Произошла ошибка. Попробуйте позже." });
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-sm">

        {/* Лого и заголовок */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600">
            <span className="text-xl font-bold text-white">G</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Создать аккаунт</h1>
          <p className="mt-1 text-sm text-gray-500">
            Уже есть аккаунт?{" "}
            <Link href="/login" className="font-medium text-brand-600 hover:text-brand-700">
              Войти
            </Link>
          </p>
        </div>

        {/* Форма */}
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>

          {errors.general && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
              {errors.general}
            </div>
          )}

          <Input
            id="name"
            type="text"
            label="Имя"
            placeholder="Иван Иванов"
            autoComplete="name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            error={errors.name}
            disabled={isLoading}
          />

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

          <Input
            id="password"
            type="password"
            label="Пароль"
            placeholder="Минимум 8 символов с цифрой"
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            error={errors.password}
            disabled={isLoading}
          />

          <Input
            id="passwordConfirm"
            type="password"
            label="Повторите пароль"
            placeholder="••••••••"
            autoComplete="new-password"
            value={form.passwordConfirm}
            onChange={(e) => setForm((f) => ({ ...f, passwordConfirm: e.target.value }))}
            error={errors.passwordConfirm}
            disabled={isLoading}
          />

          <Button type="submit" isLoading={isLoading} className="w-full">
            {isLoading ? "Создаём аккаунт..." : "Зарегистрироваться"}
          </Button>

          <p className="text-center text-xs text-gray-400">
            Регистрируясь, вы соглашаетесь с условиями использования сервиса
          </p>
        </form>

      </div>
    </main>
  );
}
