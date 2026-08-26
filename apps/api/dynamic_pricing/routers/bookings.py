"""Occupied unit-nights, for the calendar's occupancy detail.

One row is ONE ROOM OCCUPIED ON ONE NIGHT -- see BookingOut, which carries the
full explanation. It is emphatically not a stay, and the model's `nights` is
not a stay length; treating it as one draws roughly 3.5x the occupancy that
exists, so this endpoint does not publish it.

Deliberately additive: no model change, no pricing change, no migration.
"""

from __future__ import annotations

from datetime import date

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
    limit: int = Query(5000, ge=1, le=20000),
):
    """Occupied unit-nights whose date falls inside the window.

    A plain date filter is correct here BECAUSE a row is a single night. An
    earlier version widened the window by 60 days and reconstructed an end date
    from `nights` to catch "stays spanning into" it -- there are no such stays,
    and the reconstruction was the bug.
    """
    query = select(Booking).where(Booking.status != "cancelled")
    if room_type_id is not None:
        query = query.where(Booking.room_type_id == room_type_id)
    if start_date is not None:
        query = query.where(Booking.stay_date >= start_date)
    if end_date is not None:
        query = query.where(Booking.stay_date <= end_date)

    rows = list(session.scalars(query.order_by(Booking.stay_date).limit(limit)).all())
    categories = {rt.id: rt.category for rt in session.scalars(select(RoomType)).all()}

    out = [
        BookingOut(
            id=b.id,
            external_id=b.external_id,
            room_type_id=b.room_type_id,
            room_category=categories.get(b.room_type_id),
            # NULL for every seeded row: no booking is assigned to a unit
            # (ASSUMPTIONS U11).
            physical_room_id=b.physical_room_id,
            stay_date=b.stay_date,
            guests=b.guests,
            net_rate=b.net_rate,
            channel=b.channel,
            status=b.status,
        )
        for b in rows
    ]
    return out
