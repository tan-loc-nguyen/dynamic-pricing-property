"""Seasonal Rate Book — CLIENT-VALIDATED rate strategy.

Served on its own endpoints, separate from the experimental dynamic strategy,
so the UI can present validated fact and unvalidated experiment distinctly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from ..db import get_session
from ..pricing.rate_book import (
    CATEGORY_LABELS,
    RATE_BOOK_SOURCE,
    ROOM_CATEGORIES,
    SEASONS,
)
from ..schemas import RateBandOut, RateBandUpdateIn
from ..services.rate_book import list_bands, reset_rate_book, update_band

router = APIRouter(prefix="/api/rate-book", tags=["rate-book"])


def _serialise(row) -> dict:
    return {
        "id": row.id,
        "season_key": row.season_key,
        "season_label": row.season_label,
        "months": row.months or [],
        "room_category": row.room_category,
        "room_category_label": CATEGORY_LABELS.get(row.room_category, row.room_category),
        "min_net_rate": row.min_net_rate,
        "base_net_rate": row.base_net_rate,
        "max_net_rate": row.max_net_rate,
        "currency": row.currency,
        "rate_basis": row.rate_basis,
        "source": row.source,
        "note": row.note,
    }


@router.get("", response_model=list[RateBandOut])
def read_rate_book(session: Session = Depends(get_session)):
    return [_serialise(r) for r in list_bands(session)]


@router.get("/meta")
def rate_book_meta():
    """Season and category vocabulary, plus the provenance statement."""
    return {
        "seasons": SEASONS,
        "categories": ROOM_CATEGORIES,
        "source": RATE_BOOK_SOURCE,
        "rate_basis": "NET",
        "statement": (
            "These MIN/BASE/MAX figures are NET rates supplied by Luminous and validated by "
            "real operation. They already encode seasonality, so the pricing engine selects a "
            "band by season rather than multiplying a seasonality factor on top."
        ),
    }


@router.put("/{band_id}", response_model=RateBandOut)
def edit_band(band_id: int, body: RateBandUpdateIn, session: Session = Depends(get_session)):
    if not (body.min_net_rate <= body.base_net_rate <= body.max_net_rate):
        raise HTTPException(
            status_code=422, detail="Rate band must satisfy MIN <= BASE <= MAX."
        )
    row = update_band(
        session,
        band_id,
        min_net_rate=body.min_net_rate,
        base_net_rate=body.base_net_rate,
        max_net_rate=body.max_net_rate,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Rate band not found")
    return _serialise(row)


@router.post("/reset")
def reset(session: Session = Depends(get_session), regenerate: bool = True):
    """Restore every band to the client-validated values."""
    from ..services.recommendations import PricingRunFailed, generate_recommendations

    restored = reset_rate_book(session)
    if regenerate:
        try:
            generate_recommendations(session)
        except PricingRunFailed as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"restored": restored, "source": RATE_BOOK_SOURCE}
