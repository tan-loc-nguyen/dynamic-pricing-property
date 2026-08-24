"""Outcome tracking — the dataset that will eventually answer
"was the recommendation actually good?".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import RecommendationOutcome
from ..schemas import OutcomeOut
from ..services.outcomes import generate_demo_outcomes, outcome_summary, record_outcome

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])


class OutcomeIn(BaseModel):
    recommendation_id: int
    units_booked: int | None = None
    final_occupancy: float | None = None
    realized_net_rate: float | None = None
    realized_revenue: float | None = None
    cancellations: int | None = None
    source: str = "manual"
    notes: str | None = None


@router.get("/summary")
def summary(session: Session = Depends(get_session)):
    return outcome_summary(session)


@router.get("", response_model=list[OutcomeOut])
def list_outcomes(session: Session = Depends(get_session), limit: int = Query(200, ge=1, le=2000)):
    return list(
        session.scalars(
            select(RecommendationOutcome)
            .order_by(RecommendationOutcome.captured_at.desc())
            .limit(limit)
        ).all()
    )


@router.post("", response_model=OutcomeOut, status_code=201)
def create_outcome(body: OutcomeIn, session: Session = Depends(get_session)):
    """Record a REAL outcome. Never synthetic — demo rows come from /demo."""
    outcome = record_outcome(
        session,
        body.recommendation_id,
        units_booked=body.units_booked,
        final_occupancy=body.final_occupancy,
        realized_net_rate=body.realized_net_rate,
        realized_revenue=body.realized_revenue,
        cancellations=body.cancellations,
        is_synthetic=False,
        source=body.source,
        notes=body.notes,
    )
    if outcome is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return outcome


@router.post("/demo")
def create_demo_outcomes(session: Session = Depends(get_session)):
    """Generate SYNTHETIC outcomes for past stay dates. Clearly flagged."""
    created = generate_demo_outcomes(session)
    return {
        "created": created,
        "is_synthetic": True,
        "warning": "Synthetic demo outcomes — not real Luminous performance data.",
    }
