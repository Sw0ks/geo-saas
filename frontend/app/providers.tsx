"use client";

/**
 * Client-компонент обёртка для всех провайдеров.
 * SessionProvider требует "use client" — выносим отдельно от layout.
 */
import { SessionProvider } from "next-auth/react";

export function Providers({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
