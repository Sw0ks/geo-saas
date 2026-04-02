/**
 * Базовый клиент для запросов к FastAPI бэкенду.
 * Все запросы идут через этот модуль — не вызывай fetch напрямую в компонентах.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  token?: string;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, token, ...rest } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(rest.headers as Record<string, string> | undefined),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // Для 204 No Content возвращаем null
  if (response.status === 204) return null as T;

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : `Ошибка ${response.status}`;
    throw new ApiError(response.status, message, data.detail);
  }

  return data as T;
}

// Хелпер для /api/v1/* эндпоинтов
function apiV1<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>(`/api/v1${path}`, options);
}

// ──────────────── Auth ────────────────

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  subscription_plan: string;
  subscription_expires_at: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export const authApi = {
  register: (data: { email: string; name: string; password: string }) =>
    apiV1<TokenResponse>("/auth/register", { method: "POST", body: data }),

  login: (data: { email: string; password: string }) =>
    apiV1<TokenResponse>("/auth/login", { method: "POST", body: data }),

  me: (token: string) =>
    apiV1<AuthUser>("/auth/me", { token }),

  logout: (token: string) =>
    apiV1<void>("/auth/logout", { method: "POST", token }),

  updateMe: (token: string, data: { name?: string; password?: string }) =>
    apiV1<AuthUser>("/auth/me", { method: "PATCH", body: data, token }),
};

// ──────────────── Projects ────────────────

export interface Project {
  id: string;
  user_id: string;
  name: string;
  domain: string;
  competitors: string[];
  prompts: string[];
  tracker_token: string;
  created_at: string;
}

export const projectsApi = {
  list: (token: string) =>
    apiV1<Project[]>("/projects", { token }),

  get: (token: string, id: string) =>
    apiV1<Project>(`/projects/${id}`, { token }),

  create: (token: string, data: { name: string; domain: string; competitors?: string[]; prompts?: string[] }) =>
    apiV1<Project>("/projects", { method: "POST", body: data, token }),
};

// ──────────────── Monitoring ────────────────

export interface MonitoringResult {
  id: string;
  project_id: string;
  prompt: string;
  platform: "alice" | "gigachat";
  mentioned: boolean;
  position: number | null;
  sentiment: "positive" | "neutral" | "negative" | null;
  response_text: string | null;
  checked_at: string;
}

export interface MonitoringStats {
  total: number;
  mentioned: number;
  mention_rate: number;
  avg_position: number | null;
  by_platform: Record<string, { total: number; mentioned: number; mention_rate: number }>;
  by_sentiment: Record<string, number>;
}

export interface RunMonitoringResponse {
  message: string;
  project_id: string;
  prompts_count: number;
}

export const monitoringApi = {
  run: (token: string, projectId: string) =>
    apiV1<RunMonitoringResponse>("/monitoring/run", {
      method: "POST",
      body: { project_id: projectId },
      token,
    }),

  results: (token: string, projectId: string) =>
    apiV1<MonitoringResult[]>(`/monitoring/${projectId}`, { token }),

  stats: (token: string, projectId: string) =>
    apiV1<MonitoringStats>(`/monitoring/${projectId}/stats`, { token }),
};

// ──────────────── Crawler ────────────────

export interface CrawlerEvent {
  id: string;
  project_id: string;
  bot_name: string;
  user_agent: string | null;
  url_path: string;
  ip: string | null;
  verified: boolean;
  visited_at: string;
}

export interface CrawlerStats {
  project_id: string;
  total_visits: number;
  verified_visits: number;
  by_bot: Record<string, number>;
  by_day: Array<{ date: string; count: number }>;
  top_pages: Array<{ url: string; visits: number }>;
}

export interface TrackerTokenResponse {
  project_id: string;
  tracker_token: string;
  snippet_url: string;
}

export const crawlerApi = {
  token: (token: string, projectId: string) =>
    apiV1<TrackerTokenResponse>(`/crawler/${projectId}/token`, { token }),

  events: (token: string, projectId: string, params?: { bot_name?: string; verified_only?: boolean; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.bot_name) qs.set("bot_name", params.bot_name);
    if (params?.verified_only) qs.set("verified_only", "true");
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString() ? `?${qs}` : "";
    return apiV1<CrawlerEvent[]>(`/crawler/${projectId}/events${query}`, { token });
  },

  stats: (token: string, projectId: string) =>
    apiV1<CrawlerStats>(`/crawler/${projectId}/stats`, { token }),
};

// ──────────────── Agent / Action Plans ────────────────

export interface ActionTask {
  priority: number;
  category: "content" | "faq" | "technical" | "mentions" | "tone";
  title: string;
  description: string;
  expected_result: string;
}

export interface ActionPlan {
  id: string;
  project_id: string;
  tasks_json: Array<{ _summary?: string } & Partial<ActionTask>>;
  generated_at: string;
  status: "new" | "in_progress" | "done";
}

export interface GeneratePlanResponse {
  plan: ActionPlan;
  tasks_count: number;
  summary: string;
  message: string;
}

export const agentApi = {
  generatePlan: (token: string, projectId: string) =>
    apiV1<GeneratePlanResponse>("/agent/generate-plan", {
      method: "POST",
      body: { project_id: projectId },
      token,
    }),

  latestPlan: (token: string, projectId: string) =>
    apiV1<GeneratePlanResponse>(`/agent/plan/${projectId}`, { token }),

  planHistory: (token: string, projectId: string) =>
    apiV1<ActionPlan[]>(`/agent/plans/${projectId}`, { token }),

  updateStatus: (token: string, planId: string, status: ActionPlan["status"]) =>
    apiV1<ActionPlan>(`/agent/plan/${planId}/status`, {
      method: "PATCH",
      body: { status },
      token,
    }),

  suggestPrompts: (token: string, data: { name: string; description: string }) =>
    apiV1<{ prompts: string[] }>("/agent/suggest-prompts", {
      method: "POST",
      body: data,
      token,
    }),
};

// ──────────────── Content ────────────────

export type ContentType = "article" | "faq" | "description";
export type ContentStatus = "draft" | "published";

export interface GeneratedContent {
  id: string;
  project_id: string;
  type: ContentType;
  title: string;
  body: string;
  status: ContentStatus;
  created_at: string;
}

export const contentApi = {
  generate: (
    token: string,
    data: { project_id: string; type: ContentType; topic: string; task_id?: string; additional_context?: string }
  ) =>
    apiV1<GeneratedContent>("/agent/generate-content", {
      method: "POST",
      body: data,
      token,
    }),

  list: (token: string, projectId: string, params?: { type?: ContentType; status?: ContentStatus }) => {
    const qs = new URLSearchParams();
    if (params?.type) qs.set("type", params.type);
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString() ? `?${qs}` : "";
    return apiV1<GeneratedContent[]>(`/agent/content/${projectId}${query}`, { token });
  },

  updateStatus: (token: string, contentId: string, status: ContentStatus) =>
    apiV1<GeneratedContent>(`/agent/content/${contentId}/status`, {
      method: "PATCH",
      body: { status },
      token,
    }),
};
