FROM node:20-alpine AS base

WORKDIR /app

# Устанавливаем зависимости
COPY package.json package-lock.json* ./
RUN npm ci --frozen-lockfile

# Копируем исходный код
COPY . .

# Сборка
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Production runner
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Копируем только необходимое для запуска
COPY --from=base /app/public ./public
COPY --from=base /app/.next/standalone ./
COPY --from=base /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
