"""Recommendation listing, detail, generation and the human-in-the-loop actions.

Shadow Mode: accepting a rate records the decision and updates the local NET
rate. Nothing is pushed to Blue Jay or any OTA.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..constants import (
    DECISION_ACCEPTED,
    STATUS_ERROR,
    DECISION_OVERRIDDEN,
    OVERRIDE_REASON_CODES,
    STATUS_ACCEPTED,
    STATUS_OVERRIDDEN,
)
from ..db import get_session
from ..lookup import UnknownRegistryKey
from ..models import OperatorDecision, PricingRecommendation, RoomType, StayDateInventory
from ..pricing import DEFAULT_ENGINE
from ..schemas import (
    AcceptIn,
    OverrideIn,
    RecommendationDetailOut,
    RecommendationOut,
    SummaryOut,
)
from ..services.recommendations import (
    PricingRunFailed,
    generate_recommendations,
    latest_run_id,
)
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
    if room_category and room_category != "all":
        # Category lives on RoomType, so this must be a join rather than a
        # post-query Python filter -- otherwise it would filter an already
        # truncated page.
        # NOTE: this filters the LIVE category while the response renders the
        # category frozen in the run's feature snapshot. Recategorising a room
        # type between runs makes the two disagree until the next run.
        query = query.where(
            PricingRecommendation.room_type_id.in_(
                select(RoomType.id).where(RoomType.category == room_category)
            )
        )
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
    codes: str | None = None,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """List the current run's recommendations.

    ``search`` is free text over REAL-WORLD names — a property, a room type —
    which are never translated and so have no code to resolve to.

    ``codes`` is a comma-separated list of room-category and season CODES. The
    operator types in their own language and the FRONTEND resolves that against
    its message files (D30) before calling; the API never learns a second
    language. Without this, searching the Vietnamese table for the Vietnamese
    words printed on it returned nothing, because the columns being matched
    hold English.
    """
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
    query = query.order_by(PricingRecommendation.stay_date, PricingRecommendation.room_type_id)

    wanted = {c.strip().lower() for c in (codes or "").split(",") if c.strip()}
    needle = (search or "").strip().lower()

    if not (needle or wanted):
        # Only the search branch needs the full set. Paging in SQL otherwise
        # avoids materialising and serialising every matching row to return one.
        query = query.offset(offset).limit(limit)

    rows = session.scalars(query).all()
    payloads = [recommendation_dict(r) for r in rows]
    if not (needle or wanted):
        return payloads

    def matches(p: dict) -> bool:
        # Alternatives, NOT a narrowing. One box drives both mechanisms, so a
        # term that resolves to a code is by definition absent from the property
        # name — anding them would return nothing for every successful lookup.
        if wanted and (p["room_category"] in wanted or p["season_key"] in wanted):
            return True
        if needle and (
            needle in p["room_type_name"].lower()
            or needle in p["room_category_label"].lower()
            or needle in p["property_name"].lower()
        ):
            return True
        return False

    # Applied BEFORE paging, so the page is a slice of the matches rather than a
    # filter of one arbitrary page.
    payloads = [p for p in payloads if matches(p)]
    return payloads[offset : offset + limit]


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
        unpriced_recommendations=0,
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
    if not rows:
        return empty

    errored = [r for r in rows if r.status == STATUS_ERROR]
    priced = [r for r in rows if r.status != STATUS_ERROR]
    occ = [r.features.get("occupancy") for r in rows if (r.features or {}).get("occupancy") is not None]
    gaps = [r.features.get("pace_gap") for r in rows if (r.features or {}).get("pace_gap") is not None]
    changes = [r.change_pct for r in priced]
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
        unpriced_recommendations=len(errored),
        # Averaged over PRICED rows only. Error rows carry change_pct = 0 by
        # construction, so including them would drag the average toward zero and
        # understate the real movement.
        average_recommended_change_pct=round(sum(changes) / len(changes), 2) if changes else 0.0,
        total_recommendations=len(rows),
        currency=rows[0].features.get("currency", "VND"),
        horizon_start=min(dates),
        horizon_end=max(dates),
        mode=rows[0].mode,
    )


@router.post("/generate")
def generate(session: Session = Depends(get_session), engine_key: str = DEFAULT_ENGINE):
    try:
        return generate_recommendations(session, engine_key=engine_key).as_dict()
    except UnknownRegistryKey as exc:
        # The message already names every valid key -- that is exactly the body
        # a 422 wants, and it was being discarded into a 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PricingRunFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    if rec.status == STATUS_ERROR:
        # There is no recommendation to act on. Recording a decision here would
        # put a fictional entry in the audit trail, which is the one dataset
        # this product cannot afford to have noise in.
        raise HTTPException(
            status_code=409,
            detail="This stay date could not be priced, so there is no recommendation to act on.",
        )

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
    if rec.status == STATUS_ERROR:
        # There is no recommendation to act on. Recording a decision here would
        # put a fictional entry in the audit trail, which is the one dataset
        # this product cannot afford to have noise in.
        raise HTTPException(
            status_code=409,
            detail="This stay date could not be priced, so there is no recommendation to act on.",
        )
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
