/**
 * Next.js middleware — защищает роуты дашборда.
 * Неавторизованных пользователей редиректит на /login.
 */
import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

export default withAuth(
  function middleware(req) {
    // Дополнительная логика (например, проверка тарифа) — здесь
    return NextResponse.next();
  },
  {
    callbacks: {
      // Разрешаем доступ только если есть токен в сессии
      authorized: ({ token }) => !!token,
    },
  },
);

// Защищаем все страницы дашборда
export const config = {
  matcher: ["/dashboard/:path*"],
};
