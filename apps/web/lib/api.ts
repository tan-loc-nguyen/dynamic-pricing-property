/**
 * Thin API client. The frontend holds NO pricing logic — every number it
 * renders was computed by the Python engine and arrives over these calls.
 */
import type {
  Booking,
  Competitor,
  EventItem,
  HistoryEntry,
  MarketObservation,
  Preview,
  PricingConfig,
  Property,
  RateBand,
  Recommendation,
  RecommendationDetail,
  Summary,
  SystemStatus,
} from "./types";

/**
 * Where the API lives.
 *
 * `make dev` runs the frontend on :3000 and the API on :8000, so a bare build
 * needs the absolute address. The PACKAGED build serves both from one process
 * on whatever port was free, so it sets `NEXT_PUBLIC_API_URL=/` and every call
 * becomes a relative path — baking in a port the runner may not get is how the
 * whole app breaks on the one laptop that already has something on 8000.
 *
 * The empty string is a meaningful value here (it means "same origin"), which
 * is why this tests for absence rather than falsiness.
 */
const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL;

export const API_URL =
  configuredApiUrl === undefined || configuredApiUrl === ""
    ? "http://127.0.0.1:8000"
    : configuredApiUrl.replace(/\/$/, "");

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

export interface RecommendationFilters extends Record<string, unknown> {
  property_id?: number | null;
  room_type_id?: number | null;
  room_category?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: string | null;
  search?: string | null;
  /** Comma-separated room-category / season codes, resolved from the
   *  operator's own language by lib/search.ts. */
  codes?: string | null;
}

function toQuery(filters: Record<string, unknown>): string {
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
  engines: () => request<{ key: string; name: string; version: string }[]>("/api/engines"),

  // --- recommendations ---------------------------------------------------
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
  override: (id: number, final_net_rate: number, reason_code: string, note?: string) =>
    request<RecommendationDetail>(`/api/recommendations/${id}/override`, {
      method: "POST",
      body: JSON.stringify({ final_net_rate, reason_code, note: note || null }),
    }),
  resetDecision: (id: number) =>
    request<RecommendationDetail>(`/api/recommendations/${id}/reset`, { method: "POST" }),

  // --- rate book (CLIENT VALIDATED) --------------------------------------
  rateBook: () => request<RateBand[]>("/api/rate-book"),
  rateBookMeta: () => request<any>("/api/rate-book/meta"),
  updateRateBand: (id: number, body: { min_net_rate: number; base_net_rate: number; max_net_rate: number }) =>
    request<RateBand>(`/api/rate-book/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  resetRateBook: () => request<any>("/api/rate-book/reset", { method: "POST" }),

  // --- experimental dynamic strategy -------------------------------------
  config: () => request<PricingConfig>("/api/settings/config"),
  defaults: () => request<any>("/api/settings/defaults"),
  saveConfig: (payload: any, label = "operator-edit") =>
    request<PricingConfig>("/api/settings/config", {
      method: "PUT",
      body: JSON.stringify({ payload, label, regenerate: true }),
    }),
  resetConfig: () => request<PricingConfig>("/api/settings/reset", { method: "POST" }),
  preview: (payload: any, room_type_id?: number | null, stay_date?: string | null) =>
    request<Preview | null>("/api/settings/preview", {
      method: "POST",
      body: JSON.stringify({ payload, room_type_id: room_type_id ?? null, stay_date: stay_date ?? null }),
    }),

  // --- bookings (the calendar's occupancy timeline) -----------------------
  bookings: (params: { start_date?: string | null; end_date?: string | null } = {}) =>
    request<Booking[]>(`/api/bookings${toQuery(params)}`),

  // --- history -----------------------------------------------------------
  history: (params: { decision?: string; room_type_id?: number | null } = {}) =>
    request<HistoryEntry[]>(`/api/history${toQuery(params)}`),

  // --- market ------------------------------------------------------------
  observations: (params: { room_type_id?: number | null; stay_date?: string | null; start_date?: string | null; end_date?: string | null; source?: string | null; confidence?: string | null; limit?: number | null } = {}) =>
    request<MarketObservation[]>(`/api/market/observations${toQuery(params)}`),
  addObservation: (body: Record<string, unknown>) =>
    request<MarketObservation>("/api/market/observations", { method: "POST", body: JSON.stringify(body) }),
  deleteObservation: (id: number) =>
    request<void>(`/api/market/observations/${id}`, { method: "DELETE" }),
  marketMeta: () => request<any>("/api/market/meta"),
  marketProviders: () =>
    request<{ key: string; name: string; healthy: boolean; mode: string; detail: string; remediation: string; max_confidence: string }[]>(
      "/api/market/providers",
    ),
  collectMarket: (stay_date: string, room_type_id?: number | null) =>
    request<{ ok: boolean; collected: number; message: string; remediation: string; provider: string }>(
      "/api/market/collect",
      { method: "POST", body: JSON.stringify({ stay_date, room_type_id: room_type_id ?? null }) },
    ),
  competitors: () => request<Competitor[]>("/api/market/competitors"),
  addCompetitor: (body: Record<string, unknown>) =>
    request<Competitor>("/api/market/competitors", { method: "POST", body: JSON.stringify(body) }),
  deleteCompetitor: (id: number) =>
    request<void>(`/api/market/competitors/${id}`, { method: "DELETE" }),

  // --- events ------------------------------------------------------------
  events: (includeInactive = false) =>
    request<EventItem[]>(`/api/events${toQuery({ include_inactive: includeInactive || null })}`),
  eventMeta: () => request<any>("/api/events/meta"),
  addEvent: (body: Record<string, unknown>) =>
    request<EventItem>("/api/events", { method: "POST", body: JSON.stringify(body) }),
  deleteEvent: (id: number) => request<void>(`/api/events/${id}`, { method: "DELETE" }),

  // --- outcomes ----------------------------------------------------------
  outcomeSummary: () => request<Record<string, any>>("/api/outcomes/summary"),
  generateDemoOutcomes: () => request<any>("/api/outcomes/demo", { method: "POST" }),

  sync: () => request<Record<string, any>>("/api/sync", { method: "POST" }),
  resetDemo: () => request<Record<string, any>>("/api/demo/reset", { method: "POST" }),

  pmsSource: () => request<import("./types").PmsSourceInfo>("/api/pms/source"),
  setPmsSource: (source: string) =>
    request<{ active: string }>("/api/pms/source", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    }),
  categoryMap: () =>
    request<{
      map: Record<string, string>;
      categories: string[];
      unmapped: import("./types").UnmappedRoomType[];
    }>("/api/pms/category-map"),
  setCategoryMap: (map: Record<string, string>) =>
    request<{ map: Record<string, string> }>("/api/pms/category-map", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ map }),
    }),
};
