"""Load a date range out of the database and hand it to the aggregator.

The Rate page asks one question -- "what should I charge for this tier over
these nights?" -- so this assembles exactly what answers it and nothing else.
All the arithmetic lives in ``rate_range``; this is the part that talks to the
database.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..constants import STATUS_ERROR
from ..models import (
    Booking,
    PricingRecommendation,
    RoomType,
    StayDateInventory,
)
from .rate_range import (
    Contribution,
    NightlyPrice,
    NightOccupancy,
    RangeAggregate,
    UnitAvailability,
    aggregate_range,
    count_units_with_a_free_night,
)
from .recommendations import latest_run_id
from .seasons import season_on


class RangeCrossesSeason(ValueError):
    """The requested range does not sit inside a single season."""


@dataclass(frozen=True)
class Tile:
    room_type_id: int
    room_type_name: str
    room_category: str
    units_total: int
    availability: UnitAvailability
    aggregate: RangeAggregate


def check_one_season(session: Session, start: date, end: date) -> None:
    """A range must sit inside ONE season, or no single band applies.

    Read from the PERSISTED calendar, so an operator who redraws the year moves
    this guard with it. Compared on BOUNDS rather than on the season key, so
    the wrapping Nov-Dec-Jan season is one continuous stretch: 20 Dec to 5 Jan
    is a legitimate range, while 25 Oct to 5 Nov is not.
    """
    if end < start:
        raise ValueError("The end of the range cannot fall before its start.")
    first, last = season_on(session, start), season_on(session, end)
    if (first["start"], first["end"]) != (last["start"], last["end"]):
        raise RangeCrossesSeason(
            f"This range crosses a season boundary ({first['label']} into {last['label']}). "
            f"One price cannot sit inside two different validated bands, so the range has "
            f"to stop at the boundary."
        )


def _nightly_prices(rows: list[PricingRecommendation]) -> list[NightlyPrice]:
    return [
        NightlyPrice(
            stay_date=r.stay_date,
            season_key=r.season_key or "",
            base_net_rate=r.base_net_rate,
            recommended_net_rate=r.recommended_net_rate,
            current_net_rate=r.current_net_rate,
            band_min=r.band_min_net_rate or 0.0,
            band_base=r.band_base_net_rate or 0.0,
            band_max=r.band_max_net_rate,
            units_total=(r.features or {}).get("units_total", 0),
            units_sold=(r.features or {}).get("units_sold", 0),
            priced=r.status != STATUS_ERROR,
            days_to_arrival=(r.features or {}).get("days_to_arrival"),
            expected_occupancy=(r.features or {}).get("expected_occupancy"),
            occupancy=(r.features or {}).get("occupancy"),
            rate_provenance=(r.features or {}).get("rate_provenance") or "published",
            adjustments=tuple(
                Contribution(
                    code=a.code,
                    label=a.label,
                    label_key=a.label_key,
                    delta=a.delta,
                    is_neutral=a.is_neutral,
                    is_ignored=a.is_ignored,
                )
                for a in sorted(r.adjustments, key=lambda a: a.sequence)
            ),
        )
        for r in sorted(rows, key=lambda r: r.stay_date)
    ]


def load_range(
    session: Session, *, room_type_id: int, start: date, end: date, rounding_increment: int
) -> tuple[RangeAggregate, list[NightlyPrice], UnitAvailability, RoomType | None]:
    """One tier over one range: the drawer's whole payload.

    Returns the aggregate AND the individual nights, because the drawer shows
    both -- the averaged breakdown the operator accepts, and the per-night
    strip that reveals a range whose nights disagree with each other.
    """
    check_one_season(session, start, end)

    run_id = latest_run_id(session)
    rows = (
        list(
            session.scalars(
                select(PricingRecommendation)
                .where(
                    PricingRecommendation.run_id == run_id,
                    PricingRecommendation.room_type_id == room_type_id,
                    PricingRecommendation.stay_date >= start,
                    PricingRecommendation.stay_date <= end,
                )
                .options(selectinload(PricingRecommendation.adjustments))
            ).all()
        )
        if run_id
        else []
    )
    room_type = session.get(RoomType, room_type_id)
    nights = _nightly_prices(rows)
    occupancy = _occupancy_by_room_type(session, start=start, end=end).get(room_type_id, [])
    availability = count_units_with_a_free_night(
        units_total=room_type.units_total if room_type else 0, nights=occupancy
    )
    aggregate = (
        aggregate_range(nights, rounding_increment=rounding_increment) if nights else None
    )
    return aggregate, nights, availability, room_type


def load_tiles(session: Session, *, start: date, end: date, rounding_increment: int) -> list[Tile]:
    check_one_season(session, start, end)

    run_id = latest_run_id(session)
    if not run_id:
        return []

    recs = list(
        session.scalars(
            select(PricingRecommendation)
            .where(
                PricingRecommendation.run_id == run_id,
                PricingRecommendation.stay_date >= start,
                PricingRecommendation.stay_date <= end,
            )
            .options(selectinload(PricingRecommendation.adjustments))
        ).all()
    )
    by_room_type: dict[int, list[PricingRecommendation]] = defaultdict(list)
    for r in recs:
        by_room_type[r.room_type_id].append(r)

    room_types = {
        rt.id: rt
        for rt in session.scalars(select(RoomType).where(RoomType.is_active.is_(True))).all()
    }
    occupancy = _occupancy_by_room_type(session, start=start, end=end)

    tiles: list[Tile] = []
    for room_type_id, rows in by_room_type.items():
        rt = room_types.get(room_type_id)
        if rt is None:
            continue
        tiles.append(
            Tile(
                room_type_id=room_type_id,
                room_type_name=rt.name,
                room_category=rt.category,
                units_total=rt.units_total,
                availability=count_units_with_a_free_night(
                    units_total=rt.units_total, nights=occupancy.get(room_type_id, [])
                ),
                aggregate=aggregate_range(
                    _nightly_prices(rows), rounding_increment=rounding_increment
                ),
            )
        )
    return sorted(tiles, key=lambda t: t.room_category)


def _occupancy_by_room_type(
    session: Session, *, start: date, end: date
) -> dict[int, list[NightOccupancy]]:
    """Per night: how many units are sold, and which of them we can name.

    ``units_sold`` is the PMS's own count and includes bookings whose room was
    never assigned. ``booked_units`` holds only the ones we can attribute, and
    the gap between the two is what makes an availability count inexact.
    """
    sold = {
        (row.room_type_id, row.stay_date): row.units_sold
        for row in session.scalars(
            select(StayDateInventory).where(
                StayDateInventory.stay_date >= start, StayDateInventory.stay_date <= end
            )
        ).all()
    }
    attributed: dict[tuple[int, date], set[int]] = defaultdict(set)
    for b in session.scalars(
        select(Booking).where(
            Booking.stay_date >= start,
            Booking.stay_date <= end,
            Booking.status != "cancelled",
        )
    ).all():
        if b.physical_room_id is not None:
            attributed[(b.room_type_id, b.stay_date)].add(b.physical_room_id)

    out: dict[int, list[NightOccupancy]] = defaultdict(list)
    for (room_type_id, stay_date), units_sold in sold.items():
        out[room_type_id].append(
            NightOccupancy(
                stay_date=stay_date,
                units_sold=units_sold,
                booked_units=frozenset(attributed.get((room_type_id, stay_date), set())),
            )
        )
    return out
