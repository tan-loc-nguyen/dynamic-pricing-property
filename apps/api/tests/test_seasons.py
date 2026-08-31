"""Operator-defined seasons.

A season is a CONTIGUOUS run of whole months (or whole quarters) and the
seasons together cover the year EXACTLY ONCE. That is not tidiness: the Rate
page refuses a date range that crosses a season, so a gap in the year is a hole
the picker cannot describe, and a date belonging to no season has no validated
band and cannot be priced at all.

Enforcing it on save is the same invariant the hardcoded table asserted at
import (`assert len(MONTH_TO_SEASON) == 12`), moved to where edits happen.
"""

from __future__ import annotations

import pytest

from dynamic_pricing.pricing.seasons import PartitionError, validate_partition

VALID = [
    {"key": "low_1", "months": [5, 6]},
    {"key": "high_1", "months": [7, 8]},
    {"key": "low_2", "months": [9, 10]},
    {"key": "high_2", "months": [11, 12, 1]},
    {"key": "medium", "months": [2, 3, 4]},
]


def test_the_client_calendar_is_a_valid_partition():
    validate_partition(VALID)


def test_the_wrapping_season_is_allowed():
    """High Season 2 is Nov-Dec-Jan. Rejecting a wrap would forbid the one
    season Luminous actually operates."""
    validate_partition([{"key": "a", "months": [11, 12, 1]}, {"key": "b", "months": list(range(2, 11))}])


def test_a_month_covered_by_nobody_is_refused():
    """A date in the gap has no band, so it cannot be priced -- and the Rate
    picker cannot say where its range must stop."""
    holed = [dict(s) for s in VALID]
    holed[0] = {"key": "low_1", "months": [5]}  # June now belongs to no season

    with pytest.raises(PartitionError) as exc:
        validate_partition(holed)
    assert "6" in str(exc.value)


def test_a_month_claimed_by_two_seasons_is_refused():
    doubled = [dict(s) for s in VALID]
    doubled[1] = {"key": "high_1", "months": [6, 7, 8]}  # June claimed twice

    with pytest.raises(PartitionError) as exc:
        validate_partition(doubled)
    assert "6" in str(exc.value)


def test_a_season_split_across_the_year_is_refused():
    """[1, 3] is not a run -- it is two seasons wearing one name.

    season_bounds walks a run from its start month, so a broken run would give
    a range that silently swallowed February.
    """
    broken = [{"key": "a", "months": [1, 3]}, {"key": "b", "months": [2] + list(range(4, 13))}]

    with pytest.raises(PartitionError):
        validate_partition(broken)


# --------------------------------------------------- the book's own calendar


def test_a_rate_book_resolves_dates_by_ITS_OWN_season_calendar():
    """The calendar travels WITH the book, never read from a module global.

    `lookup()` used to take its bands from the database and its month-to-season
    mapping from the hardcoded constant. Once an operator can edit seasons,
    those two are different answers: the band table would say September is high
    season while the mapping still said low, and the engine would quote a
    September date from the wrong band without anything failing. A band table
    and a season calendar that can disagree is the same class of bug as a
    predicate with fewer states than the thing it reads.
    """
    from datetime import date

    from dynamic_pricing.pricing.rate_book import SeasonalRateBook

    # A calendar where September is HIGH season, unlike the client default.
    calendar = [
        {"key": "high_1", "label": "High", "months": [7, 8, 9]},
        {"key": "low_1", "label": "Low", "months": [10, 11, 12, 1, 2, 3, 4, 5, 6]},
    ]
    book = SeasonalRateBook(
        {("high_1", "2br_regular"): (2_100_000, 2_300_000, 2_600_000),
         ("low_1", "2br_regular"): (1_800_000, 2_000_000, 2_200_000)},
        seasons=calendar,
    )

    band = book.lookup("2br_regular", date(2026, 9, 14))

    assert band is not None
    assert band.season_key == "high_1"
    assert band.base_net_rate == 2_300_000


def test_the_default_rate_book_still_uses_the_client_calendar():
    """No calendar supplied means the validated one, unchanged."""
    from datetime import date

    from dynamic_pricing.pricing.rate_book import SeasonalRateBook

    band = SeasonalRateBook().lookup("2br_regular", date(2026, 9, 14))

    assert band is not None and band.season_key == "low_2"


# ------------------------------------------------------------- optional MAX


def test_a_band_with_no_ceiling_does_not_clamp_upwards():
    """MAX is optional: an empty one means the season has no ceiling of its own.

    That is NOT unbounded. The dynamic layer is already capped at the bound in
    Strategy, so `base x (1 + bound)` is the real ceiling -- but the BAND stops
    imposing one, which is the whole point of leaving it blank.
    """
    from dynamic_pricing.pricing.rate_book import RateBand

    band = RateBand(
        season_key="low_2",
        season_label="Low 2",
        room_category="2br_regular",
        min_net_rate=1_800_000,
        base_net_rate=2_100_000,
        max_net_rate=None,
    )

    value, applied = band.clamp(9_000_000)

    assert value == 9_000_000
    assert applied is None


def test_a_band_with_no_ceiling_still_enforces_its_floor():
    """MIN stays required, so the floor is untouched by an empty MAX."""
    from dynamic_pricing.pricing.rate_book import RateBand

    band = RateBand(
        season_key="low_2",
        season_label="Low 2",
        room_category="2br_regular",
        min_net_rate=1_800_000,
        base_net_rate=2_100_000,
        max_net_rate=None,
    )

    assert band.clamp(1_000_000) == (1_800_000, "min")


def test_saving_a_band_with_no_ceiling_keeps_it_empty():
    """`float(None)` would crash; a silent 0.0 would be a ceiling of zero.

    Both are worse than the honest answer, and a ceiling of zero would clamp
    every recommendation for that season down to nothing.
    """
    from dynamic_pricing.services.rate_book import _coerce_ceiling

    assert _coerce_ceiling(None) is None
    assert _coerce_ceiling("") is None
    assert _coerce_ceiling(2_600_000) == 2_600_000.0
