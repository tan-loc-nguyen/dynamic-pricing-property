"""Range aggregation for the Rate page.

The Rate page prices a DATE RANGE, not a single night: the operator picks
1-14 Sep, sees one average per room tier, and accepts once for all fourteen
nights. Everything the drawer shows therefore has to survive being averaged.

The load-bearing property is that the breakdown still ADDS UP. A breakdown
that does not reconcile with the price above it destroys the only thing that
panel exists to build.
"""

from __future__ import annotations

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
