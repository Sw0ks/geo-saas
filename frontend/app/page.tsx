import Link from "next/link";

// ─── Данные ───────────────────────────────────────────────────────────────────

const STEPS = [
  {
    num: "01",
    title: "Вводишь сайт",
    desc: "Указываешь домен своего бизнеса и конкурентов, которых хочешь обогнать.",
  },
  {
    num: "02",
    title: "Мы проверяем Алису и ГигаЧат",
    desc: "Каждый день прогоняем промпты через Яндекс Алису и ГигаЧат. Смотрим: упоминается ли твой бренд, на какой позиции, с какой тональностью.",
  },
  {
    num: "03",
    title: "Получаешь план действий",
    desc: "AI-агент анализирует результаты и выдаёт список конкретных шагов: какие статьи написать, что исправить на сайте, какие FAQ добавить.",
  },
  {
    num: "04",
    title: "Контент генерируется автоматически",
    desc: "Сразу получаешь готовые черновики статей и FAQ — оптимизированные под формат, который Алиса цитирует чаще всего.",
  },
];

const PLANS = [
  {
    name: "Старт",
    price: "990",
    prompts: "10 промптов / мес",
    projects: "1 проект",
    features: ["GEO мониторинг", "AI Краулер трекер", "Email-отчёты"],
    cta: "Начать",
    highlighted: false,
  },
  {
    name: "Бизнес",
    price: "2 990",
    prompts: "50 промптов / мес",
    projects: "3 проекта",
    features: ["Всё из Старта", "Агент план действий", "Генерация контента", "Сравнение с конкурентами"],
    cta: "Попробовать",
    highlighted: true,
  },
  {
    name: "Агентство",
    price: "7 990",
    prompts: "200 промптов / мес",
    projects: "10 проектов",
    features: ["Всё из Бизнеса", "White label", "Приоритетная поддержка", "API доступ"],
    cta: "Связаться",
    highlighted: false,
  },
];

// ─── Компонент ────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white text-gray-900">

      {/* ── Навбар ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 bg-white/90 backdrop-blur border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-bold text-indigo-600">GEO Analytics</span>
          <nav className="hidden sm:flex items-center gap-6 text-sm text-gray-600">
            <a href="#how" className="hover:text-gray-900 transition-colors">Как работает</a>
            <a href="#pricing" className="hover:text-gray-900 transition-colors">Тарифы</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              Войти
            </Link>
            <Link
              href="/register"
              className="text-sm bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Начать бесплатно
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pt-20 pb-24 text-center">
        <div className="inline-flex items-center gap-2 text-xs font-medium text-indigo-600 bg-indigo-50 border border-indigo-100 px-3 py-1.5 rounded-full mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>
          Для малого бизнеса в России
        </div>

        <h1 className="text-5xl sm:text-6xl font-extrabold leading-tight tracking-tight mb-6">
          Узнайте что{" "}
          <span className="text-indigo-600">Алиса</span>{" "}
          говорит о вашем бизнесе
        </h1>

        <p className="text-xl text-gray-500 max-w-2xl mx-auto mb-10">
          Мониторинг упоминаний в Яндекс Алисе и ГигаЧате. Конкретный план как подняться выше конкурентов. Автоматическая генерация контента.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/register"
            className="bg-indigo-600 text-white text-base font-semibold px-8 py-3.5 rounded-xl hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-200"
          >
            Попробовать бесплатно
          </Link>
          <a
            href="#how"
            className="bg-white text-gray-700 text-base font-semibold px-8 py-3.5 rounded-xl border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            Как это работает
          </a>
        </div>

        {/* Соцдоказательство */}
        <p className="mt-10 text-sm text-gray-400">
          Отслеживаем Алису, ГигаЧат, YandexGPT, Perplexity и других AI-ботов
        </p>
      </section>

      {/* ── Как работает ───────────────────────────────────────────────────── */}
      <section id="how" className="bg-gray-50 py-24">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Как это работает</h2>
            <p className="text-gray-500 text-lg">Четыре простых шага до первых результатов</p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {STEPS.map((step) => (
              <div key={step.num} className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm">
                <div className="text-4xl font-black text-indigo-100 mb-4">{step.num}</div>
                <h3 className="font-bold text-gray-900 mb-2">{step.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Тарифы ─────────────────────────────────────────────────────────── */}
      <section id="pricing" className="py-24">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Тарифы</h2>
            <p className="text-gray-500 text-lg">Подберите план под ваш бизнес</p>
          </div>

          <div className="grid sm:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`rounded-2xl p-8 border flex flex-col ${
                  plan.highlighted
                    ? "bg-indigo-600 border-indigo-600 text-white shadow-xl shadow-indigo-200"
                    : "bg-white border-gray-200 text-gray-900"
                }`}
              >
                <div className="mb-6">
                  <p className={`text-sm font-medium mb-2 ${plan.highlighted ? "text-indigo-200" : "text-gray-500"}`}>
                    {plan.name}
                  </p>
                  <div className="flex items-baseline gap-1">
                    <span className="text-4xl font-extrabold">{plan.price}</span>
                    <span className={`text-sm ${plan.highlighted ? "text-indigo-200" : "text-gray-400"}`}>
                      ₽/мес
                    </span>
                  </div>
                </div>

                <ul className="space-y-2.5 mb-8 flex-1">
                  <li className={`text-sm font-medium ${plan.highlighted ? "text-indigo-100" : "text-gray-500"}`}>
                    {plan.prompts}
                  </li>
                  <li className={`text-sm font-medium ${plan.highlighted ? "text-indigo-100" : "text-gray-500"}`}>
                    {plan.projects}
                  </li>
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm">
                      <span className={plan.highlighted ? "text-indigo-300" : "text-indigo-500"}>✓</span>
                      {f}
                    </li>
                  ))}
                </ul>

                <Link
                  href="/register"
                  className={`w-full text-center text-sm font-semibold py-3 rounded-xl transition-colors ${
                    plan.highlighted
                      ? "bg-white text-indigo-600 hover:bg-indigo-50"
                      : "bg-indigo-600 text-white hover:bg-indigo-700"
                  }`}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="bg-gray-50 border-t border-gray-100 py-12">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-6">
          <span className="text-lg font-bold text-indigo-600">GEO Analytics</span>
          <div className="flex gap-6 text-sm text-gray-500">
            <a href="#how" className="hover:text-gray-900 transition-colors">Как работает</a>
            <a href="#pricing" className="hover:text-gray-900 transition-colors">Тарифы</a>
            <Link href="/login" className="hover:text-gray-900 transition-colors">Войти</Link>
            <Link href="/register" className="hover:text-gray-900 transition-colors">Регистрация</Link>
          </div>
          <p className="text-xs text-gray-400">© 2025 GEO Analytics. Для малого бизнеса России.</p>
        </div>
      </footer>

    </div>
  );
}
