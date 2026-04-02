/**
 * Корневой layout приложения.
 * Оборачивает всё дерево в SessionProvider (нужен для useSession в Client Components).
 */
import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "GEO Analytics — мониторинг упоминаний в AI",
  description:
    "Узнайте, упоминает ли Алиса и ГигаЧат ваш бизнес. Получите план как попасть в ответы AI.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-gray-50 font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
