from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dynamic_pricing.features.context import PricingContext  # noqa: E402
from dynamic_pricing.pricing import default_config, get_engine  # noqa: E402
from dynamic_pricing.pricing.rate_book import SeasonalRateBook  # noqa: E402

# A Thursday in Low Season 2 (Sep–Oct). 2BR Regular there is
# MIN 1,800,000 / BASE 2,100,000 / MAX 2,300,000 — wide enough that the
# dynamic layer can move without immediately hitting a clamp.
STAY = date(2026, 9, 10)


@pytest.fixture
def config() -> dict:
    return default_config()


@pytest.fixture
def engine():
    return get_engine("default")


@pytest.fixture
def rate_book() -> SeasonalRateBook:
    return SeasonalRateBook()


def make_context(**overrides) -> PricingContext:
    """A deliberately NEUTRAL baseline context.

    Every dynamic signal lands on 0.0%, so a test that changes one signal
    isolates exactly that signal's effect.
    """
    band = SeasonalRateBook().lookup(
        overrides.get("room_category", "2br_regular"),
        overrides.get("stay_date", STAY),
    )
    base = dict(
        property_id=1,
        property_name="Luminous Luxury Apartments",
        room_type_id=1,
        room_type_name="2BR Regular",
        room_category="2br_regular",
        room_category_label="2BR Regular",
        stay_date=STAY,
        currency="VND",
        season_key=band.season_key,
        season_label=band.season_label,
        band_min_net_rate=band.min_net_rate,
        band_base_net_rate=band.base_net_rate,
        band_max_net_rate=band.max_net_rate,
        rate_band_source=band.source,
        current_net_rate=band.base_net_rate,
        units_total=10,
        units_sold=4,
        units_available=6,
        occupancy=0.40,
        days_to_arrival=30,
        expected_occupancy=0.40,   # exactly on pace -> 0.0%
        pace_gap=0.0,
        recent_pickup=1.0,
        expected_pickup=1.0,
        pickup_delta=0.0,          # as expected -> 0.0%
        day_of_week="thursday",
        is_weekend=False,
        month=STAY.month,
        market_price_index=1.0,
        market_reference_net_rate=band.base_net_rate,
        market_baseline_net_rate=band.base_net_rate,
        market_confidence="HIGH",
        market_observation_count=3,
        market_qualified_count=3,
        market_ignored_count=0,
        missing=(),
    )
    base.update(overrides)
    return PricingContext(**base)
