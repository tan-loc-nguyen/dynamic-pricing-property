"""EXPERIMENTAL dynamic strategy configuration.

=============================================================================
 EVERYTHING IN THIS FILE IS UNVALIDATED.

 The client-validated MIN/BASE/MAX rate table lives in ``rate_book.py`` and is
 deliberately NOT here — validated fact and unvalidated experiment must never
 be mixed in one config blob. This file holds only the *dynamic layer* the
 client asked for on top of their rate table: pace, pickup, events, market.

 Each entry maps to an ID in ASSUMPTIONS.md (U1, U2, ...) for operator review.
=============================================================================

Design rules for this layer:
  * Adjustments are ADDITIVE percentages of the band BASE rate, not stacked
    multipliers — bounded and easy to reason about.
  * Signals must not double-count the same demand condition. Pace position and
    recent pickup measure different things (level vs. acceleration).
  * Seasonality is NOT here: the rate band already encodes it.
"""

from __future__ import annotations

import copy
from typing import Any

CONFIG_SCHEMA_VERSION = 2

DEMO_DEFAULTS: dict[str, Any] = {
    "schema_version": CONFIG_SCHEMA_VERSION,
    "label": "demo-defaults",
    "currency": "VND",
    # Shadow mode: recommend, never push. The default and only supported mode.
    "mode": "shadow",

    # ------------------------------------------------------------------ U10
    "rounding": {
        "increment": 10_000,
        "mode": "nearest",
    },

    # ---------------------------------------------------------------- U8
    # Hard bound on the whole dynamic layer, applied BEFORE the band clamp.
    "dynamic": {
        "max_total_adjustment_pct": 15.0,
        "min_total_adjustment_pct": -15.0,
    },

    # ---------------------------------------------------------------- U2
    # Pace position: on-the-books occupancy vs the booking curve's expectation.
    # This is the PRIMARY demand signal. Bands are on pace_gap (fraction:
    # 0.10 = 10 percentage points ahead of expectation).
    "pace": {
        "enabled": True,
        "bands": [
            {"label": "Well behind pace", "max_gap": -0.20, "adjustment_pct": -8.0},
            {"label": "Behind pace", "max_gap": -0.08, "adjustment_pct": -4.0},
            {"label": "On pace", "max_gap": 0.08, "adjustment_pct": 0.0},
            {"label": "Ahead of pace", "max_gap": 0.20, "adjustment_pct": 4.0},
            {"label": "Well ahead of pace", "max_gap": 99.0, "adjustment_pct": 8.0},
        ],
    },

    # ---------------------------------------------------------------- U3
    # Recent pickup: booking ACCELERATION over the last window. Distinct from
    # pace position, which is a level. Kept small so it cannot dominate.
    "recent_pickup": {
        "enabled": True,
        "lookback_days": 7,
        "expected_pickup_per_week": 1.0,
        "bands": [
            {"label": "Pickup stalled", "max_delta": -1.0, "adjustment_pct": -3.0},
            {"label": "Pickup slowing", "max_delta": -0.25, "adjustment_pct": -1.5},
            {"label": "Pickup as expected", "max_delta": 0.5, "adjustment_pct": 0.0},
            {"label": "Pickup accelerating", "max_delta": 2.0, "adjustment_pct": 2.0},
            {"label": "Pickup surging", "max_delta": 999.0, "adjustment_pct": 4.0},
        ],
    },

    # ---------------------------------------------------------------- U4
    "event": {
        "enabled": True,
        "impact_adjustment_pct": {
            "low": 3.0,
            "medium": 8.0,
            "high": 15.0,
        },
    },

    # ---------------------------------------------------------------- U5, U6
    "market": {
        "enabled": True,
        # Only observations at or above this confidence can move a price.
        # HIGH | MEDIUM | LOW  — LOW effectively disables the gate.
        "min_confidence": "MEDIUM",
        "min_observations": 2,
        "observation_max_age_days": 14,
        # adjustment_pct = sensitivity * (market_index - 1) * 100, then capped.
        "sensitivity": 0.50,
        "max_adjustment_pct": 5.0,
    },

    # ---------------------------------------------------------------- U7
    # OFF by default: the client has not confirmed any weekday pattern, and
    # the seasonal table shows no day-of-week structure at all.
    "day_of_week": {
        "enabled": False,
        "adjustment_pct": {
            "monday": 0.0,
            "tuesday": 0.0,
            "wednesday": 0.0,
            "thursday": 0.0,
            "friday": 0.0,
            "saturday": 0.0,
            "sunday": 0.0,
        },
    },

    # ---------------------------------------------------------------- U1
    # Booking curve shape. See features/booking_curve.py — UNVALIDATED.
    "booking_curve": {
        "provider": "demo",
        "anchors": None,        # null = module defaults
        "season_pace": None,
        "category_pace": None,
    },

    # ------------------------------------------------------------------
    # Legacy PricingEngineV1 configuration, isolated so it cannot leak into
    # V2. V1 is kept registered to prove the engine registry still works.
    # Its seasonality factor has been REMOVED (the rate band owns season).
    "legacy_v1": {
        "pricing": {
            "rounding_increment": 10_000,
            "rounding_mode": "nearest",
            "global_multiplier_min": 0.70,
            "global_multiplier_max": 1.60,
        },
        "day_of_week": {
            "enabled": False,
            "multipliers": {
                "monday": 1.0, "tuesday": 1.0, "wednesday": 1.0, "thursday": 1.0,
                "friday": 1.0, "saturday": 1.0, "sunday": 1.0,
            },
        },
        "occupancy": {
            "enabled": True,
            "bands": [
                {"label": "Very low occupancy", "max": 0.30, "multiplier": 0.92},
                {"label": "Low occupancy", "max": 0.50, "multiplier": 0.97},
                {"label": "Healthy occupancy", "max": 0.70, "multiplier": 1.00},
                {"label": "High occupancy", "max": 0.85, "multiplier": 1.08},
                {"label": "Very high occupancy", "max": 1.01, "multiplier": 1.15},
            ],
        },
        "lead_time": {
            "enabled": True,
            "bands": [
                {"label": "Last minute (0-3 days out)", "max_days": 3, "multiplier": 0.95},
                {"label": "Short lead time (4-7 days out)", "max_days": 7, "multiplier": 0.98},
                {"label": "Normal lead time (8-30 days out)", "max_days": 30, "multiplier": 1.00},
                {"label": "Long lead time (31-60 days out)", "max_days": 60, "multiplier": 1.02},
                {"label": "Far out (60+ days)", "max_days": 3650, "multiplier": 1.00},
            ],
            "urgency_discount": {
                "enabled": True,
                "within_days": 7,
                "occupancy_below": 0.50,
                "multiplier": 0.92,
                "label": "Unsold inventory close to check-in",
            },
        },
        "booking_pace": {
            "enabled": True,
            "bands": [
                {"label": "Very weak booking pace", "max": 0.40, "multiplier": 0.94},
                {"label": "Weak booking pace", "max": 0.80, "multiplier": 0.98},
                {"label": "On-pace bookings", "max": 1.30, "multiplier": 1.00},
                {"label": "Strong booking pace", "max": 2.00, "multiplier": 1.05},
                {"label": "Very strong booking pace", "max": 999.0, "multiplier": 1.10},
            ],
        },
        "event": {"enabled": True, "multiplier": 1.20},
        "market": {
            "enabled": True,
            "sensitivity": 0.50,
            "min_multiplier": 0.90,
            "max_multiplier": 1.15,
            "min_observations": 2,
        },
    },
}

# Ordered metadata for the Settings UI. Every entry here is EXPERIMENTAL —
# the validated rate book is served separately.
EXPERIMENTAL_SECTIONS = [
    "pace",
    "recent_pickup",
    "event",
    "market",
    "day_of_week",
    "dynamic",
    "rounding",
    "booking_curve",
]


def default_config() -> dict[str, Any]:
    """Deep copy so callers can never mutate the module-level default."""
    return copy.deepcopy(DEMO_DEFAULTS)


def merge_config(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-merge a partial payload over the demo defaults.

    Guarantees the engine always receives a fully-populated config, so a
    partially-filled Settings form can never crash a pricing run.
    """
    base = default_config()
    if not payload:
        return base
    return _deep_merge(base, payload)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
