"""The season calendar: which months belong to which season.

Replaced wholesale rather than edited one season at a time, because the
partition is a property of the whole year -- validating one season in isolation
cannot see the gap its edit just opened next door.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..pricing.seasons import PartitionError
from ..services.seasons import save_seasons, season_calendar

router = APIRouter(prefix="/api/seasons", tags=["seasons"])


class SeasonIn(BaseModel):
    key: str
    label: str
    months: list[int]


class SeasonsIn(BaseModel):
    seasons: list[SeasonIn]


@router.get("")
def read_seasons(session: Session = Depends(get_session)) -> dict:
    return {"seasons": season_calendar(session)}


@router.put("")
def write_seasons(payload: SeasonsIn, session: Session = Depends(get_session)) -> dict:
    try:
        saved = save_seasons(
            session, [{"key": s.key, "label": s.label, "months": s.months} for s in payload.seasons]
        )
    except PartitionError as exc:
        # The message names the offending MONTHS, which is what the operator
        # needs to fix it -- discarding it into a bare 422 would throw away the
        # only useful part.
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"seasons": saved}
