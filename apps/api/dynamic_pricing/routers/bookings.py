"""Booking rows, for the calendar's occupancy timeline.

These rows have existed since the first seed and nothing could read them. The
calendar needs them to draw a booking as a BAR across the nights it occupies
rather than as an occupancy percentage per night.

Deliberately additive: no model change, no pricing change, no migration.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Booking, RoomType
from ..schemas import BookingOut

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.get("", response_model=list[BookingOut])
def list_bookings(
    session: Session = Depends(get_session),
    start_date: date | None = None,
    end_date: date | None = None,
    room_type_id: int | None = None,
    limit: int = Query(2000, ge=1, le=10000),
):
    """Bookings OVERLAPPING the window, not merely starting inside it.

    A booking that checked in before `start_date` still occupies nights inside
    it, and a calendar that dropped those would show the month emptier than it
    is. `nights` is on the row, so the overlap is computable without a stored
    end date.
    """
    query = select(Booking).where(Booking.status != "cancelled")
    if room_type_id is not None:
        query = query.where(Booking.room_type_id == room_type_id)
    if end_date is not None:
        query = query.where(Booking.stay_date <= end_date)
    if start_date is not None:
        # Cheap pre-filter in SQL: nothing starting more than the longest
        # possible stay before the window can still overlap it. The exact
        # overlap is settled below, where `nights` is available per row.
        query = query.where(Booking.stay_date >= start_date - timedelta(days=60))

    rows = list(session.scalars(query.order_by(Booking.stay_date).limit(limit)).all())

    categories = {
        rt.id: rt.category
        for rt in session.scalars(select(RoomType)).all()
    }

    out: list[BookingOut] = []
    for b in rows:
        nights = max(int(b.nights or 1), 1)
        last_night = b.stay_date + timedelta(days=nights - 1)
        if start_date is not None and last_night < start_date:
            continue
        out.append(
            BookingOut(
                id=b.id,
                external_id=b.external_id,
                room_type_id=b.room_type_id,
                room_category=categories.get(b.room_type_id),
                # NULL for every seeded row: no booking is assigned to a unit.
                # The calendar degrades to unlabelled lanes rather than
                # inventing an apartment number (ASSUMPTIONS U11).
                physical_room_id=b.physical_room_id,
                stay_date=b.stay_date,
                nights=nights,
                last_night=last_night,
                guests=b.guests,
                net_rate=b.net_rate,
                channel=b.channel,
                status=b.status,
            )
        )
    return out
