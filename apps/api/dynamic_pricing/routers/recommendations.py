"""Recommendation listing, detail, generation and the human-in-the-loop actions.

Shadow Mode: accepting a rate records the decision and updates the local NET
rate. Nothing is pushed to Blue Jay or any OTA.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..constants import (
    DECISION_ACCEPTED,
    DECISION_OVERRIDDEN,
    OVERRIDE_REASON_CODES,
    STATUS_ACCEPTED,
    STATUS_OVERRIDDEN,
)
from ..db import get_session
from ..models import OperatorDecision, PricingRecommendation, RoomType, StayDateInventory
from ..pricing import DEFAULT_ENGINE
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


def _apply_filters(query, *, property_id, room_type_id, room_category, start_date, end_date, status):
    if property_id:
        query = query.where(PricingRecommendation.property_id == property_id)
    if room_type_id:
        query = query.where(PricingRecommendation.room_type_id == room_type_id)
    if start_date:
        query = query.where(PricingRecommendation.stay_date >= start_date)
    if end_date:
        query = query.where(PricingRecommendation.stay_date <= end_date)
    if status and status != "all":
        query = query.where(PricingRecommendation.status == status)
    return query


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    session: Session = Depends(get_session),
    property_id: int | None = None,
    room_type_id: int | None = None,
    room_category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    run_id, query = _current_query(session)
    if query is None:
        return []
    query = _apply_filters(
        query,
        property_id=property_id,
        room_type_id=room_type_id,
        room_category=room_category,
        start_date=start_date,
        end_date=end_date,
        status=status,
    )
    rows = session.scalars(
        query.order_by(PricingRecommendation.stay_date, PricingRecommendation.room_type_id)
        .offset(offset)
        .limit(limit)
    ).all()

    payloads = [recommendation_dict(r) for r in rows]
    if room_category and room_category != "all":
        payloads = [p for p in payloads if p["room_category"] == room_category]
    if search:
        needle = search.lower()
        payloads = [
            p
            for p in payloads
            if needle in p["room_type_name"].lower()
            or needle in p["room_category_label"].lower()
            or needle in p["property_name"].lower()
        ]
    return payloads


@router.get("/summary", response_model=SummaryOut)
def summary(
    session: Session = Depends(get_session),
    property_id: int | None = None,
    room_type_id: int | None = None,
    room_category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    run_id, query = _current_query(session)
    room_types = list(session.scalars(select(RoomType).where(RoomType.is_active.is_(True))).all())
    total_units = sum(rt.units_total for rt in room_types)

    empty = SummaryOut(
        room_types=len(room_types),
        total_units=total_units,
        upcoming_nights=0,
        average_occupancy=None,
        average_pace_gap=None,
        pending_recommendations=0,
        accepted_recommendations=0,
        overridden_recommendations=0,
        average_recommended_change_pct=0.0,
        total_recommendations=0,
    )
    if query is None:
        return empty

    query = _apply_filters(
        query,
        property_id=property_id,
        room_type_id=room_type_id,
        room_category=room_category,
        start_date=start_date,
        end_date=end_date,
        status=None,
    )
    rows = list(session.scalars(query).all())
    if room_category and room_category != "all":
        rows = [r for r in rows if (r.features or {}).get("room_category") == room_category]
    if not rows:
        return empty

    occ = [r.features.get("occupancy") for r in rows if (r.features or {}).get("occupancy") is not None]
    gaps = [r.features.get("pace_gap") for r in rows if (r.features or {}).get("pace_gap") is not None]
    changes = [r.change_pct for r in rows]
    dates = [r.stay_date for r in rows]

    return SummaryOut(
        room_types=len(room_types),
        total_units=total_units,
        upcoming_nights=len(rows),
        average_occupancy=round(sum(occ) / len(occ), 4) if occ else None,
        average_pace_gap=round(sum(gaps) / len(gaps), 4) if gaps else None,
        pending_recommendations=sum(1 for r in rows if r.status == "pending"),
        accepted_recommendations=sum(1 for r in rows if r.status == STATUS_ACCEPTED),
        overridden_recommendations=sum(1 for r in rows if r.status == STATUS_OVERRIDDEN),
        average_recommended_change_pct=round(sum(changes) / len(changes), 2),
        total_recommendations=len(rows),
        currency=rows[0].features.get("currency", "VND"),
        horizon_start=min(dates),
        horizon_end=max(dates),
        mode=rows[0].mode,
    )


@router.post("/generate")
def generate(session: Session = Depends(get_session), engine_key: str = DEFAULT_ENGINE):
    return generate_recommendations(session, engine_key=engine_key).as_dict()


@router.get("/{recommendation_id}", response_model=RecommendationDetailOut)
def get_recommendation(recommendation_id: int, session: Session = Depends(get_session)):
    rec = session.scalars(
        select(PricingRecommendation)
        .where(PricingRecommendation.id == recommendation_id)
        .options(
            selectinload(PricingRecommendation.adjustments),
            selectinload(PricingRecommendation.decisions),
            selectinload(PricingRecommendation.outcomes),
        )
    ).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation_dict(rec, detail=True, decisions=decisions_for_stay_date(session, rec))


def _apply_net_rate(session: Session, rec: PricingRecommendation, net_rate: float) -> float:
    """Record the approved NET rate locally.

    SHADOW MODE: this updates our own view only. Blue Jay remains the system of
    record and the execution layer; the operator applies the rate there.
    """
    inventory = session.scalars(
        select(StayDateInventory).where(
            StayDateInventory.room_type_id == rec.room_type_id,
            StayDateInventory.stay_date == rec.stay_date,
        )
    ).first()
    previous = inventory.current_net_rate if inventory else rec.current_net_rate
    if inventory:
        inventory.current_net_rate = net_rate
    return previous


@router.post("/{recommendation_id}/accept", response_model=RecommendationDetailOut)
def accept(recommendation_id: int, body: AcceptIn, session: Session = Depends(get_session)):
    rec = session.get(PricingRecommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    previous = _apply_net_rate(session, rec, rec.recommended_net_rate)
    session.add(
        OperatorDecision(
            recommendation_id=rec.id,
            decision=DECISION_ACCEPTED,
            recommended_net_rate=rec.recommended_net_rate,
            final_net_rate=rec.recommended_net_rate,
            previous_net_rate=previous,
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

    previous = _apply_net_rate(session, rec, body.final_net_rate)
    session.add(
        OperatorDecision(
            recommendation_id=rec.id,
            decision=DECISION_OVERRIDDEN,
            recommended_net_rate=rec.recommended_net_rate,
            final_net_rate=body.final_net_rate,
            previous_net_rate=previous,
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
