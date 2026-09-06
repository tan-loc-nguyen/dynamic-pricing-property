"""Range aggregation for the Rate page.

The Rate page prices a DATE RANGE, not a single night: the operator picks
1-14 Sep, sees one average per room tier, and accepts once for all fourteen
nights. Everything the drawer shows therefore has to survive being averaged.

The load-bearing property is that the breakdown still ADDS UP. A breakdown
that does not reconcile with the price above it destroys the only thing that
panel exists to build.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from dynamic_pricing.services.rate_range import (
    Contribution,
    NightOccupancy,
    NightlyPrice,
    SeasonBoundaryCrossed,
    count_units_with_a_free_night,
    aggregate_range,
)


def night(
    day: int,
    *,
    recommended: float,
    contributions: tuple[tuple[str, float], ...],
    base: float = 2_000_000.0,
    current: float = 2_100_000.0,
    season: str = "low_2",
    units_total: int = 8,
    units_sold: int = 3,
    priced: bool = True,
) -> NightlyPrice:
    return NightlyPrice(
        stay_date=date(2026, 9, day),
        season_key=season,
        base_net_rate=base,
        recommended_net_rate=recommended,
        current_net_rate=current,
        band_min=1_800_000.0,
        band_base=base,
        band_max=2_300_000.0,
        units_total=units_total,
        units_sold=units_sold,
        priced=priced,
        adjustments=tuple(
            Contribution(code=code, label_key=f"adjustments.{code}", label=code, delta=delta)
            for code, delta in contributions
        ),
    )


def test_the_averaged_breakdown_sums_to_the_averaged_price():
    """base + every averaged contribution == the price the operator is shown.

    Averaging is linear, so this holds exactly -- but only if the rounding of
    the AVERAGE is itself folded back into the rounding line. Without that the
    displayed lines fall short of the displayed total by up to one increment,
    and the operator can see the arithmetic fail.
    """
    nights = [
        night(1, recommended=2_050_000, contributions=(("pace", 40_000), ("rounding", 10_000))),
        night(2, recommended=1_990_000, contributions=(("pace", -20_000), ("rounding", 10_000))),
        night(3, recommended=2_030_000, contributions=(("pace", 30_000), ("rounding", 0))),
    ]

    agg = aggregate_range(nights, rounding_increment=10_000)

    total = agg.base_net_rate + sum(c.delta for c in agg.adjustments)
    assert total == pytest.approx(agg.average_recommended_net_rate), (
        f"breakdown sums to {total:,.2f} but the operator is shown "
        f"{agg.average_recommended_net_rate:,.2f}"
    )


def test_a_range_that_spans_two_seasons_is_refused():
    """One accepted price cannot be right for two bands.

    The picker greys out dates past the season's end, but a UI guard is not an
    invariant -- it is a convenience. If a range with two seasons ever reaches
    here, the band is ambiguous and a single price could be written OUTSIDE the
    validated band of one of them, which is the one thing the engine promises
    never happens.
    """
    nights = [
        night(30, recommended=2_050_000, contributions=(("pace", 50_000),), season="low_2"),
        night(1, recommended=2_050_000, contributions=(("pace", 50_000),), season="high_2"),
    ]

    with pytest.raises(SeasonBoundaryCrossed):
        aggregate_range(nights, rounding_increment=10_000)


def test_a_night_that_could_not_be_priced_is_excluded_from_the_average_and_counted():
    """Zero is not a neutral price.

    An unpriced night carries recommended_net_rate 0. Averaged in, it drags the
    whole range DOWN -- and under bulk accept that wrong number gets written to
    every night in the range without anyone seeing the one that failed. So it
    leaves the average AND it gets counted, because "we could not price this"
    and "this is cheap" must never look the same.
    """
    nights = [
        night(1, recommended=2_000_000, contributions=(("pace", 0),)),
        night(2, recommended=2_000_000, contributions=(("pace", 0),)),
        night(3, recommended=0, contributions=(), priced=False),
    ]

    agg = aggregate_range(nights, rounding_increment=10_000)

    assert agg.average_recommended_net_rate == 2_000_000, "an unpriced night dragged the average"
    assert agg.unpriced_nights == 1
    assert agg.nights == 3


# --------------------------------------------------------------- inventory
#
# The tile counts UNITS, not unit-nights: a unit with at least one free night
# in the range counts once. Which unit is free is only knowable when a booking
# names its room -- Blue Jay leaves `roomName` as "Unassigned" on roughly a
# third of real rows -- so this has three states, not two: known free, known
# booked throughout, and not attributable.


def occupancy(day: int, *, sold: int, booked_units: set[int]) -> NightOccupancy:
    return NightOccupancy(
        stay_date=date(2026, 9, day), units_sold=sold, booked_units=frozenset(booked_units)
    )


def test_a_unit_free_on_any_night_is_counted_once():
    """Not once per free night -- once, for the whole range.

    Unit 1 is booked on the 1st and free on the 2nd; unit 2 is the reverse.
    Both have a free night, so both count, and the answer is 3 of 3 rather
    than the 4 free unit-nights across the range.
    """
    nights = [
        occupancy(1, sold=1, booked_units={1}),
        occupancy(2, sold=1, booked_units={2}),
    ]

    result = count_units_with_a_free_night(units_total=3, nights=nights)

    assert result.units == 3
    assert result.is_exact is True


def test_a_unit_booked_every_night_of_the_range_is_not_counted():
    nights = [
        occupancy(1, sold=2, booked_units={1, 2}),
        occupancy(2, sold=2, booked_units={1, 3}),
    ]

    result = count_units_with_a_free_night(units_total=3, nights=nights)

    assert result.units == 2, "unit 1 is booked on both nights and has no free night"
    assert result.is_exact is True


def test_unassigned_bookings_never_let_the_count_overstate_availability():
    """Counting only the bookings that name a room reports units as free that
    are not.

    Night 1 has all three units sold, but only one booking names its room --
    Blue Jay leaves the other two "Unassigned". Attributing only what we can
    see, no unit looks booked-throughout, and the tile would claim all 3 are
    sellable on a night that is completely full.

    So when a night carries bookings we cannot attribute, the answer falls back
    to what is provably true -- the most units free on any single night -- and
    says it is not exact. Erring LOW is the safe direction: telling an operator
    they have less to sell than they do costs a missed booking, telling them
    they have more costs an oversell.
    """
    nights = [
        occupancy(1, sold=3, booked_units={1}),
        occupancy(2, sold=1, booked_units={2}),
    ]

    result = count_units_with_a_free_night(units_total=3, nights=nights)

    assert result.units == 2, "the fully-sold night proves at most 2 units are free somewhere"
    assert result.is_exact is False


# ------------------------------------------------- averaging the breakdown
#
# A code is not a narrative. `pace` alone carries six different label_keys --
# well_behind, behind, on_pace, ahead, well_ahead, unavailable -- and a range
# can contain several of them. Collapsing on `code` and keeping whichever
# label the first night happened to have states one of them as though it
# described the whole range.


def contribution(code: str, label_key: str, delta: float, **params) -> Contribution:
    return Contribution(
        code=code, label=code, label_key=label_key, delta=delta, params=params
    )


def night_with(day: int, *, recommended: float, contributions: tuple[Contribution, ...]):
    return NightlyPrice(
        stay_date=date(2026, 9, day),
        season_key="low_2",
        base_net_rate=2_000_000.0,
        recommended_net_rate=recommended,
        current_net_rate=2_100_000.0,
        band_min=1_800_000.0,
        band_base=2_000_000.0,
        band_max=2_300_000.0,
        units_total=8,
        units_sold=3,
        priced=True,
        adjustments=contributions,
    )


def test_nights_that_tell_different_stories_get_separate_lines():
    """Four nights behind pace and two on pace are two facts, not one."""
    nights = [
        night_with(d, recommended=1_940_000, contributions=(
            contribution("pace", "adjustments.pace.behind", -60_000, gap_pp=-12),
        ))
        for d in (1, 2)
    ] + [
        night_with(3, recommended=2_000_000, contributions=(
            contribution("pace", "adjustments.pace.on_pace", 0.0, gap_pp=1),
        ))
    ]

    agg = aggregate_range(nights, rounding_increment=10_000)

    keys = [c.label_key for c in agg.adjustments if c.code == "pace"]
    assert sorted(keys) == ["adjustments.pace.behind", "adjustments.pace.on_pace"]


def test_separate_lines_still_sum_to_the_price_shown():
    """Splitting the narrative must not break the arithmetic: each line's delta
    is its share of the WHOLE range, not an average of its own nights."""
    nights = [
        night_with(d, recommended=1_940_000, contributions=(
            contribution("pace", "adjustments.pace.behind", -60_000, gap_pp=-12),
        ))
        for d in (1, 2)
    ] + [
        night_with(3, recommended=2_000_000, contributions=(
            contribution("pace", "adjustments.pace.on_pace", 0.0, gap_pp=1),
        ))
    ]

    agg = aggregate_range(nights, rounding_increment=10_000)

    total = agg.base_net_rate + sum(c.delta for c in agg.adjustments)
    assert total == pytest.approx(agg.average_recommended_net_rate)


def test_an_averaged_line_carries_the_params_its_message_needs():
    """The engine emits a message KEY plus the numbers it interpolates (D30).

    Dropping the params leaves a key whose placeholders nothing fills -- ICU
    refuses the whole message, so the operator gets no explanation at all. It
    also crashed the drawer outright, because the renderer reads them.
    """
    nights = [
        night_with(1, recommended=1_940_000, contributions=(
            contribution("pace", "adjustments.pace.behind", -60_000, gap_pp=-20, occupancy=0.4),
        )),
        night_with(2, recommended=1_980_000, contributions=(
            contribution("pace", "adjustments.pace.behind", -20_000, gap_pp=-10, occupancy=0.6),
        )),
    ]

    agg = aggregate_range(nights, rounding_increment=10_000)
    line = next(c for c in agg.adjustments if c.code == "pace")

    assert line.params["gap_pp"] == pytest.approx(-15), "numbers average across the range"
    assert line.params["occupancy"] == pytest.approx(0.5)


def test_the_loader_carries_params_off_the_stored_adjustment():
    """The dataclass having a `params` field is not the same as it being filled.

    It was added and left unpopulated, so every averaged line arrived with an
    empty dict: the message key survived, the numbers it interpolates did not,
    and ICU refuses a message whose arguments are missing.
    """
    from dynamic_pricing.services.rate_page import _nightly_prices

    class FakeAdjustment:
        code, label, label_key = "pace", "Behind", "adjustments.pace.behind"
        delta, sequence, is_neutral, is_ignored = -60_000.0, 1, False, False
        params = {"gap_pp": -12, "occupancy": 0.4}

    class FakeRec:
        stay_date = date(2026, 9, 1)
        season_key = "low_2"
        base_net_rate = current_net_rate = 2_000_000.0
        recommended_net_rate = 1_940_000.0
        band_min_net_rate, band_base_net_rate, band_max_net_rate = 1.8e6, 2e6, 2.3e6
        net_rate_before_clamp = 1_940_000.0
        status = "pending"
        features: dict = {}
        adjustments = [FakeAdjustment()]

    nights = _nightly_prices([FakeRec()])

    assert nights[0].adjustments[0].params == {"gap_pp": -12, "occupancy": 0.4}


def test_folding_the_rounding_drift_does_not_discard_its_params():
    """The rounding line is REBUILT to absorb the average's own rounding.

    Rebuilding it by hand dropped the params on the way through, so the one
    line guaranteed to be touched was also the one guaranteed to lose its
    numbers -- and `adjustments.rounding` interpolates {increment}.
    """
    nights = [
        night_with(1, recommended=2_050_000, contributions=(
            contribution("rounding", "adjustments.rounding", 10_000, increment=10_000),
        )),
        night_with(2, recommended=1_990_000, contributions=(
            contribution("rounding", "adjustments.rounding", 10_000, increment=10_000),
        )),
        night_with(3, recommended=2_030_000, contributions=(
            contribution("rounding", "adjustments.rounding", 0, increment=10_000),
        )),
    ]

    agg = aggregate_range(nights, rounding_increment=10_000)
    rounding = next(c for c in agg.adjustments if c.code == "rounding")

    assert rounding.params == {"increment": 10_000}


def test_each_averaged_row_reports_how_many_nights_it_covers():
    """A row that describes 2 of 7 nights must say so.

    Grouping is by (code, label_key), so one factor can produce several rows.
    Without a night count the operator reads any one of them as describing the
    whole range -- which is the defect this field exists to fix.
    """
    nights = [
        night(1, recommended=2_000_000, contributions=(("pace", 0),)),
        night(2, recommended=2_000_000, contributions=(("pace", 0),)),
        night(3, recommended=2_000_000, contributions=(("pace", 0),)),
    ]
    # Give night 3 a different label_key for the same code, so the group splits.
    nights[2] = replace(
        nights[2],
        adjustments=(
            Contribution(
                code="pace",
                label_key="adjustments.pace.well_behind",
                label="pace",
                delta=0.0,
            ),
        ),
    )
    result = aggregate_range(nights, rounding_increment=0)
    covered = {c.label_key: c.nights_covered for c in result.adjustments}
    assert covered["adjustments.pace"] == 2
    assert covered["adjustments.pace.well_behind"] == 1


def test_an_unpriced_night_is_not_counted_in_any_row():
    """Unpriced nights are excluded from every average, so they cannot be
    counted as covered by a row they never contributed to."""
    nights = [
        night(1, recommended=2_000_000, contributions=(("pace", 0),)),
        night(2, recommended=0, contributions=(), priced=False),
    ]
    result = aggregate_range(nights, rounding_increment=0)
    pace = next(c for c in result.adjustments if c.code == "pace")
    assert pace.nights_covered == 1
    assert result.unpriced_nights == 1


def test_a_single_night_row_covers_one_night():
    """The identity case. Night mode accepts one night as a range of length
    one, so this must not report the whole range."""
    result = aggregate_range(
        [night(1, recommended=2_000_000, contributions=(("pace", 0),))],
        rounding_increment=0,
    )
    assert all(c.nights_covered == 1 for c in result.adjustments)


def test_a_synthesised_rounding_row_reports_the_whole_range():
    """When no night carried a rounding line, aggregate_range invents one to
    absorb the drift from rounding the average. That row describes every
    priced night, not one of them -- a default of 1 would be a lie."""
    nights = [
        night(1, recommended=2_000_000, contributions=(("pace", 33_333),)),
        night(2, recommended=2_000_000, contributions=(("pace", 33_333),)),
        night(3, recommended=2_000_000, contributions=(("pace", 33_333),)),
    ]
    result = aggregate_range(nights, rounding_increment=10_000)
    rounding = next(c for c in result.adjustments if c.code == "rounding")
    assert rounding.nights_covered == 3


def test_a_night_is_clamped_when_the_pre_clamp_price_left_the_band():
    """Compared against the BAND, not against the recommended rate: rounding
    moves the recommended rate by up to one increment, which would report a
    clamp that never happened."""
    from dynamic_pricing.services.rate_range import clamp_side

    assert clamp_side(before=2_500_000, band_min=1_800_000, band_max=2_300_000) == "max"
    assert clamp_side(before=1_500_000, band_min=1_800_000, band_max=2_300_000) == "min"
    assert clamp_side(before=2_000_000, band_min=1_800_000, band_max=2_300_000) is None


def test_an_open_ceiling_can_never_clamp_at_the_top():
    """MAX is optional (ASSUMPTIONS U9). An empty ceiling means the only bound
    is the dynamic one, so there is no band edge to hit."""
    from dynamic_pricing.services.rate_range import clamp_side

    assert clamp_side(before=9_000_000, band_min=1_800_000, band_max=None) is None
    assert clamp_side(before=1_000_000, band_min=1_800_000, band_max=None) == "min"
