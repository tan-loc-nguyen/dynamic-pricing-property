export type Status = "pending" | "accepted" | "overridden";
export type Confidence = "HIGH" | "MEDIUM" | "LOW" | "UNUSABLE";

export interface PhysicalRoom {
  id: number;
  external_id: string;
  unit_label: string;
  floor: string | null;
  is_active: boolean;
}

export interface RoomType {
  id: number;
  external_id: string;
  name: string;
  category: string;
  category_label: string;
  capacity: number;
  units_total: number;
  is_active: boolean;
  physical_rooms: PhysicalRoom[];
}

export interface Property {
  id: number;
  external_id: string;
  name: string;
  city: string;
  district: string;
  currency: string;
  room_types: RoomType[];
}

export interface RateBand {
  id: number;
  season_key: string;
  season_label: string;
  months: number[];
  room_category: string;
  room_category_label: string;
  min_net_rate: number;
  base_net_rate: number;
  max_net_rate: number;
  currency: string;
  rate_basis: string;
  source: string;
  note: string | null;
}

export interface Adjustment {
  sequence: number;
  code: string;
  label: string;
  adjustment_pct: number;
  factor: number;
  price_before: number;
  price_after: number;
  delta: number;
  reason: string;
  is_neutral: boolean;
  is_ignored: boolean;
}

export interface Decision {
  id: number;
  decision: string;
  recommended_net_rate: number;
  final_net_rate: number;
  previous_net_rate: number;
  reason_code: string | null;
  reason_label: string | null;
  note: string | null;
  engine_version: string;
  config_version: number;
  operator: string;
  created_at: string;
}

export interface Outcome {
  id: number;
  units_booked: number | null;
  final_occupancy: number | null;
  realized_net_rate: number | null;
  realized_revenue: number | null;
  cancellations: number | null;
  is_synthetic: boolean;
  source: string;
  captured_at: string;
  notes: string | null;
}

export interface Recommendation {
  id: number;
  run_id: string;
  mode: string;
  property_id: number;
  property_name: string;
  room_type_id: number;
  room_type_name: string;
  room_category: string;
  room_category_label: string;
  stay_date: string;
  day_of_week: string | null;
  currency: string;

  season_key: string | null;
  season_label: string | null;
  band_min_net_rate: number | null;
  band_base_net_rate: number | null;
  band_max_net_rate: number | null;
  rate_band_source: string | null;

  base_net_rate: number;
  current_net_rate: number;
  current_ota_price: number | null;
  net_rate_before_clamp: number;
  recommended_net_rate: number;
  change_pct: number;
  change_abs: number;
  total_adjustment_pct: number;

  units_total: number | null;
  units_sold: number | null;
  units_available: number | null;
  occupancy: number | null;
  days_to_arrival: number | null;
  expected_occupancy: number | null;
  pace_gap: number | null;
  recent_pickup: number | null;
  pickup_delta: number | null;

  is_event: boolean;
  event_name: string | null;
  event_impact_level: string | null;

  market_price_index: number | null;
  market_reference_net_rate: number | null;
  market_confidence: Confidence | null;
  market_observation_count: number;
  market_qualified_count: number;
  market_ignored_count: number;

  status: Status;
  explanation: string;
  engine_version: string;
  config_version: number;
  created_at: string;
  missing_signals: string[];
  clamp_applied: string | null;
}

export interface RecommendationDetail extends Recommendation {
  adjustments: Adjustment[];
  decisions: Decision[];
  outcomes: Outcome[];
  features: Record<string, any>;
  metadata: Record<string, any>;
}

export interface Summary {
  room_types: number;
  total_units: number;
  upcoming_nights: number;
  average_occupancy: number | null;
  average_pace_gap: number | null;
  pending_recommendations: number;
  accepted_recommendations: number;
  overridden_recommendations: number;
  unpriced_recommendations: number;
  average_recommended_change_pct: number;
  total_recommendations: number;
  currency: string;
  horizon_start: string | null;
  horizon_end: string | null;
  mode: string;
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
  mode: string;
  engine: { key: string; name: string; version: string; description: string };
  available_engines: { key: string; name: string; version: string; description: string }[];
  booking_curve: { name: string; validated: boolean; note: string };
  rate_book: { source: string; rate_basis: string; bands: number; seasons: number; categories: number };
  config_version: number;
  config_label: string;
  pms: ProviderStatus;
  market: ProviderStatus;
  data_provider_setting: string;
  market_provider_setting: string;
  counts: Record<string, number>;
  override_reasons: { code: string; label: string }[];
  vocabularies: Record<string, any>;
  outcome_readiness: {
    total_outcomes: number;
    synthetic_outcomes: number;
    real_outcomes: number;
    decided_recommendations: number;
    ready_for_evaluation: boolean;
    note: string;
  };
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
  problems: string[];
  room_type_id: number;
  room_type_name: string;
  room_category_label: string;
  stay_date: string;
  currency: string;
  season_label: string | null;
  band_min_net_rate: number | null;
  band_base_net_rate: number | null;
  band_max_net_rate: number | null;
  base_net_rate: number;
  current_net_rate: number;
  recommended_net_rate: number;
  change_pct: number;
  total_adjustment_pct: number;
  adjustments: Adjustment[];
  explanation: string;
  engine_version: string;
}

export interface HistoryEntry {
  id: number;
  created_at: string;
  property_name: string;
  room_type_name: string;
  room_category_label: string;
  stay_date: string;
  season_label: string | null;
  decision: string;
  recommended_net_rate: number;
  final_net_rate: number;
  previous_net_rate: number;
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
  room_type_id: number | null;
  competitor_id: number | null;
  room_type_name: string | null;
  stay_date: string;
  competitor_name: string;
  observed_price: number;
  currency: string;
  room_category: string | null;
  length_of_stay: number | null;
  guests: number | null;
  price_basis: string;
  tax_inclusion: string;
  fee_inclusion: string;
  promotion_status: string;
  is_refundable: boolean | null;
  confidence: Confidence;
  confidence_reason: string | null;
  source: string;
  source_url: string | null;
  notes: string | null;
  observed_at: string;
}

export interface Competitor {
  id: number;
  name: string;
  location: string;
  comparable_category: string | null;
  source: string;
  source_url: string | null;
  is_active: boolean;
  notes: string | null;
  observation_count: number;
}

export interface EventItem {
  id: number;
  property_id: number | null;
  name: string;
  start_date: string;
  end_date: string;
  impact_level: string;
  adjustment_pct: number | null;
  event_type: string;
  source: string;
  notes: string | null;
  is_active: boolean;
  created_at: string;
}
