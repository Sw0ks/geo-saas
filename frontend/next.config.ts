import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone режим для Docker — включает server.js и убирает node_modules из образа
  output: "standalone",

  // Адрес бэкенда — проксируем /api/backend/* на FastAPI
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
