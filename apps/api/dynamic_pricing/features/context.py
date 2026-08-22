"""PricingContext — the contract between the Feature Engine and any Pricing Engine.

This is the seam that lets the finance team ship their own engine later: they
consume this object and never touch the database, the PMS adapters, or the UI.

Every signal is Optional. A missing signal is recorded in ``missing`` so an
engine can apply a neutral factor and *say so* in the explanation, rather than
crashing or silently pretending the signal was 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PricingContext:
    # --- identity -------------------------------------------------------
    property_id: int
    property_name: str
    room_id: int
    room_name: str
    room_type: str
    stay_date: date
    currency: str = "VND"

    # --- commercial guardrails (from the PMS/room record) ---------------
    base_price: float = 0.0
    current_price: float = 0.0
    min_price: float | None = None
    max_price: float | None = None

    # --- demand signals -------------------------------------------------
    units_total: int | None = None
    units_sold: int | None = None
    occupancy: float | None = None

    days_to_checkin: int | None = None
    avg_booking_lead_time: float | None = None

    recent_pickup: float | None = None
    expected_pickup: float | None = None
    booking_pace_index: float | None = None

    historical_occupancy: float | None = None
    historical_avg_price: float | None = None

    # --- calendar signals -----------------------------------------------
    day_of_week: str | None = None
    is_weekend: bool | None = None
    month: int | None = None
    season_label: str | None = None
    is_event: bool = False
    event_name: str | None = None

    # --- market signals --------------------------------------------------
    market_reference_price: float | None = None
    market_baseline_price: float | None = None
    market_price_index: float | None = None
    market_observation_count: int = 0
    market_sources: tuple[str, ...] = ()

    # --- provenance ------------------------------------------------------
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def is_missing(self, signal: str) -> bool:
        return signal in self.missing

    def to_dict(self) -> dict[str, Any]:
        """Serialisable snapshot stored alongside each recommendation.

        Persisting the exact inputs makes a recommendation reproducible even
        after the underlying inventory changes.
        """
        return {
            "property_id": self.property_id,
            "property_name": self.property_name,
            "room_id": self.room_id,
            "room_name": self.room_name,
            "room_type": self.room_type,
            "stay_date": self.stay_date.isoformat(),
            "currency": self.currency,
            "base_price": self.base_price,
            "current_price": self.current_price,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "units_total": self.units_total,
            "units_sold": self.units_sold,
            "occupancy": self.occupancy,
            "days_to_checkin": self.days_to_checkin,
            "avg_booking_lead_time": self.avg_booking_lead_time,
            "recent_pickup": self.recent_pickup,
            "expected_pickup": self.expected_pickup,
            "booking_pace_index": self.booking_pace_index,
            "historical_occupancy": self.historical_occupancy,
            "historical_avg_price": self.historical_avg_price,
            "day_of_week": self.day_of_week,
            "is_weekend": self.is_weekend,
            "month": self.month,
            "season_label": self.season_label,
            "is_event": self.is_event,
            "event_name": self.event_name,
            "market_reference_price": self.market_reference_price,
            "market_baseline_price": self.market_baseline_price,
            "market_price_index": self.market_price_index,
            "market_observation_count": self.market_observation_count,
            "market_sources": list(self.market_sources),
            "missing": list(self.missing),
            "notes": list(self.notes),
        }
