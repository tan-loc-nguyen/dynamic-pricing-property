"""Pydantic API schemas (transport only — no business logic).

Naming rule: every monetary field says whether it is a NET rate or an OTA
price. There is no bare "price".
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- portfolio
class PhysicalRoomOut(BaseModel):
    id: int
    external_id: str
    unit_label: str
    floor: str | None = None
    is_active: bool


class RoomTypeOut(BaseModel):
    id: int
    external_id: str
    name: str
    category: str
    category_label: str
    capacity: int
    units_total: int
    is_active: bool
    physical_rooms: list[PhysicalRoomOut] = []


class PropertyOut(BaseModel):
    id: int
    external_id: str
    name: str
    city: str
    district: str
    currency: str
    room_types: list[RoomTypeOut] = []


# ---------------------------------------------------------------- rate book
class RateBandOut(BaseModel):
    id: int
    season_key: str
    season_label: str
    months: list[int]
    room_category: str
    room_category_label: str
    min_net_rate: float
    base_net_rate: float
    max_net_rate: float
    currency: str
    rate_basis: str
    source: str
    note: str | None = None


class RateBandUpdateIn(BaseModel):
    min_net_rate: float = Field(gt=0)
    base_net_rate: float = Field(gt=0)
    max_net_rate: float = Field(gt=0)


# ----------------------------------------------------------- recommendations
class ConfigProblemOut(BaseModel):
    """A rejected configuration field.

    ``code`` + ``params`` are what the UI renders in the operator's language;
    ``message`` is the English form kept for logs and 422 bodies.
    """

    code: str
    path: str | None = None
    params: dict[str, Any] = {}
    message: str


class AdjustmentOut(BaseModel):
    sequence: int
    code: str
    label: str
    adjustment_pct: float
    factor: float
    price_before: float
    price_after: float
    delta: float
    label_key: str | None = None
    params: dict[str, Any] = {}
    is_neutral: bool
    is_ignored: bool


class DecisionOut(BaseModel):
    id: int
    decision: str
    recommended_net_rate: float
    final_net_rate: float
    previous_net_rate: float
    reason_code: str | None = None
    reason_label: str | None = None
    note: str | None = None
    engine_version: str
    config_version: int
    operator: str
    created_at: datetime


class OutcomeOut(BaseModel):
    id: int
    units_booked: int | None = None
    final_occupancy: float | None = None
    realized_net_rate: float | None = None
    realized_revenue: float | None = None
    cancellations: int | None = None
    is_synthetic: bool
    source: str
    captured_at: datetime
    notes: str | None = None


class RecommendationOut(BaseModel):
    id: int
    run_id: str
    mode: str
    property_id: int
    property_name: str
    room_type_id: int
    room_type_name: str
    room_category: str
    room_category_label: str
    stay_date: date
    day_of_week: str | None = None
    currency: str = "VND"

    # validated rate band
    season_key: str | None = None
    season_label: str | None = None
    band_min_net_rate: float | None = None
    band_base_net_rate: float | None = None
    band_max_net_rate: float | None = None
    rate_band_source: str | None = None

    base_net_rate: float
    current_net_rate: float
    current_ota_price: float | None = None
    #: "published" | "derived_adr" | "last_known_adr" | "unavailable".
    rate_provenance: str = "published"
    net_rate_before_clamp: float
    recommended_net_rate: float
    change_pct: float
    change_abs: float
    total_adjustment_pct: float

    # demand signals
    units_total: int | None = None
    units_sold: int | None = None
    units_available: int | None = None
    occupancy: float | None = None
    days_to_arrival: int | None = None
    expected_occupancy: float | None = None
    pace_gap: float | None = None
    recent_pickup: float | None = None
    pickup_delta: float | None = None

    is_event: bool = False
    event_name: str | None = None
    event_impact_level: str | None = None

    market_price_index: float | None = None
    market_reference_net_rate: float | None = None
    market_confidence: str | None = None
    market_observation_count: int = 0
    market_qualified_count: int = 0
    market_ignored_count: int = 0

    status: str
    engine_version: str
    config_version: int
    created_at: datetime
    missing_signals: list[str] = []
    pace_label_key: str | None = None
    pickup_label_key: str | None = None
    pace_label: str | None = None
    pickup_label: str | None = None
    pace_tone: str | None = None
    unpriced: bool = False
    unpriced_reason: str | None = None
    clamp_applied: str | None = None


class RecommendationDetailOut(RecommendationOut):
    adjustments: list[AdjustmentOut] = []
    decisions: list[DecisionOut] = []
    outcomes: list[OutcomeOut] = []
    features: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class SummaryOut(BaseModel):
    room_types: int
    total_units: int
    upcoming_nights: int
    average_occupancy: float | None
    average_pace_gap: float | None
    pending_recommendations: int
    accepted_recommendations: int
    overridden_recommendations: int
    unpriced_recommendations: int = 0
    average_recommended_change_pct: float
    total_recommendations: int
    currency: str = "VND"
    horizon_start: date | None = None
    horizon_end: date | None = None
    mode: str = "shadow"


class AcceptIn(BaseModel):
    note: str | None = None
    operator: str = "demo-operator"


class OverrideIn(BaseModel):
    final_net_rate: float = Field(gt=0)
    reason_code: str
    note: str | None = None
    operator: str = "demo-operator"


# ------------------------------------------------------------- configuration
class ConfigOut(BaseModel):
    version: int
    label: str
    payload: dict[str, Any]
    is_active: bool
    created_at: datetime
    note: str | None = None


class ConfigIn(BaseModel):
    payload: dict[str, Any]
    label: str = "operator-edit"
    note: str | None = None
    regenerate: bool = True


class PreviewIn(BaseModel):
    payload: dict[str, Any]
    room_type_id: int | None = None
    stay_date: date | None = None


class PreviewOut(BaseModel):
    # Field-level problems with the UNSAVED config. Reported rather than raised,
    # so a half-finished edit shows guidance instead of a blank panel.
    problems: list[ConfigProblemOut] = []
    room_type_id: int
    room_type_name: str
    room_category_label: str
    stay_date: date
    currency: str
    season_label: str | None = None
    # The CODES as well as the labels. The labels are English in every locale --
    # they are what the preview header used, so it read "2BR Regular · High
    # Season 1" above a breakdown written in Vietnamese. The frontend looks the
    # code up in its own message file (D30); the labels stay for logs and for a
    # caller that has no catalogue.
    room_category: str | None = None
    season_key: str | None = None
    band_min_net_rate: float | None = None
    band_base_net_rate: float | None = None
    band_max_net_rate: float | None = None
    base_net_rate: float
    current_net_rate: float
    recommended_net_rate: float
    change_pct: float
    total_adjustment_pct: float
    adjustments: list[AdjustmentOut]
    engine_version: str


# ------------------------------------------------------------------ bookings
class BookingOut(BaseModel):
    """ONE OCCUPIED UNIT-NIGHT, not a stay.

    This is the whole contract and it is easy to get wrong, so it is stated
    here rather than left to the field names. The mock provider emits exactly
    `units_sold` rows for every (room type, date) -- verified 260/260 groups --
    and FeatureEngine counts one row as one booking ON that date. A row is a
    room that was occupied on one night.

    `nights` is deliberately NOT published. The provider assigns it at random
    per row and nothing consumed it until a calendar tried to draw stay bars
    from it, smearing each unit-night across up to five days and drawing ~3.5x
    the occupancy that exists. It is the field whose NAME caused that, so the
    fix is to withhold it rather than to document it and hope: there is no
    `nights` and no `last_night` here, and no way to re-derive a span from this
    payload at all.

    Real stay ranges need Blue Jay (ASSUMPTIONS U16), like unit assignment.
    """

    id: int
    external_id: str
    room_type_id: int
    room_category: str | None = None
    #: NULL for every seeded booking -- unit assignment needs Blue Jay (U11).
    physical_room_id: int | None = None
    stay_date: date
    guests: int
    net_rate: float
    channel: str
    status: str


# -------------------------------------------------------------------- market
class CompetitorOut(BaseModel):
    id: int
    name: str
    location: str
    comparable_category: str | None = None
    source: str
    source_url: str | None = None
    is_active: bool
    notes: str | None = None
    observation_count: int = 0


class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    location: str = ""
    comparable_category: str | None = None
    source: str = "manual"
    source_url: str | None = None
    notes: str | None = None
    is_active: bool = True


class MarketObservationOut(BaseModel):
    id: int
    property_id: int | None
    room_type_id: int | None
    competitor_id: int | None
    room_type_name: str | None = None
    stay_date: date
    competitor_name: str
    observed_price: float
    currency: str
    room_category: str | None = None
    length_of_stay: int | None = None
    guests: int | None = None
    price_basis: str
    tax_inclusion: str
    fee_inclusion: str
    promotion_status: str
    is_refundable: bool | None = None
    confidence: str
    confidence_reason: str | None = None
    confidence_code: str | None = None
    confidence_gaps: list[str] = []
    source: str
    source_url: str | None = None
    notes: str | None = None
    observed_at: datetime


class MarketObservationIn(BaseModel):
    stay_date: date
    competitor_name: str = Field(min_length=1, max_length=160)
    observed_price: float = Field(gt=0)
    room_type_id: int | None = None
    property_id: int | None = None
    room_category: str | None = None
    length_of_stay: int | None = None
    guests: int | None = None
    price_basis: str = "UNKNOWN"
    tax_inclusion: str = "UNKNOWN"
    fee_inclusion: str = "UNKNOWN"
    promotion_status: str = "UNKNOWN"
    is_refundable: bool | None = None
    source: str = "manual"
    source_url: str | None = None
    notes: str | None = None


class MarketCollectIn(BaseModel):
    stay_date: date
    room_type_id: int | None = None
    property_id: int | None = None


# -------------------------------------------------------------------- events
class EventOut(BaseModel):
    id: int
    property_id: int | None
    name: str
    start_date: date
    end_date: date
    impact_level: str
    adjustment_pct: float | None = None
    event_type: str
    source: str
    notes: str | None = None
    is_active: bool
    created_at: datetime


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date
    impact_level: str = "medium"
    adjustment_pct: float | None = None
    event_type: str = "other"
    source: str = "manual"
    notes: str | None = None
    property_id: int | None = None
    is_active: bool = True


# ------------------------------------------------------------------- history
class HistoryOut(BaseModel):
    id: int
    created_at: datetime
    property_name: str
    room_type_name: str
    room_category_label: str
    # The CODE travels with the label: a label can only be translated if the
    # frontend knows what it was derived from.
    room_category: str | None = None
    stay_date: date
    season_label: str | None = None
    season_key: str | None = None
    decision: str
    recommended_net_rate: float
    final_net_rate: float
    previous_net_rate: float
    difference: float
    difference_pct: float
    reason_code: str | None = None
    reason_label: str | None = None
    note: str | None = None
    engine_version: str
    config_version: int
    operator: str
    currency: str = "VND"


# -------------------------------------------------------------------- system
class ProviderStatusOut(BaseModel):
    name: str
    healthy: bool
    mode: str
    detail: str = ""
    remediation: str = ""
    unresolved_mappings: list[str] = []
    #: Warnings about the DATA, kept separate from mapping gaps: "this snapshot
    #: may still contain guest information" must not render under a heading
    #: about room-type configuration.
    warnings: list[str] = []


class SystemStatusOut(BaseModel):
    api_version: str
    mode: str
    engine: dict[str, Any]
    available_engines: list[dict[str, str]]
    booking_curve: dict[str, Any]
    rate_book: dict[str, Any]
    config_version: int
    config_label: str
    pms: ProviderStatusOut
    market: ProviderStatusOut
    data_provider_setting: str
    market_provider_setting: str
    counts: dict[str, int]
    override_reasons: list[dict[str, str]]
    vocabularies: dict[str, Any]
    outcome_readiness: dict[str, Any]
    demo_mode: bool
    last_run_id: str | None = None
    #: What the last sync could not fully vouch for. Persisted and exposed here
    #: because a finding returned only in a POST response body reaches nobody.
    last_sync_findings: dict[str, Any] = {}
