"""Manual event management.

Events are curated by the operator, not scraped. An automated event feed is an
explicit non-goal for this phase.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..constants import EVENT_IMPACT_LEVELS, EVENT_TYPES
from ..db import get_session
from ..models import Event
from ..schemas import EventIn, EventOut

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventOut])
def list_events(
    session: Session = Depends(get_session),
    include_inactive: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
):
    query = select(Event).order_by(Event.start_date)
    if not include_inactive:
        query = query.where(Event.is_active.is_(True))
    if start_date:
        query = query.where(Event.end_date >= start_date)
    if end_date:
        query = query.where(Event.start_date <= end_date)
    return list(session.scalars(query).all())


@router.get("/meta")
def event_meta():
    return {"impact_levels": EVENT_IMPACT_LEVELS, "event_types": EVENT_TYPES}


@router.post("", response_model=EventOut, status_code=201)
def create_event(body: EventIn, session: Session = Depends(get_session)):
    if body.end_date < body.start_date:
        raise HTTPException(status_code=422, detail="end_date cannot precede start_date")
    event = Event(**body.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.put("/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventIn, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if body.end_date < body.start_date:
        # Without this an event can be edited into an inverted range, where
        # Event.covers() is false for every date and it silently stops
        # affecting any recommendation.
        raise HTTPException(status_code=422, detail="end_date cannot precede start_date")
    for key, value in body.model_dump().items():
        setattr(event, key, value)
    session.commit()
    session.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, session: Session = Depends(get_session)):
    session.execute(delete(Event).where(Event.id == event_id))
    session.commit()
