"""Pydantic API schemas (transport only — no business logic)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class RoomOut(BaseModel):
    id: int
    external_id: str
    name: str
    room_type: str
    capacity: int
    units_total: int
    base_price: float
    min_price: float
    max_price: float
    is_active: bool


class PropertyOut(BaseModel):
    id: int
    external_id: str
    name: str
    city: str
    district: str
    currency: str
    rooms: list[RoomOut] = []


class AdjustmentOut(BaseModel):
    sequence: int
    code: str
    label: str
    factor: float
    price_before: float
    price_after: float
    delta: float
    reason: str
    is_neutral: bool


class DecisionOut(BaseModel):
    id: int
    decision: str
    recommended_price: float
    final_price: float
    previous_price: float
    reason_code: str | None = None
    reason_label: str | None = None
    note: str | None = None
    engine_version: str
    config_version: int
    operator: str
    created_at: datetime


class RecommendationOut(BaseModel):
    id: int
    run_id: str
    property_id: int
    property_name: str
    room_id: int
    room_name: str
    room_type: str
    stay_date: date
    day_of_week: str | None = None
    currency: str = "VND"

    base_price: float
    current_price: float
    price_before_bounds: float
    recommended_price: float
    change_pct: float
    change_abs: float
    total_multiplier: float

    occupancy: float | None = None
    units_sold: int | None = None
    units_total: int | None = None
    days_to_checkin: int | None = None
    booking_pace_index: float | None = None
    market_price_index: float | None = None
    market_reference_price: float | None = None
    market_observation_count: int = 0
    is_event: bool = False
    event_name: str | None = None

    status: str
    explanation: str
    engine_version: str
    config_version: int
    created_at: datetime
    missing_signals: list[str] = []


class RecommendationDetailOut(RecommendationOut):
    adjustments: list[AdjustmentOut] = []
    decisions: list[DecisionOut] = []
    features: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class SummaryOut(BaseModel):
    active_rooms: int
    upcoming_nights: int
    average_occupancy: float | None
    pending_recommendations: int
    accepted_recommendations: int
    overridden_recommendations: int
    average_recommended_change_pct: float
    total_recommendations: int
    currency: str = "VND"
    horizon_start: date | None = None
    horizon_end: date | None = None


class AcceptIn(BaseModel):
    note: str | None = None
    operator: str = "demo-operator"


class OverrideIn(BaseModel):
    final_price: float = Field(gt=0)
    reason_code: str
    note: str | None = None
    operator: str = "demo-operator"


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
    room_id: int | None = None
    stay_date: date | None = None


class PreviewOut(BaseModel):
    room_id: int
    room_name: str
    stay_date: date
    currency: str
    base_price: float
    current_price: float
    recommended_price: float
    change_pct: float
    price_before_bounds: float
    adjustments: list[AdjustmentOut]
    explanation: str
    engine_version: str


class MarketObservationOut(BaseModel):
    id: int
    property_id: int | None
    room_id: int | None
    property_name: str | None = None
    room_name: str | None = None
    stay_date: date
    competitor_name: str
    observed_price: float
    currency: str
    source: str
    source_url: str | None = None
    notes: str | None = None
    collected_at: datetime


class MarketObservationIn(BaseModel):
    stay_date: date
    competitor_name: str = Field(min_length=1, max_length=160)
    observed_price: float = Field(gt=0)
    room_id: int | None = None
    property_id: int | None = None
    source: str = "manual"
    source_url: str | None = None
    notes: str | None = None


class MarketCollectIn(BaseModel):
    stay_date: date
    room_id: int | None = None
    property_id: int | None = None


class HistoryOut(BaseModel):
    id: int
    created_at: datetime
    property_name: str
    room_name: str
    stay_date: date
    decision: str
    recommended_price: float
    final_price: float
    previous_price: float
    difference: float
    difference_pct: float
    reason_code: str | None = None
    reason_label: str | None = None
    note: str | None = None
    engine_version: str
    config_version: int
    operator: str
    currency: str = "VND"


class ProviderStatusOut(BaseModel):
    name: str
    healthy: bool
    mode: str
    detail: str = ""
    remediation: str = ""
    unresolved_mappings: list[str] = []


class SystemStatusOut(BaseModel):
    api_version: str
    engine: dict[str, Any]
    available_engines: list[dict[str, str]]
    config_version: int
    config_label: str
    pms: ProviderStatusOut
    market: ProviderStatusOut
    data_provider_setting: str
    market_provider_setting: str
    counts: dict[str, int]
    override_reasons: list[dict[str, str]]
    demo_mode: bool
    last_run_id: str | None = None
