from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dynamic_pricing.features.context import PricingContext  # noqa: E402
from dynamic_pricing.pricing import default_config, get_engine  # noqa: E402

STAY = date(2026, 9, 10)  # a Thursday -> weekday factor 1.00, keeps maths readable


@pytest.fixture
def config() -> dict:
    return default_config()


@pytest.fixture
def engine():
    return get_engine("v1")


def make_context(**overrides) -> PricingContext:
    """A deliberately NEUTRAL baseline context.

    Every factor lands on x1.00, so any test that changes one signal isolates
    exactly that signal's effect.
    """
    base = dict(
        property_id=1,
        property_name="Luminous Test Property",
        room_id=1,
        room_name="Test Studio",
        room_type="Studio",
        stay_date=STAY,
        currency="VND",
        base_price=1_000_000.0,
        current_price=1_000_000.0,
        min_price=500_000.0,
        max_price=5_000_000.0,
        units_total=10,
        units_sold=6,          # 60% -> "Healthy occupancy" x1.00
        occupancy=0.60,
        days_to_checkin=20,    # "Normal lead time" x1.00
        recent_pickup=1.0,
        expected_pickup=1.0,
        booking_pace_index=1.0,  # "On-pace" x1.00
        day_of_week="thursday",  # x1.00
        is_weekend=False,
        month=9,
        is_event=False,
        market_price_index=1.0,
        market_reference_price=1_000_000.0,
        market_baseline_price=1_000_000.0,
        market_observation_count=3,
        missing=(),
    )
    base.update(overrides)
    return PricingContext(**base)


@pytest.fixture
def neutral_config(config) -> dict:
    """Baseline config with September seasonality flattened to 1.00."""
    config["season"]["month_multipliers"]["9"] = 1.00
    return config
