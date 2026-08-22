"""Recommendation listing, detail, generation and the human-in-the-loop actions."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..constants import (
    DECISION_ACCEPTED,
    DECISION_OVERRIDDEN,
    OVERRIDE_REASON_CODES,
    STATUS_ACCEPTED,
    STATUS_OVERRIDDEN,
)
from ..db import get_session
from ..models import OperatorDecision, PricingRecommendation, Room, StayDateInventory
from ..schemas import (
    AcceptIn,
    OverrideIn,
    RecommendationDetailOut,
    RecommendationOut,
    SummaryOut,
)
from ..services.recommendations import generate_recommendations, latest_run_id
from ._shared import decisions_for_stay_date, recommendation_dict

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _current_query(session: Session):
    run_id = latest_run_id(session)
    if not run_id:
        return None, None
    return run_id, select(PricingRecommendation).where(PricingRecommendation.run_id == run_id)


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    session: Session = Depends(get_session),
    property_id: int | None = None,
    room_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    run_id, query = _current_query(session)
    if query is None:
        return []
    if property_id:
        query = query.where(PricingRecommendation.property_id == property_id)
    if room_id:
        query = query.where(PricingRecommendation.room_id == room_id)
    if start_date:
        query = query.where(PricingRecommendation.stay_date >= start_date)
    if end_date:
        query = query.where(PricingRecommendation.stay_date <= end_date)
    if status and status != "all":
        query = query.where(PricingRecommendation.status == status)

    rows = session.scalars(
        query.order_by(PricingRecommendation.stay_date, PricingRecommendation.room_id)
        .offset(offset)
        .limit(limit)
    ).all()

    payloads = [recommendation_dict(r) for r in rows]
    if search:
        needle = search.lower()
        payloads = [
            p
            for p in payloads
            if needle in p["room_name"].lower() or needle in p["property_name"].lower()
        ]
    return payloads


@router.get("/summary", response_model=SummaryOut)
def summary(
    session: Session = Depends(get_session),
    property_id: int | None = None,
    room_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    run_id, query = _current_query(session)
    active_rooms = len(
        session.scalars(select(Room).where(Room.is_active.is_(True))).all()
    )
    if query is None:
        return SummaryOut(
            active_rooms=active_rooms,
            upcoming_nights=0,
            average_occupancy=None,
            pending_recommendations=0,
            accepted_recommendations=0,
            overridden_recommendations=0,
            average_recommended_change_pct=0.0,
            total_recommendations=0,
        )
    if property_id:
        query = query.where(PricingRecommendation.property_id == property_id)
    if room_id:
        query = query.where(PricingRecommendation.room_id == room_id)
    if start_date:
        query = query.where(PricingRecommendation.stay_date >= start_date)
    if end_date:
        query = query.where(PricingRecommendation.stay_date <= end_date)

    rows = session.scalars(query).all()
    if not rows:
        return SummaryOut(
            active_rooms=active_rooms,
            upcoming_nights=0,
            average_occupancy=None,
            pending_recommendations=0,
            accepted_recommendations=0,
            overridden_recommendations=0,
            average_recommended_change_pct=0.0,
            total_recommendations=0,
        )

    occupancies = [
        r.features.get("occupancy") for r in rows if (r.features or {}).get("occupancy") is not None
    ]
    changes = [r.change_pct for r in rows]
    dates = [r.stay_date for r in rows]
    return SummaryOut(
        active_rooms=active_rooms,
        upcoming_nights=len(rows),
        average_occupancy=round(sum(occupancies) / len(occupancies), 4) if occupancies else None,
        pending_recommendations=sum(1 for r in rows if r.status == "pending"),
        accepted_recommendations=sum(1 for r in rows if r.status == STATUS_ACCEPTED),
        overridden_recommendations=sum(1 for r in rows if r.status == STATUS_OVERRIDDEN),
        average_recommended_change_pct=round(sum(changes) / len(changes), 2),
        total_recommendations=len(rows),
        currency=rows[0].features.get("currency", "VND"),
        horizon_start=min(dates),
        horizon_end=max(dates),
    )


@router.post("/generate")
def generate(session: Session = Depends(get_session), engine_key: str = "v1"):
    report = generate_recommendations(session, engine_key=engine_key)
    return report.as_dict()


@router.get("/{recommendation_id}", response_model=RecommendationDetailOut)
def get_recommendation(recommendation_id: int, session: Session = Depends(get_session)):
    rec = session.scalars(
        select(PricingRecommendation)
        .where(PricingRecommendation.id == recommendation_id)
        .options(
            selectinload(PricingRecommendation.adjustments),
            selectinload(PricingRecommendation.decisions),
        )
    ).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation_dict(rec, detail=True, decisions=decisions_for_stay_date(session, rec))


def _apply_price(session: Session, rec: PricingRecommendation, price: float) -> float:
    """Write the approved price back onto the inventory row.

    The MVP does not push to the PMS (explicit non-goal), but reflecting the
    decision locally is what makes the loop feel real: once approved, that
    price becomes the current price. See docs/DECISIONS.md (D8).
    """
    inventory = session.scalars(
        select(StayDateInventory).where(
            StayDateInventory.room_id == rec.room_id,
            StayDateInventory.stay_date == rec.stay_date,
        )
    ).first()
    previous = inventory.current_price if inventory else rec.current_price
    if inventory:
        inventory.current_price = price
    return previous


@router.post("/{recommendation_id}/accept", response_model=RecommendationDetailOut)
def accept(recommendation_id: int, body: AcceptIn, session: Session = Depends(get_session)):
    rec = session.get(PricingRecommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    previous = _apply_price(session, rec, rec.recommended_price)
    session.add(
        OperatorDecision(
            recommendation_id=rec.id,
            decision=DECISION_ACCEPTED,
            recommended_price=rec.recommended_price,
            final_price=rec.recommended_price,
            previous_price=previous,
            reason_code=None,
            note=body.note,
            engine_version=rec.engine_version,
            config_version=rec.config_version,
            operator=body.operator,
        )
    )
    rec.status = STATUS_ACCEPTED
    session.commit()
    session.refresh(rec)
    return recommendation_dict(rec, detail=True, decisions=decisions_for_stay_date(session, rec))


@router.post("/{recommendation_id}/override", response_model=RecommendationDetailOut)
def override(recommendation_id: int, body: OverrideIn, session: Session = Depends(get_session)):
    rec = session.get(PricingRecommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if body.reason_code not in OVERRIDE_REASON_CODES:
        raise HTTPException(status_code=422, detail=f"Unknown override reason '{body.reason_code}'")

    previous = _apply_price(session, rec, body.final_price)
    session.add(
        OperatorDecision(
            recommendation_id=rec.id,
            decision=DECISION_OVERRIDDEN,
            recommended_price=rec.recommended_price,
            final_price=body.final_price,
            previous_price=previous,
            reason_code=body.reason_code,
            note=body.note,
            engine_version=rec.engine_version,
            config_version=rec.config_version,
            operator=body.operator,
        )
    )
    rec.status = STATUS_OVERRIDDEN
    session.commit()
    session.refresh(rec)
    return recommendation_dict(rec, detail=True, decisions=decisions_for_stay_date(session, rec))


@router.post("/{recommendation_id}/reset", response_model=RecommendationDetailOut)
def reset_decision(recommendation_id: int, session: Session = Depends(get_session)):
    """Return a recommendation to Pending (demo convenience)."""
    rec = session.get(PricingRecommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.status = "pending"
    session.commit()
    session.refresh(rec)
    return recommendation_dict(rec, detail=True, decisions=decisions_for_stay_date(session, rec))
