"""SeasonalRateBook — CLIENT-VALIDATED data.

These tests protect operator-supplied business fact. A failure here means the
system is quoting a rate Luminous never agreed to.
"""

from __future__ import annotations

from datetime import date

import pytest

from dynamic_pricing.pricing.rate_book import (
    CLIENT_RATE_TABLE,
    MONTH_TO_SEASON,
    RATE_BASIS,
    RATE_BOOK_SOURCE,
    ROOM_CATEGORIES,
    SEASONS,
    SeasonalRateBook,
    season_for,
)

# The client's table, restated independently of the implementation.
EXPECTED = {
    ("low_1", "2br_regular"): (1_800_000, 2_000_000, 2_200_000),
    ("low_1", "2br_premium"): (2_000_000, 2_300_000, 2_500_000),
    ("low_1", "3br"): (2_700_000, 2_800_000, 3_200_000),
    ("high_1", "2br_regular"): (2_100_000, 2_300_000, 2_600_000),
    ("high_1", "2br_premium"): (2_400_000, 2_700_000, 2_900_000),
    ("high_1", "3br"): (2_900_000, 3_300_000, 3_500_000),
    ("low_2", "2br_regular"): (1_800_000, 2_100_000, 2_300_000),
    ("low_2", "2br_premium"): (2_000_000, 2_400_000, 2_700_000),
    ("low_2", "3br"): (2_600_000, 2_800_000, 3_000_000),
    ("high_2", "2br_regular"): (2_100_000, 2_500_000, 3_200_000),
    ("high_2", "2br_premium"): (2_500_000, 3_000_000, 3_500_000),
    ("high_2", "3br"): (3_200_000, 3_800_000, 4_300_000),
    ("medium", "2br_regular"): (2_000_000, 2_300_000, 2_500_000),
    ("medium", "2br_premium"): (2_200_000, 2_500_000, 2_700_000),
    ("medium", "3br"): (2_700_000, 3_200_000, 3_500_000),
}


def test_all_fifteen_bands_exist():
    assert len(EXPECTED) == 15
    assert len(CLIENT_RATE_TABLE) == 15
    assert len(SEASONS) * len(ROOM_CATEGORIES) == 15


@pytest.mark.parametrize("key,expected", sorted(EXPECTED.items()))
def test_every_band_matches_the_client_table(key, expected):
    assert CLIENT_RATE_TABLE[key] == expected


@pytest.mark.parametrize(
    "month,season",
    [
        (1, "high_2"), (2, "medium"), (3, "medium"), (4, "medium"),
        (5, "low_1"), (6, "low_1"), (7, "high_1"), (8, "high_1"),
        (9, "low_2"), (10, "low_2"), (11, "high_2"), (12, "high_2"),
    ],
)
def test_every_month_maps_to_the_right_season(month, season):
    assert MONTH_TO_SEASON[month] == season
    assert season_for(date(2026, month, 15)) == season


def test_january_belongs_to_the_november_to_january_high_season():
    """The year-end wrap is the most error-prone part of the table."""
    assert season_for(date(2026, 1, 1)) == "high_2"
    assert season_for(date(2026, 1, 31)) == "high_2"
    assert season_for(date(2027, 1, 15)) == "high_2"

    band = SeasonalRateBook().lookup("3br", date(2026, 1, 15))
    assert (band.min_net_rate, band.base_net_rate, band.max_net_rate) == (
        3_200_000, 3_800_000, 4_300_000,
    )


def test_every_month_is_covered_exactly_once():
    assert len(MONTH_TO_SEASON) == 12
    covered = [m for season in SEASONS for m in season["months"]]
    assert sorted(covered) == list(range(1, 13))


def test_lookup_returns_the_band_for_the_date_and_category():
    rb = SeasonalRateBook()
    for (season_key, category), (lo, base, hi) in EXPECTED.items():
        month = next(s["months"][0] for s in SEASONS if s["key"] == season_key)
        band = rb.lookup(category, date(2026, month, 15))
        assert band.season_key == season_key
        assert (band.min_net_rate, band.base_net_rate, band.max_net_rate) == (lo, base, hi)


def test_bands_are_ordered_min_base_max():
    for (lo, base, hi) in CLIENT_RATE_TABLE.values():
        assert lo <= base <= hi


def test_rates_are_declared_net_and_client_validated():
    assert RATE_BASIS == "NET"
    assert RATE_BOOK_SOURCE == "CLIENT_VALIDATED"
    band = SeasonalRateBook().lookup("2br_regular", date(2026, 9, 10))
    assert band.rate_basis == "NET"
    assert band.source == "CLIENT_VALIDATED"


def test_clamp_reports_which_bound_was_hit():
    band = SeasonalRateBook().lookup("2br_regular", date(2026, 9, 10))
    assert band.clamp(1_000_000) == (1_800_000, "min")
    assert band.clamp(9_000_000) == (2_300_000, "max")
    assert band.clamp(2_100_000) == (2_100_000, None)


def test_unknown_category_returns_no_band():
    assert SeasonalRateBook().lookup("penthouse", date(2026, 9, 10)) is None
