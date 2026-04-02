"use client";

/**
 * Онбординг-визард для новых пользователей.
 * Показывается автоматически если у пользователя нет проектов.
 *
 * Шаг 1 — Проект:    название, домен, описание бизнеса
 * Шаг 2 — Конкуренты: до 3 доменов (можно пропустить)
 * Шаг 3 — Промпты:   5 предложений от Claude + редактирование
 *
 * По завершении: создаётся проект, запускается мониторинг, редирект на /dashboard
 */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import clsx from "clsx";
import { agentApi, monitoringApi, projectsApi } from "@/lib/api";

function useToken(): string | null {
  const { data: session } = useSession();
  return (session as { accessToken?: string })?.accessToken ?? null;
}

// ─── Индикатор шагов ─────────────────────────────────────────────────────────

function StepIndicator({ current, total }: { current: number; total: number }) {
  const labels = ["Проект", "Конкуренты", "Промпты"];
  return (
    <div className="flex items-center gap-0 mb-10">
      {Array.from({ length: total }).map((_, i) => {
        const step = i + 1;
        const done = step < current;
        const active = step === current;
        return (
          <div key={step} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <div
                className={clsx(
                  "w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-all",
                  done
                    ? "bg-indigo-600 border-indigo-600 text-white"
                    : active
                    ? "bg-white border-indigo-600 text-indigo-600"
                    : "bg-white border-gray-200 text-gray-400"
                )}
              >
                {done ? "✓" : step}
              </div>
              <span
                className={clsx(
                  "text-xs mt-1.5 font-medium",
                  active ? "text-indigo-700" : done ? "text-indigo-500" : "text-gray-400"
                )}
              >
                {labels[i]}
              </span>
            </div>
            {step < total && (
              <div
                className={clsx(
                  "flex-1 h-0.5 mx-2 mb-5 transition-colors",
                  done ? "bg-indigo-400" : "bg-gray-200"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Шаг 1: Данные проекта ────────────────────────────────────────────────────

interface Step1Data {
  name: string;
  domain: string;
  description: string;
}

function Step1({
  data,
  onChange,
  onNext,
}: {
  data: Step1Data;
  onChange: (d: Step1Data) => void;
  onNext: () => void;
}) {
  const [errors, setErrors] = useState<Partial<Step1Data>>({});

  function validate(): boolean {
    const e: Partial<Step1Data> = {};
    if (!data.name.trim()) e.name = "Введите название бизнеса";
    if (!data.domain.trim()) e.domain = "Введите домен сайта";
    else if (!/^[\w.-]+\.[a-z]{2,}$/.test(data.domain.trim().replace(/^https?:\/\//, "")))
      e.domain = "Введите корректный домен (например pizza-mario.ru)";
    if (!data.description.trim()) e.description = "Опишите бизнес в 1-2 предложениях";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function handleNext() {
    if (validate()) onNext();
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-gray-900">Расскажите о своём бизнесе</h2>
        <p className="text-sm text-gray-500 mt-1">
          На основе этих данных Claude подберёт промпты для мониторинга
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Название бизнеса
        </label>
        <input
          value={data.name}
          onChange={(e) => onChange({ ...data, name: e.target.value })}
          placeholder="Например: Пицца Марио"
          className={clsx(
            "w-full px-3 py-2.5 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500",
            errors.name ? "border-red-400" : "border-gray-300"
          )}
        />
        {errors.name && <p className="text-red-500 text-xs mt-1">{errors.name}</p>}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Домен сайта
        </label>
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm select-none">
            https://
          </span>
          <input
            value={data.domain}
            onChange={(e) => onChange({ ...data, domain: e.target.value })}
            placeholder="pizza-mario.ru"
            className={clsx(
              "w-full pl-[72px] pr-3 py-2.5 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500",
              errors.domain ? "border-red-400" : "border-gray-300"
            )}
          />
        </div>
        {errors.domain && <p className="text-red-500 text-xs mt-1">{errors.domain}</p>}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Чем занимается ваш бизнес?
        </label>
        <textarea
          value={data.description}
          onChange={(e) => onChange({ ...data, description: e.target.value })}
          placeholder="Например: Доставка пиццы в Москве. Работаем с 2015 года, более 30 видов пиццы, доставка за 40 минут."
          rows={3}
          className={clsx(
            "w-full px-3 py-2.5 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none",
            errors.description ? "border-red-400" : "border-gray-300"
          )}
        />
        {errors.description && (
          <p className="text-red-500 text-xs mt-1">{errors.description}</p>
        )}
        <p className="text-xs text-gray-400 mt-1">1-2 предложения — используется для генерации промптов</p>
      </div>

      <button
        onClick={handleNext}
        className="w-full py-2.5 bg-indigo-600 text-white rounded-lg font-medium text-sm hover:bg-indigo-700 transition-colors"
      >
        Далее →
      </button>
    </div>
  );
}

// ─── Шаг 2: Конкуренты ───────────────────────────────────────────────────────

function Step2({
  competitors,
  onChange,
  onNext,
  onSkip,
  onBack,
}: {
  competitors: string[];
  onChange: (c: string[]) => void;
  onNext: () => void;
  onSkip: () => void;
  onBack: () => void;
}) {
  function updateAt(index: number, value: string) {
    const next = [...competitors];
    next[index] = value.trim().replace(/^https?:\/\//, "").replace(/\/$/, "");
    onChange(next);
  }

  function addSlot() {
    if (competitors.length < 3) onChange([...competitors, ""]);
  }

  function removeAt(index: number) {
    onChange(competitors.filter((_, i) => i !== index));
  }

  const filledCompetitors = competitors.filter((c) => c.trim());

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-gray-900">Кто ваши конкуренты?</h2>
        <p className="text-sm text-gray-500 mt-1">
          Мы будем сравнивать вашу видимость в AI с конкурентами.
          Можно добавить до 3 доменов.
        </p>
      </div>

      <div className="space-y-3">
        {competitors.map((c, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm select-none">
                https://
              </span>
              <input
                value={c}
                onChange={(e) => updateAt(i, e.target.value)}
                placeholder={`competitor${i + 1}.ru`}
                className="w-full pl-[72px] pr-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <button
              onClick={() => removeAt(i)}
              className="w-9 h-9 flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
            >
              ✕
            </button>
          </div>
        ))}

        {competitors.length < 3 && (
          <button
            onClick={addSlot}
            className="w-full py-2 border-2 border-dashed border-gray-300 rounded-lg text-sm text-gray-500 hover:border-indigo-300 hover:text-indigo-600 transition-colors"
          >
            + Добавить конкурента
          </button>
        )}
      </div>

      <div className="flex gap-3 pt-2">
        <button
          onClick={onBack}
          className="px-4 py-2.5 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50 transition-colors"
        >
          ← Назад
        </button>
        <button
          onClick={onSkip}
          className="px-4 py-2.5 text-gray-500 rounded-lg text-sm hover:bg-gray-50 transition-colors"
        >
          Пропустить
        </button>
        <button
          onClick={onNext}
          className="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg font-medium text-sm hover:bg-indigo-700 transition-colors"
        >
          {filledCompetitors.length > 0
            ? `Далее (${filledCompetitors.length} конкурента) →`
            : "Далее →"}
        </button>
      </div>
    </div>
  );
}

// ─── Шаг 3: Промпты ──────────────────────────────────────────────────────────

function Step3({
  prompts,
  onChange,
  onBack,
  onFinish,
  creating,
}: {
  prompts: string[];
  onChange: (p: string[]) => void;
  onBack: () => void;
  onFinish: () => void;
  creating: boolean;
}) {
  function updateAt(index: number, value: string) {
    const next = [...prompts];
    next[index] = value;
    onChange(next);
  }

  function removeAt(index: number) {
    onChange(prompts.filter((_, i) => i !== index));
  }

  function addEmpty() {
    onChange([...prompts, ""]);
  }

  const validPrompts = prompts.filter((p) => p.trim());

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-gray-900">Промпты для мониторинга</h2>
        <p className="text-sm text-gray-500 mt-1">
          Это запросы которые мы будем проверять в Алисе и ГигаЧате — упоминает ли AI ваш бизнес.
          Отредактируйте если нужно.
        </p>
      </div>

      <div className="space-y-2">
        {prompts.map((prompt, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="flex-shrink-0 w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 text-xs flex items-center justify-center font-semibold">
              {i + 1}
            </div>
            <input
              value={prompt}
              onChange={(e) => updateAt(i, e.target.value)}
              placeholder="Введите запрос..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={() => removeAt(i)}
              className="w-7 h-7 flex items-center justify-center text-gray-300 hover:text-red-400 transition-colors"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {prompts.length < 10 && (
        <button
          onClick={addEmpty}
          className="w-full py-2 border-2 border-dashed border-gray-300 rounded-lg text-xs text-gray-500 hover:border-indigo-300 hover:text-indigo-600 transition-colors"
        >
          + Добавить промпт вручную
        </button>
      )}

      {validPrompts.length === 0 && (
        <p className="text-xs text-red-500">Добавьте хотя бы один промпт для мониторинга</p>
      )}

      <div className="flex gap-3 pt-2">
        <button
          onClick={onBack}
          disabled={creating}
          className="px-4 py-2.5 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          ← Назад
        </button>
        <button
          onClick={onFinish}
          disabled={creating || validPrompts.length === 0}
          className="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg font-semibold text-sm hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors inline-flex items-center justify-center gap-2"
        >
          {creating ? (
            <>
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Создаём проект...
            </>
          ) : (
            "🚀 Запустить мониторинг"
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Основной компонент ───────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();
  const token = useToken();
  const { status: sessionStatus } = useSession();

  const [step, setStep] = useState(1);

  // Данные по шагам
  const [step1, setStep1] = useState({ name: "", domain: "", description: "" });
  const [competitors, setCompetitors] = useState<string[]>([""]);
  const [prompts, setPrompts] = useState<string[]>([]);

  // Состояния загрузки
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [promptsError, setPromptsError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Автоматически подгружаем промпты при переходе на шаг 3
  const promptsLoadedRef = useRef(false);
  useEffect(() => {
    if (step !== 3 || promptsLoadedRef.current || !token) return;
    if (!step1.name || !step1.description) return;

    promptsLoadedRef.current = true;
    setLoadingPrompts(true);
    setPromptsError(null);

    agentApi
      .suggestPrompts(token, { name: step1.name, description: step1.description })
      .then((res) => setPrompts(res.prompts))
      .catch(() => {
        setPromptsError("Не удалось загрузить промпты. Можно ввести вручную.");
        setPrompts([]);
      })
      .finally(() => setLoadingPrompts(false));
  }, [step, token, step1.name, step1.description]);

  async function handleRegeneratePrompts() {
    if (!token) return;
    promptsLoadedRef.current = true;
    setLoadingPrompts(true);
    setPromptsError(null);
    try {
      const res = await agentApi.suggestPrompts(token, {
        name: step1.name,
        description: step1.description,
      });
      setPrompts(res.prompts);
    } catch {
      setPromptsError("Ошибка генерации промптов. Введите вручную.");
    } finally {
      setLoadingPrompts(false);
    }
  }

  async function handleFinish() {
    if (!token) return;
    setCreating(true);
    setCreateError(null);

    const cleanCompetitors = competitors.filter((c) => c.trim());
    const cleanPrompts = prompts.filter((p) => p.trim());

    try {
      // 1. Создаём проект
      const project = await projectsApi.create(token, {
        name: step1.name,
        domain: step1.domain,
        competitors: cleanCompetitors,
        prompts: cleanPrompts,
      });

      // 2. Запускаем первый мониторинг в фоне (не ждём результата)
      monitoringApi.run(token, project.id).catch(() => {
        // Игнорируем ошибку запуска мониторинга — он мог уже запуститься
      });

      // 3. Редиректим на дашборд с сообщением
      router.push("/dashboard?onboarding=1");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка создания проекта";
      setCreateError(msg);
      setCreating(false);
    }
  }

  // Пока сессия грузится — пустой экран
  if (sessionStatus === "loading") {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Логотип */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-indigo-600">GEO Analytics</h1>
          <p className="text-sm text-gray-500 mt-1">Настройка займёт 2 минуты</p>
        </div>

        {/* Карточка визарда */}
        <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-8">
          <StepIndicator current={step} total={3} />

          {/* Шаг 1 */}
          {step === 1 && (
            <Step1
              data={step1}
              onChange={setStep1}
              onNext={() => setStep(2)}
            />
          )}

          {/* Шаг 2 */}
          {step === 2 && (
            <Step2
              competitors={competitors}
              onChange={setCompetitors}
              onNext={() => setStep(3)}
              onSkip={() => { setCompetitors([]); setStep(3); }}
              onBack={() => setStep(1)}
            />
          )}

          {/* Шаг 3 */}
          {step === 3 && (
            <div className="space-y-5">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Промпты для мониторинга</h2>
                <p className="text-sm text-gray-500 mt-1">
                  Запросы которые мы проверяем в Алисе и ГигаЧате каждый день.
                </p>
              </div>

              {/* Состояние загрузки промптов */}
              {loadingPrompts ? (
                <div className="flex flex-col items-center justify-center py-10 gap-3">
                  <div className="w-8 h-8 border-3 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
                  <p className="text-sm text-gray-500">
                    Claude подбирает промпты для «{step1.name}»...
                  </p>
                </div>
              ) : (
                <>
                  {promptsError && (
                    <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm text-amber-800">
                      {promptsError}
                    </div>
                  )}

                  <Step3
                    prompts={prompts}
                    onChange={setPrompts}
                    onBack={() => { promptsLoadedRef.current = false; setStep(2); }}
                    onFinish={handleFinish}
                    creating={creating}
                  />

                  {/* Кнопка регенерации */}
                  {!creating && (
                    <button
                      onClick={handleRegeneratePrompts}
                      className="w-full text-xs text-indigo-500 hover:text-indigo-700 py-1 transition-colors"
                    >
                      ✨ Сгенерировать другие промпты
                    </button>
                  )}

                  {createError && (
                    <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg px-3 py-2 text-sm">
                      {createError}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Подпись снизу */}
        <p className="text-center text-xs text-gray-400 mt-6">
          Настройки можно изменить в любое время в разделе «Проекты»
        </p>
      </div>
    </div>
  );
}
