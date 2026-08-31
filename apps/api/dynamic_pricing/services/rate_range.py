"""Aggregate a date range into the single answer the Rate page shows.

The operator picks a range, sees ONE average per room tier, and accepts once
for every night in it. So every number the drawer shows has to survive being
averaged -- and the breakdown has to keep adding up afterwards, because a
breakdown that does not reconcile with the total above it destroys the only
thing that panel exists to build.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: The engine's own code for the rounding step. The averaged breakdown reuses it
#: rather than inventing a second rounding line, so the drawer keeps rendering
#: one row with one translation key.
ROUNDING_CODE = "rounding"


class SeasonBoundaryCrossed(ValueError):
    """The range covers more than one season, so no single band applies."""


@dataclass(frozen=True)
class Contribution:
    """One explainable step, carried in DONG rather than percent.

    Percentages of different bases do not average meaningfully; dong do.
    """

    code: str
    label: str
    delta: float
    label_key: str | None = None
    is_neutral: bool = False
    is_ignored: bool = False


@dataclass(frozen=True)
class NightlyPrice:
    stay_date: date
    season_key: str
    base_net_rate: float
    recommended_net_rate: float
    current_net_rate: float
    band_min: float
    band_base: float
    band_max: float | None
    units_total: int
    units_sold: int
    priced: bool
    adjustments: tuple[Contribution, ...]
    #: Lead-time view, used to draw the build-up curve for the whole range.
    days_to_arrival: int | None = None
    expected_occupancy: float | None = None
    occupancy: float | None = None
    rate_provenance: str = "published"


@dataclass(frozen=True)
class NightOccupancy:
    stay_date: date
    #: EVERY booking for the night, whether or not its unit is known.
    units_sold: int
    #: Only the bookings that name a physical unit.
    booked_units: frozenset[int]


@dataclass(frozen=True)
class UnitAvailability:
    units: int
    is_exact: bool


def count_units_with_a_free_night(
    *, units_total: int, nights: list[NightOccupancy]
) -> UnitAvailability:
    """How many distinct units have at least one free night in the range.

    Counts UNITS, not unit-nights: a unit free on any night counts once.
    A unit booked every single night does not count at all.
    """
    if not nights:
        return UnitAvailability(units=units_total, is_exact=True)

    # A booking that does not name its room ("Unassigned" on ~29% of real Blue
    # Jay rows) could be sitting in any unit. Attributing only what we can see
    # would report those units as free and OVERSTATE what is sellable.
    if any(n.units_sold > len(n.booked_units) for n in nights):
        # What is provably true regardless of which unit is which: on the night
        # with the most free units, that many DISTINCT units are free, so at
        # least that many have a free night. Erring low costs a missed booking;
        # erring high costs an oversell.
        floor = max(units_total - n.units_sold for n in nights)
        return UnitAvailability(units=max(floor, 0), is_exact=False)

    booked_throughout = set.intersection(*(set(n.booked_units) for n in nights))
    return UnitAvailability(units=units_total - len(booked_throughout), is_exact=True)


@dataclass(frozen=True)
class RangeAggregate:
    start: date
    end: date
    nights: int
    base_net_rate: float
    average_recommended_net_rate: float
    average_current_net_rate: float
    adjustments: tuple[Contribution, ...]
    #: Nights in the range the engine could not price. They are excluded from
    #: every average -- a zero would drag the whole range down -- and surfaced
    #: so "could not price" never renders as "cheap".
    unpriced_nights: int = 0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_range(nights: list[NightlyPrice], *, rounding_increment: int) -> RangeAggregate:
    if not nights:
        raise ValueError("A range needs at least one night to aggregate.")

    seasons = {n.season_key for n in nights}
    if len(seasons) > 1:
        raise SeasonBoundaryCrossed(
            f"This range covers {len(seasons)} seasons ({', '.join(sorted(seasons))}). "
            f"One price cannot sit inside two different validated bands, so the range "
            f"must stop at the season boundary."
        )

    priced = [n for n in nights if n.priced]

    codes: list[str] = []
    for n in priced:
        for c in n.adjustments:
            if c.code not in codes:
                codes.append(c.code)

    averaged: list[Contribution] = []
    for code in codes:
        sample = next(c for n in priced for c in n.adjustments if c.code == code)
        deltas = [
            next((c.delta for c in n.adjustments if c.code == code), 0.0) for n in priced
        ]
        averaged.append(
            Contribution(
                code=code,
                label=sample.label,
                label_key=sample.label_key,
                delta=_mean(deltas),
                is_neutral=sample.is_neutral,
                is_ignored=sample.is_ignored,
            )
        )

    mean_price = _mean([n.recommended_net_rate for n in priced])
    shown = (
        round(mean_price / rounding_increment) * rounding_increment
        if rounding_increment
        else mean_price
    )

    # Rounding the AVERAGE is a second rounding, on top of the per-night one the
    # engine already did. It has to land somewhere visible: left out, the lines
    # fall short of the total by up to one increment and the operator can watch
    # the arithmetic fail. Folding it into the existing rounding row keeps the
    # breakdown reconciling exactly and adds no new row to explain.
    base = _mean([n.base_net_rate for n in priced])
    drift = shown - (base + sum(c.delta for c in averaged))
    if drift:
        for i, c in enumerate(averaged):
            if c.code == ROUNDING_CODE:
                averaged[i] = Contribution(
                    code=c.code,
                    label=c.label,
                    label_key=c.label_key,
                    delta=c.delta + drift,
                    is_neutral=c.is_neutral,
                    is_ignored=c.is_ignored,
                )
                break
        else:
            averaged.append(
                Contribution(
                    code=ROUNDING_CODE,
                    label="Rounding",
                    label_key="adjustments.rounding",
                    delta=drift,
                )
            )

    return RangeAggregate(
        start=min(n.stay_date for n in nights),
        end=max(n.stay_date for n in nights),
        nights=len(nights),
        base_net_rate=base,
        average_recommended_net_rate=shown,
        average_current_net_rate=_mean([n.current_net_rate for n in priced]),
        adjustments=tuple(averaged),
        unpriced_nights=len(nights) - len(priced),
    )
