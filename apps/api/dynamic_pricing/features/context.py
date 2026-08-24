"""PricingContext — the contract between the Feature Engine and any Pricing Engine.

This is the seam that lets a finance team ship their own engine: they consume
this object and never touch the database, PMS adapters, or the UI.

Every signal is Optional. A missing signal is recorded in ``missing`` so an
engine applies a neutral adjustment and *says so*, rather than crashing or
silently pretending the signal was zero.

All monetary fields are **NET rates** unless the name says otherwise.
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
    room_type_id: int
    room_type_name: str
    room_category: str
    room_category_label: str
    stay_date: date
    currency: str = "VND"

    # --- validated rate band (from SeasonalRateBook) --------------------
    season_key: str | None = None
    season_label: str | None = None
    season_note: str | None = None
    band_min_net_rate: float | None = None
    band_base_net_rate: float | None = None
    band_max_net_rate: float | None = None
    rate_band_source: str | None = None

    # --- current state ---------------------------------------------------
    current_net_rate: float = 0.0
    current_ota_price: float | None = None

    # --- inventory / demand ----------------------------------------------
    units_total: int | None = None
    units_sold: int | None = None
    units_available: int | None = None
    occupancy: float | None = None            # on-the-books occupancy

    days_to_arrival: int | None = None
    expected_occupancy: float | None = None   # from the booking curve
    pace_gap: float | None = None             # actual - expected (pp as fraction)
    booking_curve_source: str | None = None
    booking_curve_validated: bool = False

    recent_pickup: float | None = None        # units picked up in the window
    expected_pickup: float | None = None
    pickup_delta: float | None = None         # recent - expected

    avg_booking_lead_time: float | None = None
    historical_occupancy: float | None = None
    historical_avg_net_rate: float | None = None

    # --- calendar ---------------------------------------------------------
    day_of_week: str | None = None
    is_weekend: bool | None = None
    month: int | None = None

    is_event: bool = False
    event_name: str | None = None
    event_impact_level: str | None = None
    event_adjustment_pct: float | None = None

    # --- market -----------------------------------------------------------
    market_reference_net_rate: float | None = None
    market_baseline_net_rate: float | None = None
    market_price_index: float | None = None
    market_confidence: str | None = None
    market_observation_count: int = 0
    market_qualified_count: int = 0       # observations that met the confidence bar
    market_ignored_count: int = 0         # seen but too low-confidence to use
    market_sources: tuple[str, ...] = ()

    # --- provenance --------------------------------------------------------
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def is_missing(self, signal: str) -> bool:
        return signal in self.missing

    def to_dict(self) -> dict[str, Any]:
        """Serialisable snapshot persisted with each recommendation.

        Storing the exact inputs makes a recommendation reproducible even after
        the underlying inventory moves on — the basis for outcome analysis.
        """
        return {
            "property_id": self.property_id,
            "property_name": self.property_name,
            "room_type_id": self.room_type_id,
            "room_type_name": self.room_type_name,
            "room_category": self.room_category,
            "room_category_label": self.room_category_label,
            "stay_date": self.stay_date.isoformat(),
            "currency": self.currency,
            "season_key": self.season_key,
            "season_label": self.season_label,
            "season_note": self.season_note,
            "band_min_net_rate": self.band_min_net_rate,
            "band_base_net_rate": self.band_base_net_rate,
            "band_max_net_rate": self.band_max_net_rate,
            "rate_band_source": self.rate_band_source,
            "current_net_rate": self.current_net_rate,
            "current_ota_price": self.current_ota_price,
            "units_total": self.units_total,
            "units_sold": self.units_sold,
            "units_available": self.units_available,
            "occupancy": self.occupancy,
            "days_to_arrival": self.days_to_arrival,
            "expected_occupancy": self.expected_occupancy,
            "pace_gap": self.pace_gap,
            "booking_curve_source": self.booking_curve_source,
            "booking_curve_validated": self.booking_curve_validated,
            "recent_pickup": self.recent_pickup,
            "expected_pickup": self.expected_pickup,
            "pickup_delta": self.pickup_delta,
            "avg_booking_lead_time": self.avg_booking_lead_time,
            "historical_occupancy": self.historical_occupancy,
            "historical_avg_net_rate": self.historical_avg_net_rate,
            "day_of_week": self.day_of_week,
            "is_weekend": self.is_weekend,
            "month": self.month,
            "is_event": self.is_event,
            "event_name": self.event_name,
            "event_impact_level": self.event_impact_level,
            "event_adjustment_pct": self.event_adjustment_pct,
            "market_reference_net_rate": self.market_reference_net_rate,
            "market_baseline_net_rate": self.market_baseline_net_rate,
            "market_price_index": self.market_price_index,
            "market_confidence": self.market_confidence,
            "market_observation_count": self.market_observation_count,
            "market_qualified_count": self.market_qualified_count,
            "market_ignored_count": self.market_ignored_count,
            "market_sources": list(self.market_sources),
            "missing": list(self.missing),
            "notes": list(self.notes),
        }
