"""THE central home for every provisional business assumption.

=============================================================================
 EVERY NUMBER IN THIS FILE IS UNVALIDATED.
 None of it came from Luminous. It is a demo scaffold chosen to make pricing
 behaviour legible, not to be economically correct.
 Each entry maps to an ID in ASSUMPTIONS.md (A1, A2, ...) for operator review.
=============================================================================

Rules of the road:
  * No pricing constant may live in a React component, API route, SQL query,
    PMS adapter or market adapter. It lives here (or in the persisted
    PricingConfiguration derived from here) and nowhere else.
  * Adding a new factor means adding a key here + a step in the engine, not
    touching the database schema or the UI.
"""

from __future__ import annotations

import copy
from typing import Any

CONFIG_SCHEMA_VERSION = 1

DEMO_DEFAULTS: dict[str, Any] = {
    "schema_version": CONFIG_SCHEMA_VERSION,
    "label": "demo-defaults",
    "currency": "VND",
    # ---------------------------------------------------------------- A1-A4
    "pricing": {
        # Base price normally comes from the room record (which the PMS owns).
        # An operator can pin a global override here for experimentation.
        "base_price_override": None,          # A1
        "min_price_override": None,           # A2
        "max_price_override": None,           # A3
        "rounding_increment": 10_000,         # A4  (VND 10k = smallest tick an operator cares about)
        "rounding_mode": "nearest",           # nearest | up | down
        # Guardrail against multiplier compounding running away. Applied to the
        # PRODUCT of all factors before bounds. A5.
        "global_multiplier_min": 0.70,        # A5
        "global_multiplier_max": 1.60,        # A5
        # Recommendations smaller than this are surfaced as "no change".
        "min_change_pct_to_surface": 0.5,     # A6
    },
    # ---------------------------------------------------------------- A7
    "day_of_week": {
        "enabled": True,
        "multipliers": {
            "monday": 0.95,
            "tuesday": 0.95,
            "wednesday": 0.96,
            "thursday": 1.00,
            "friday": 1.10,
            "saturday": 1.15,
            "sunday": 1.00,
        },
    },
    # ---------------------------------------------------------------- A8
    # Bands are evaluated in order; the first band whose `max` exceeds the
    # observed value wins. `max` is exclusive-ish (uses <) with a final catch-all.
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
    # ---------------------------------------------------------------- A9, A10
    "lead_time": {
        "enabled": True,
        "bands": [
            {"label": "Last minute (0-3 days out)", "max_days": 3, "multiplier": 0.95},
            {"label": "Short lead time (4-7 days out)", "max_days": 7, "multiplier": 0.98},
            {"label": "Normal lead time (8-30 days out)", "max_days": 30, "multiplier": 1.00},
            {"label": "Long lead time (31-60 days out)", "max_days": 60, "multiplier": 1.02},
            {"label": "Far out (60+ days)", "max_days": 3650, "multiplier": 1.00},
        ],
        # Distressed inventory: close to check-in AND still empty -> discount.
        # This is an interaction rule, kept explicit rather than hidden. A10.
        "urgency_discount": {
            "enabled": True,
            "within_days": 7,
            "occupancy_below": 0.50,
            "multiplier": 0.92,
            "label": "Unsold inventory close to check-in",
        },
    },
    # ---------------------------------------------------------------- A11
    # pace_index = bookings picked up in the recent window / expected pickup.
    # 1.0 == exactly on pace.
    "booking_pace": {
        "enabled": True,
        "lookback_days": 7,            # A12 observation window
        "expected_pickup_per_week": 1.0,  # A13 units/week considered "on pace"
        "bands": [
            {"label": "Very weak booking pace", "max": 0.40, "multiplier": 0.94},
            {"label": "Weak booking pace", "max": 0.80, "multiplier": 0.98},
            {"label": "On-pace bookings", "max": 1.30, "multiplier": 1.00},
            {"label": "Strong booking pace", "max": 2.00, "multiplier": 1.05},
            {"label": "Very strong booking pace", "max": 999.0, "multiplier": 1.10},
        ],
    },
    # ---------------------------------------------------------------- A14
    "season": {
        "enabled": True,
        # Month number -> multiplier. Vietnam STR demo shape: peak Dec-Feb.
        "month_multipliers": {
            "1": 1.10, "2": 1.08, "3": 1.00, "4": 1.02, "5": 0.98, "6": 0.96,
            "7": 1.00, "8": 1.00, "9": 0.96, "10": 0.98, "11": 1.02, "12": 1.12,
        },
        "month_labels": {
            "1": "Peak season", "2": "Peak season", "3": "Shoulder season",
            "4": "Shoulder season", "5": "Low season", "6": "Low season",
            "7": "Shoulder season", "8": "Shoulder season", "9": "Low season",
            "10": "Shoulder season", "11": "Shoulder season", "12": "Peak season",
        },
    },
    # ---------------------------------------------------------------- A15
    "event": {
        "enabled": True,
        "multiplier": 1.20,
    },
    # ---------------------------------------------------------------- A16-A18
    "market": {
        "enabled": True,
        # market_factor = 1 + sensitivity * (market_price_index - 1), then clamped.
        # sensitivity 0 = ignore market entirely, 1 = track market one-for-one.
        "sensitivity": 0.50,              # A16
        "min_multiplier": 0.90,           # A17
        "max_multiplier": 1.15,           # A17
        "min_observations": 2,            # A18 below this the signal is untrusted
        "observation_max_age_days": 14,   # A19 stale observations are ignored
    },
}

# Ordered metadata used by the Settings UI and by ASSUMPTIONS.md generation.
FACTOR_ORDER = [
    "day_of_week",
    "occupancy",
    "booking_pace",
    "lead_time",
    "season",
    "event",
    "market",
]


def default_config() -> dict[str, Any]:
    """Return a deep copy so callers can never mutate the module-level default."""
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
