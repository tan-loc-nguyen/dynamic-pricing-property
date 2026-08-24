"""Outcome tracking — "was the recommendation actually good?"

This is the strategically important dataset. Every recommendation already
stores a reproducible feature + rate-band snapshot; an outcome attaches what
actually happened to that stay date afterwards.

PRODUCTION: outcomes are only written from real post-stay data. Nothing is
inferred or invented.
DEMO: synthetic outcomes may be generated for *past* stay dates so the shape
of the dataset is visible, and every such row is flagged ``is_synthetic``.
"""

from __future__ import annotations

import random
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Booking,
    PricingRecommendation,
    RecommendationOutcome,
    StayDateInventory,
)


def record_outcome(
    session: Session,
    recommendation_id: int,
    *,
    units_booked: int | None = None,
    final_occupancy: float | None = None,
    realized_net_rate: float | None = None,
    realized_revenue: float | None = None,
    cancellations: int | None = None,
    is_synthetic: bool = False,
    source: str = "manual",
    notes: str | None = None,
) -> RecommendationOutcome | None:
    rec = session.get(PricingRecommendation, recommendation_id)
    if rec is None:
        return None

    if realized_revenue is None and realized_net_rate is not None and units_booked is not None:
        realized_revenue = round(realized_net_rate * units_booked, 2)

    outcome = RecommendationOutcome(
        recommendation_id=rec.id,
        room_type_id=rec.room_type_id,
        stay_date=rec.stay_date,
        units_booked=units_booked,
        final_occupancy=final_occupancy,
        realized_net_rate=realized_net_rate,
        realized_revenue=realized_revenue,
        cancellations=cancellations,
        is_synthetic=is_synthetic,
        source=source,
        notes=notes,
    )
    session.add(outcome)
    session.commit()
    session.refresh(outcome)
    return outcome


def generate_demo_outcomes(session: Session, today: date | None = None, seed: int = 20260822) -> int:
    """Attach SYNTHETIC outcomes to past stay dates, for demo purposes only.

    Clearly flagged so it can never be mistaken for measurement. Real outcome
    capture requires post-stay data from Blue Jay.
    """
    today = today or date.today()
    rng = random.Random(seed)

    recs = list(
        session.scalars(
            select(PricingRecommendation).where(PricingRecommendation.stay_date < today)
        ).all()
    )
    existing = {
        r[0]
        for r in session.execute(select(RecommendationOutcome.recommendation_id)).all()
    }

    created = 0
    for rec in recs:
        if rec.id in existing:
            continue
        inventory = session.scalars(
            select(StayDateInventory).where(
                StayDateInventory.room_type_id == rec.room_type_id,
                StayDateInventory.stay_date == rec.stay_date,
            )
        ).first()
        if inventory is None:
            continue

        units_booked = inventory.units_sold
        realized = round(rec.recommended_net_rate * rng.uniform(0.96, 1.02) / 10_000) * 10_000
        record_outcome(
            session,
            rec.id,
            units_booked=units_booked,
            final_occupancy=inventory.occupancy,
            realized_net_rate=float(realized),
            cancellations=rng.choice([0, 0, 0, 1]),
            is_synthetic=True,
            source="demo",
            notes="Synthetic demo outcome — not real Luminous performance data.",
        )
        created += 1
    return created


def outcome_summary(session: Session) -> dict:
    """Readiness view: how much outcome data exists, and of what kind."""
    total = int(session.scalar(select(func.count()).select_from(RecommendationOutcome)) or 0)
    synthetic = int(
        session.scalar(
            select(func.count())
            .select_from(RecommendationOutcome)
            .where(RecommendationOutcome.is_synthetic.is_(True))
        )
        or 0
    )
    decided = int(
        session.scalar(
            select(func.count())
            .select_from(PricingRecommendation)
            .where(PricingRecommendation.status != "pending")
        )
        or 0
    )
    return {
        "total_outcomes": total,
        "synthetic_outcomes": synthetic,
        "real_outcomes": total - synthetic,
        "decided_recommendations": decided,
        "ready_for_evaluation": (total - synthetic) > 0,
        "note": (
            "Real outcome capture requires post-stay data from Blue Jay "
            "(realised NET revenue, final occupancy, cancellations)."
        ),
    }
