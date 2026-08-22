/**
 * Thin API client. The frontend holds NO pricing logic — every number it
 * renders was computed by the Python engine and arrives over these calls.
 */
import type {
  HistoryEntry,
  MarketObservation,
  Preview,
  PricingConfig,
  Property,
  Recommendation,
  RecommendationDetail,
  Summary,
  SystemStatus,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the default message */
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface RecommendationFilters {
  property_id?: number | null;
  room_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: string | null;
  search?: string | null;
}

function toQuery(filters: RecommendationFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "" && value !== "all") {
      params.set(key, String(value));
    }
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  status: () => request<SystemStatus>("/api/status"),
  properties: () => request<Property[]>("/api/properties"),

  recommendations: (filters: RecommendationFilters = {}) =>
    request<Recommendation[]>(`/api/recommendations${toQuery(filters)}`),
  summary: (filters: RecommendationFilters = {}) =>
    request<Summary>(`/api/recommendations/summary${toQuery(filters)}`),
  recommendation: (id: number) => request<RecommendationDetail>(`/api/recommendations/${id}`),
  generate: () => request<Record<string, unknown>>("/api/recommendations/generate", { method: "POST" }),

  accept: (id: number, note?: string) =>
    request<RecommendationDetail>(`/api/recommendations/${id}/accept`, {
      method: "POST",
      body: JSON.stringify({ note: note || null }),
    }),
  override: (id: number, final_price: number, reason_code: string, note?: string) =>
    request<RecommendationDetail>(`/api/recommendations/${id}/override`, {
      method: "POST",
      body: JSON.stringify({ final_price, reason_code, note: note || null }),
    }),
  resetDecision: (id: number) =>
    request<RecommendationDetail>(`/api/recommendations/${id}/reset`, { method: "POST" }),

  config: () => request<PricingConfig>("/api/settings/config"),
  defaults: () => request<{ payload: any; factor_order: string[] }>("/api/settings/defaults"),
  saveConfig: (payload: any, label = "operator-edit", note?: string) =>
    request<PricingConfig>("/api/settings/config", {
      method: "PUT",
      body: JSON.stringify({ payload, label, note: note || null, regenerate: true }),
    }),
  resetConfig: () => request<PricingConfig>("/api/settings/reset", { method: "POST" }),
  preview: (payload: any, room_id?: number | null, stay_date?: string | null) =>
    request<Preview | null>("/api/settings/preview", {
      method: "POST",
      body: JSON.stringify({ payload, room_id: room_id ?? null, stay_date: stay_date ?? null }),
    }),

  history: (params: { decision?: string; property_id?: number | null } = {}) =>
    request<HistoryEntry[]>(`/api/history${toQuery(params as RecommendationFilters)}`),

  observations: (params: { room_id?: number | null; stay_date?: string | null; source?: string | null } = {}) =>
    request<MarketObservation[]>(`/api/market/observations${toQuery(params as RecommendationFilters)}`),
  addObservation: (body: Record<string, unknown>) =>
    request<MarketObservation>("/api/market/observations", { method: "POST", body: JSON.stringify(body) }),
  deleteObservation: (id: number) =>
    request<void>(`/api/market/observations/${id}`, { method: "DELETE" }),
  marketProviders: () =>
    request<{ key: string; name: string; healthy: boolean; mode: string; detail: string; remediation: string }[]>(
      "/api/market/providers",
    ),
  collectMarket: (stay_date: string, room_id?: number | null) =>
    request<{ ok: boolean; collected: number; message: string; remediation: string; provider: string }>(
      "/api/market/collect",
      { method: "POST", body: JSON.stringify({ stay_date, room_id: room_id ?? null }) },
    ),

  sync: () => request<Record<string, any>>("/api/sync", { method: "POST" }),
  resetDemo: () => request<Record<string, any>>("/api/demo/reset", { method: "POST" }),
};
