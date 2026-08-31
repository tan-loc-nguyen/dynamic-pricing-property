/**
 * Includes "error": a night the engine could not price.
 *
 * Omitting it was not a harmless gap. TypeScript then reported
 * `status === "error"` as a comparison that "can never be true", so the
 * drawer's unpriced branch read as dead code and was deleted — after which an
 * unpriced night showed a confident rate and Accept failed with a 409. The
 * vocabulary has always carried `status.error` ("Unpriced"); only this union
 * disagreed.
 */
export type Status = "pending" | "accepted" | "overridden" | "error";
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
  /** null = this season imposes no ceiling; the dynamic bound is the limit. */
  max_net_rate: number | null;
  currency: string;
  rate_basis: string;
  source: string;
  note: string | null;
}

/** A rejected configuration field: a code the UI translates, plus the English
 *  message the server logs and returns in a 422 body. */
export interface ConfigProblem {
  code: string;
  path: string | null;
  params: Record<string, string | number>;
  message: string;
}

/** One explainable step, reduced to what it takes to RENDER one.
 *
 *  A range's averaged breakdown carries exactly this and no more — it has no
 *  single `price_before`, `factor` or `sequence`, because it is several
 *  nights folded together. Typing those lines as full `Adjustment`s claimed
 *  fields the API never sends, which is a union wider than the thing it
 *  describes: the compiler would have accepted a component reaching for a
 *  price that does not exist. */
export interface ExplainedStep {
  code: string;
  label: string;
  delta: number;
  /** Message key for the label and its sentence; null when the wording is
   *  operator-authored and must be shown verbatim. */
  label_key: string | null;
  /** The figures the sentence interpolates. Never pre-formatted. */
  params: Record<string, unknown>;
  is_neutral: boolean;
  is_ignored: boolean;
}

export interface Adjustment extends ExplainedStep {
  sequence: number;
  adjustment_pct: number;
  factor: number;
  price_before: number;
  price_after: number;
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
  /** Where current_net_rate came from. Blue Jay publishes no forward rate, so
   *  most live/snapshot rates are reconstructed — and an achieved average must
   *  never be read as a published list price. */
  rate_provenance:
    | "published"
    | "derived_adr"
    // The seasonal band's BASE for that date's season. This union OMITTED it,
    // which is the `Status`-without-"error" bug again: the value was emitted,
    // TypeScript called the branch handling it dead, and the drawer drew a
    // styled EMPTY box on every unbooked night. Kept in step with
    // RATE_PROVENANCE_VALUES in providers/pms/base.py.
    | "seasonal_base"
    | "last_known_adr"
    | "unavailable";
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
  engine_version: string;
  config_version: number;
  created_at: string;
  missing_signals: string[];
  pace_label_key: string | null;
  pickup_label_key: string | null;
  pace_label: string | null;
  pickup_label: string | null;
  pace_tone: "up" | "down" | "info" | "neutral" | null;
  unpriced: boolean;
  unpriced_reason: string | null;
  /** Which validated bound stopped the dynamic layer, or null.
   *
   *  NARROWED from `string`. viz.tsx renders it with a ternary
   *  (`clamped === "min" ? … : …`), so a third value would silently render as
   *  MAX — the blank-box class inverted: not missing text, but confidently
   *  WRONG text. With the union closed, the ternary is exhaustive by
   *  construction. Kept in step with pricing/engine.py. */
  clamp_applied: "min" | "max" | null;
}

/** Where a range's `current_net_rate` figures came from.
 *
 *  Same values as `Recommendation.rate_provenance`, plus "mixed" — a range can
 *  span nights that disagree, and showing the majority value would hide a
 *  minority "unavailable" behind a confident-looking one. */
export type RangeProvenance = Recommendation["rate_provenance"] | "mixed";

/** What the last market collection attempted and found. */
export interface CollectorReport {
  /** False = never collected. Distinct from ran-and-found-nothing, which is a
   *  broken source rather than an unconfigured one. */
  has_run: boolean;
  ran_at: string | null;
  attempted: number;
  prices_found: number;
  truncated_nights: number;
  errors: string[];
  error_count: number;
}

/** One operator-defined season: a contiguous run of whole months.
 *
 *  The seasons together cover the year exactly once. `months` may WRAP —
 *  [11, 12, 1] is High Season 2 — so it is not safe to sort it. */
export interface SeasonDef {
  key: string;
  label: string;
  months: number[];
}

/** One room tier over a date range: the Rate page's tile. */
export interface RateTile {
  room_type_id: number;
  room_type_name: string;
  room_category: string;
  room_category_label: string;
  units_total: number;
  /** Units with at least one FREE NIGHT in the range — not unit-nights. */
  available_units: number;
  /** False when unassigned bookings make the count a provable floor rather
   *  than the exact answer, so the tile can say so instead of implying
   *  precision it does not have. */
  availability_is_exact: boolean;
  average_recommended_net_rate: number;
  average_current_net_rate: number;
  change_pct: number;
  unpriced_nights: number;
}

export interface RateTiles {
  start_date: string;
  end_date: string;
  nights: number;
  season: { key: string; label: string; start: string; end: string };
  tiles: RateTile[];
}

/** One night inside a range — the per-night strip and the pace curve. */
export interface RangeNight {
  stay_date: string;
  units_sold: number;
  units_total: number;
  recommended_net_rate: number;
  priced: boolean;
  days_to_arrival: number | null;
  expected_occupancy: number | null;
  occupancy: number | null;
}

/** What the drawer renders for a range. */
export interface RangeDetail {
  room_type_id: number;
  room_type_name: string;
  room_category: string;
  room_category_label: string;
  start_date: string;
  end_date: string;
  nights: number;
  season: { key: string; label: string; start: string; end: string };
  base_net_rate: number;
  average_recommended_net_rate: number;
  average_current_net_rate: number;
  /** ONE band for the whole range — guaranteed by the season check on the
   *  server. `max` is nullable: an empty MAX means the only ceiling is the
   *  dynamic bound, and the band strip is drawn open to the right. */
  band: { min: number | null; base: number | null; max: number | null };
  adjustments: ExplainedStep[];
  nightly: RangeNight[];
  pace_gap: number | null;
  units_sold: number;
  units_total: number;
  available_units: number;
  availability_is_exact: boolean;
  unpriced_nights: number;
  rate_provenance: RangeProvenance;
}

export interface BulkDecisionResult {
  group_id: string;
  net_rate: number;
  decisions_written: number;
  nights: number;
  skipped_unpriced: number;
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
  /** Warnings about the DATA — a snapshot that may still hold guest details,
   *  or whose pseudonyms are recoverable. Separate from mapping gaps on
   *  purpose: a guest-data warning under a "mapping" heading reads as a nit. */
  warnings: string[];
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
  /** What the last sync could not vouch for. */
  last_sync_findings: { warnings?: string[]; discrepancies?: string[]; skipped?: number };
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
  problems: ConfigProblem[];
  room_type_id: number;
  room_type_name: string;
  room_category_label: string;
  stay_date: string;
  currency: string;
  season_label: string | null;
  /** Codes, translated client-side. The *_label fields above are English in
   *  every locale and must not be rendered to an operator. */
  room_category: string | null;
  season_key: string | null;
  band_min_net_rate: number | null;
  band_base_net_rate: number | null;
  band_max_net_rate: number | null;
  base_net_rate: number;
  current_net_rate: number;
  recommended_net_rate: number;
  change_pct: number;
  total_adjustment_pct: number;
  adjustments: Adjustment[];
  engine_version: string;
}

export interface HistoryEntry {
  id: number;
  created_at: string;
  property_name: string;
  room_type_name: string;
  room_category_label: string;
  room_category: string | null;
  stay_date: string;
  season_label: string | null;
  season_key: string | null;
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
  /** Set when this decision came from a bulk range action; the log groups on
   *  it so a fortnight priced in one click reads as one entry, not fourteen. */
  group_id: string | null;
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
  confidence_code: string | null;
  confidence_gaps: string[];
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

/**
 * ONE OCCUPIED UNIT-NIGHT, not a stay.
 *
 * There is deliberately no `nights` and no `last_night`: the provider emits one
 * row per occupied room per night, so a span cannot be built from this and an
 * earlier attempt drew ~3.5x the real occupancy. Stay ranges need Blue Jay
 * (ASSUMPTIONS U16), as does unit assignment.
 */
export interface Booking {
  id: number;
  external_id: string;
  room_type_id: number;
  room_category: string | null;
  /** NULL for every seeded booking — unit assignment needs Blue Jay (U11). */
  physical_room_id: number | null;
  stay_date: string;
  guests: number;
  net_rate: number;
  channel: string;
  status: string;
}

export type PmsSource = "mock" | "snapshot" | "bluejay";

/** One documented Blue Jay testing window. `confirmed` is false for the
 *  `24:00-24:59` entry, which is not clock notation and is never auto-called. */
export interface TestingWindow {
  text: string;
  confirmed: boolean;
  note: string;
}

export interface UnmappedRoomType {
  id: string;
  name: string;
}

export interface PmsSourceInfo {
  active: PmsSource;
  available: string[];
  sources: { key: PmsSource; label_key: string; hint_key: string }[];
  bluejay_window: {
    timezone: string;
    now: string;
    is_open: boolean;
    next_open_at: string | null;
    seconds_until_open: number;
    windows: TestingWindow[];
  };
}
