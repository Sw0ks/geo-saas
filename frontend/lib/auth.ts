/**
 * NextAuth.js конфигурация.
 * Используем Credentials provider — авторизация через наш FastAPI бэкенд.
 * JWT-стратегия: токен хранится в зашифрованной cookie.
 */
import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import { authApi } from "@/lib/api";

// Расширяем типы NextAuth чтобы хранить наши поля
declare module "next-auth" {
  interface Session {
    accessToken: string;
    user: {
      id: string;
      email: string;
      name: string;
      subscriptionPlan: string;
    };
  }
  interface User {
    id: string;
    email: string;
    name: string;
    accessToken: string;
    subscriptionPlan: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken: string;
    userId: string;
    subscriptionPlan: string;
  }
}

export const authOptions: NextAuthOptions = {
  // Храним сессию в JWT cookie (не в БД — не нужна доп. таблица)
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 24 * 7, // 7 дней
  },

  pages: {
    signIn: "/login",
    error: "/login",
  },

  providers: [
    CredentialsProvider({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Пароль", type: "password" },
      },

      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        try {
          const data = await authApi.login({
            email: credentials.email,
            password: credentials.password,
          });

          return {
            id: data.user.id,
            email: data.user.email,
            name: data.user.name,
            accessToken: data.access_token,
            subscriptionPlan: data.user.subscription_plan,
          };
        } catch {
          // Возвращаем null — NextAuth покажет страницу с ошибкой
          return null;
        }
      },
    }),
  ],

  callbacks: {
    // Кладём accessToken и userId в JWT cookie
    async jwt({ token, user }) {
      if (user) {
        token.accessToken = user.accessToken;
        token.userId = user.id;
        token.subscriptionPlan = user.subscriptionPlan;
      }
      return token;
    },

    // Прокидываем данные из JWT в сессию (доступно через useSession)
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.user.id = token.userId;
      session.user.subscriptionPlan = token.subscriptionPlan;
      return session;
    },
  },

  secret: process.env.NEXTAUTH_SECRET,
};
