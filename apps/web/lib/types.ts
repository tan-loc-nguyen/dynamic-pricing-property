export type Status = "pending" | "accepted" | "overridden";

export interface Room {
  id: number;
  external_id: string;
  name: string;
  room_type: string;
  capacity: number;
  units_total: number;
  base_price: number;
  min_price: number;
  max_price: number;
  is_active: boolean;
}

export interface Property {
  id: number;
  external_id: string;
  name: string;
  city: string;
  district: string;
  currency: string;
  rooms: Room[];
}

export interface Adjustment {
  sequence: number;
  code: string;
  label: string;
  factor: number;
  price_before: number;
  price_after: number;
  delta: number;
  reason: string;
  is_neutral: boolean;
}

export interface Decision {
  id: number;
  decision: string;
  recommended_price: number;
  final_price: number;
  previous_price: number;
  reason_code: string | null;
  reason_label: string | null;
  note: string | null;
  engine_version: string;
  config_version: number;
  operator: string;
  created_at: string;
}

export interface Recommendation {
  id: number;
  run_id: string;
  property_id: number;
  property_name: string;
  room_id: number;
  room_name: string;
  room_type: string;
  stay_date: string;
  day_of_week: string | null;
  currency: string;
  base_price: number;
  current_price: number;
  price_before_bounds: number;
  recommended_price: number;
  change_pct: number;
  change_abs: number;
  total_multiplier: number;
  occupancy: number | null;
  units_sold: number | null;
  units_total: number | null;
  days_to_checkin: number | null;
  booking_pace_index: number | null;
  market_price_index: number | null;
  market_reference_price: number | null;
  market_observation_count: number;
  is_event: boolean;
  event_name: string | null;
  status: Status;
  explanation: string;
  engine_version: string;
  config_version: number;
  created_at: string;
  missing_signals: string[];
}

export interface RecommendationDetail extends Recommendation {
  adjustments: Adjustment[];
  decisions: Decision[];
  features: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface Summary {
  active_rooms: number;
  upcoming_nights: number;
  average_occupancy: number | null;
  pending_recommendations: number;
  accepted_recommendations: number;
  overridden_recommendations: number;
  average_recommended_change_pct: number;
  total_recommendations: number;
  currency: string;
  horizon_start: string | null;
  horizon_end: string | null;
}

export interface ProviderStatus {
  name: string;
  healthy: boolean;
  mode: string;
  detail: string;
  remediation: string;
  unresolved_mappings: string[];
}

export interface SystemStatus {
  api_version: string;
  engine: { key: string; name: string; version: string; description: string };
  available_engines: { key: string; name: string; version: string; description: string }[];
  config_version: number;
  config_label: string;
  pms: ProviderStatus;
  market: ProviderStatus;
  data_provider_setting: string;
  market_provider_setting: string;
  counts: Record<string, number>;
  override_reasons: { code: string; label: string }[];
  demo_mode: boolean;
  last_run_id: string | null;
}

export interface PricingConfig {
  version: number;
  label: string;
  payload: any;
  is_active: boolean;
  created_at: string;
  note: string | null;
}

export interface Preview {
  room_id: number;
  room_name: string;
  stay_date: string;
  currency: string;
  base_price: number;
  current_price: number;
  recommended_price: number;
  change_pct: number;
  price_before_bounds: number;
  adjustments: Adjustment[];
  explanation: string;
  engine_version: string;
}

export interface HistoryEntry {
  id: number;
  created_at: string;
  property_name: string;
  room_name: string;
  stay_date: string;
  decision: string;
  recommended_price: number;
  final_price: number;
  previous_price: number;
  difference: number;
  difference_pct: number;
  reason_code: string | null;
  reason_label: string | null;
  note: string | null;
  engine_version: string;
  config_version: number;
  operator: string;
  currency: string;
}

export interface MarketObservation {
  id: number;
  property_id: number | null;
  room_id: number | null;
  property_name: string | null;
  room_name: string | null;
  stay_date: string;
  competitor_name: string;
  observed_price: number;
  currency: string;
  source: string;
  source_url: string | null;
  notes: string | null;
  collected_at: string;
}
