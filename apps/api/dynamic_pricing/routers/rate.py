"""The Rate page: a date range in, one tile per room tier out.

Replaces the per-night calendar. The operator picks a range, sees an average
per tier, and accepts once for every night in it -- so the range is the unit of
work here, not the stay date.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..services.seasons import season_on
from ..services.configuration import get_active_configuration
from ..constants import DECISION_ACCEPTED, DECISION_OVERRIDDEN, OVERRIDE_REASON_CODES
from ..services.rate_decisions import apply_to_range
from ..services.rate_page import RangeCrossesSeason, Tile, load_range, load_tiles
from ._shared import category_label

router = APIRouter(prefix="/api/rate", tags=["rate"])


def _mean_pace_gap(nights: list) -> float | None:
    """Mean (actual - expected) occupancy across the range, or None.

    None rather than 0.0 when no night carries a pace reading: zero would say
    the range is exactly on pace, which is a measurement we do not have.
    """
    gaps = [
        n.occupancy - n.expected_occupancy
        for n in nights
        if n.occupancy is not None and n.expected_occupancy is not None
    ]
    return round(sum(gaps) / len(gaps), 4) if gaps else None


def _uniform_provenance(nights: list) -> str:
    seen = {n.rate_provenance for n in nights}
    return seen.pop() if len(seen) == 1 else "mixed"


def _season_payload(session: Session, day: date) -> dict:
    """From the PERSISTED calendar, not the hardcoded one.

    Reading the constant here while the engine reads the database is how the
    picker would let a range cross a boundary the engine had already moved.
    """
    return season_on(session, day)


def _tile_payload(tile: Tile) -> dict:
    agg = tile.aggregate
    current = agg.average_current_net_rate
    return {
        "room_type_id": tile.room_type_id,
        "room_type_name": tile.room_type_name,
        "room_category": tile.room_category,
        "room_category_label": category_label(tile.room_category),
        "units_total": tile.units_total,
        # Units with at least one free night in the range -- NOT unit-nights.
        "available_units": tile.availability.units,
        # False when unassigned bookings mean the count is a provable floor
        # rather than the exact answer. The tile says so rather than rounding
        # the uncertainty away.
        "availability_is_exact": tile.availability.is_exact,
        "average_recommended_net_rate": agg.average_recommended_net_rate,
        "average_current_net_rate": current,
        "change_pct": (
            round((agg.average_recommended_net_rate - current) / current * 100, 2)
            if current
            else 0.0
        ),
        "unpriced_nights": agg.unpriced_nights,
    }


@router.get("/season")
def season_endpoint(on: date = Query(...), session: Session = Depends(get_session)) -> dict:
    """Which season a date falls in, and the days it runs between.

    The Rate picker uses this to stop a range at the boundary: one accepted
    price cannot sit inside two different validated bands. Answered without
    touching the database because seasons are calendar facts, not run data.
    """
    return _season_payload(session, on)


@router.get("/tiles")
def rate_tiles(
    start_date: date = Query(...),
    end_date: date | None = Query(
        None,
        description="Omit and pass `nights` instead to have the range clamped to the season.",
    ),
    nights: int = Query(7, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict:
    """Tiles for a range. Either give an explicit `end_date`, or ask for `nights`.

    The `nights` form exists to kill a race, not as a convenience. Discovering
    the season boundary needs a call, so a client that asks for "today plus a
    week" and clamps afterwards has a window where the unclamped request is
    already in flight -- and on the last day of a season that request crosses a
    boundary and comes back 422. Clamping here, where the boundary is already
    known, means the page cannot ask for a range it is not allowed to have.
    """
    if end_date is None:
        end_date = min(
            date.fromordinal(start_date.toordinal() + nights - 1),
            season_on(session, start_date)["end"],
        )
    payload = get_active_configuration(session).payload or {}
    increment = int((payload.get("rounding") or {}).get("increment") or 0)
    try:
        tiles = load_tiles(
            session, start=start_date, end=end_date, rounding_increment=increment
        )
    except RangeCrossesSeason as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    return {
        "start_date": start_date,
        "end_date": end_date,
        "nights": (end_date - start_date).days + 1,
        "season": _season_payload(session, start_date),
        "tiles": [_tile_payload(t) for t in tiles],
    }


@router.get("/range")
def rate_range(
    room_type_id: int = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    session: Session = Depends(get_session),
) -> dict:
    """One tier across one range -- what the drawer renders.

    ``adjustments`` carries deltas in DONG rather than percent: percentages of
    different bases do not average into anything meaningful, and the operator
    needs these lines to add up to the total above them.
    """
    payload = get_active_configuration(session).payload or {}
    increment = int((payload.get("rounding") or {}).get("increment") or 0)
    try:
        aggregate, nights, availability, room_type = load_range(
            session,
            room_type_id=room_type_id,
            start=start_date,
            end=end_date,
            rounding_increment=increment,
        )
    except RangeCrossesSeason as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    if aggregate is None or room_type is None:
        raise HTTPException(
            status_code=404,
            detail="No recommendation covers this room type over that range.",
        )

    priced_nights = [n for n in nights if n.priced]
    first = nights[0]
    return {
        "room_type_id": room_type_id,
        "room_type_name": room_type.name,
        "room_category": room_type.category,
        "room_category_label": category_label(room_type.category),
        "start_date": start_date,
        "end_date": end_date,
        "nights": aggregate.nights,
        "season": _season_payload(session, start_date),
        "base_net_rate": aggregate.base_net_rate,
        "average_recommended_net_rate": aggregate.average_recommended_net_rate,
        "average_current_net_rate": aggregate.average_current_net_rate,
        # ONE band for the whole range -- guaranteed by the season check above.
        # band_max is nullable: an empty MAX means the only ceiling is the
        # dynamic bound, so the band strip is drawn open to the right.
        "band": {
            "min": first.band_min,
            "base": first.band_base,
            "max": first.band_max,
        },
        "adjustments": [
            {
                "code": a.code,
                "label": a.label,
                "label_key": a.label_key,
                "delta": a.delta,
                "is_neutral": a.is_neutral,
                "is_ignored": a.is_ignored,
            }
            for a in aggregate.adjustments
        ],
        "nightly": [
            {
                "stay_date": n.stay_date,
                "units_sold": n.units_sold,
                "units_total": n.units_total,
                "recommended_net_rate": n.recommended_net_rate,
                "priced": n.priced,
                "days_to_arrival": n.days_to_arrival,
                "expected_occupancy": n.expected_occupancy,
                "occupancy": n.occupancy,
            }
            for n in nights
        ],
        # Averaged over PRICED nights only -- an unpriced night has no pace
        # reading, and counting it as zero would say the range is selling badly.
        "pace_gap": _mean_pace_gap(priced_nights),
        "units_sold": sum(n.units_sold for n in nights),
        "units_total": max((n.units_total for n in nights), default=0),
        # Uniform where every night agrees, "mixed" where they do not. An
        # achieved average standing in for a list price must never be read as
        # one, and hiding a minority "unavailable" behind the majority value
        # would do exactly that.
        "rate_provenance": _uniform_provenance(nights),
        "available_units": availability.units,
        "availability_is_exact": availability.is_exact,
        "unpriced_nights": aggregate.unpriced_nights,
    }


class RangeDecisionIn(BaseModel):
    room_type_id: int
    start_date: date
    end_date: date
    note: str | None = None
    operator: str = "demo-operator"


class RangeOverrideIn(RangeDecisionIn):
    final_net_rate: float
    reason_code: str


def _priced_range(session: Session, body: RangeDecisionIn):
    payload = get_active_configuration(session).payload or {}
    increment = int((payload.get("rounding") or {}).get("increment") or 0)
    try:
        aggregate, _nights, _availability, room_type = load_range(
            session,
            room_type_id=body.room_type_id,
            start=body.start_date,
            end=body.end_date,
            rounding_increment=increment,
        )
    except RangeCrossesSeason as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if aggregate is None or room_type is None:
        raise HTTPException(
            status_code=404, detail="No recommendation covers this room type over that range."
        )
    return aggregate


def _result_payload(result) -> dict:
    return {
        "group_id": result.group_id,
        "net_rate": result.net_rate,
        "decisions_written": result.decisions_written,
        "nights": result.nights,
        # Nights the engine could not price get no decision at all -- inventing
        # one would put a fictional entry in the audit trail. Reported so the
        # operator knows the range was not fully covered.
        "skipped_unpriced": result.skipped_unpriced,
    }


@router.post("/accept")
def accept_range(body: RangeDecisionIn, session: Session = Depends(get_session)) -> dict:
    """Accept the averaged price for every night in the range.

    Existing decisions are replaced without a prompt.
    """
    aggregate = _priced_range(session, body)
    return _result_payload(
        apply_to_range(
            session,
            room_type_id=body.room_type_id,
            start=body.start_date,
            end=body.end_date,
            net_rate=aggregate.average_recommended_net_rate,
            decision=DECISION_ACCEPTED,
            note=body.note,
            operator=body.operator,
        )
    )


@router.post("/override")
def override_range(body: RangeOverrideIn, session: Session = Depends(get_session)) -> dict:
    """Write the operator's own price to every night in the range."""
    if body.reason_code not in OVERRIDE_REASON_CODES:
        raise HTTPException(
            status_code=422, detail=f"Unknown override reason '{body.reason_code}'"
        )
    _priced_range(session, body)
    return _result_payload(
        apply_to_range(
            session,
            room_type_id=body.room_type_id,
            start=body.start_date,
            end=body.end_date,
            net_rate=body.final_net_rate,
            decision=DECISION_OVERRIDDEN,
            reason_code=body.reason_code,
            note=body.note,
            operator=body.operator,
        )
    )
