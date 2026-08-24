"""Operator decision history — system recommendation vs. what the operator did."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import OperatorDecision, PricingRecommendation
from ..schemas import HistoryOut
from ._shared import category_label, reason_label

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistoryOut])
def list_history(
    session: Session = Depends(get_session),
    decision: str | None = None,
    room_type_id: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
):
    # Every filter must be applied in SQL BEFORE the limit. Filtering in Python
    # afterwards would only search the most recent `limit` decisions overall, so
    # a room type with older-only activity would look like it had none.
    query = (
        select(OperatorDecision)
        .join(
            PricingRecommendation,
            OperatorDecision.recommendation_id == PricingRecommendation.id,
        )
        .options(selectinload(OperatorDecision.recommendation))
    )
    if decision and decision != "all":
        query = query.where(OperatorDecision.decision == decision)
    if room_type_id:
        query = query.where(PricingRecommendation.room_type_id == room_type_id)
    query = query.order_by(OperatorDecision.created_at.desc()).limit(limit)

    rows = []
    for d in session.scalars(query).all():
        rec: PricingRecommendation | None = d.recommendation
        if rec is None:
            continue
        f = rec.features or {}
        difference = round(d.final_net_rate - d.recommended_net_rate, 2)
        rows.append(
            HistoryOut(
                id=d.id,
                created_at=d.created_at,
                property_name=f.get("property_name", ""),
                room_type_name=f.get("room_type_name", ""),
                room_category_label=f.get("room_category_label") or category_label(f.get("room_category")),
                stay_date=rec.stay_date,
                season_label=f.get("season_label"),
                decision=d.decision,
                recommended_net_rate=d.recommended_net_rate,
                final_net_rate=d.final_net_rate,
                previous_net_rate=d.previous_net_rate,
                difference=difference,
                difference_pct=round(difference / d.recommended_net_rate * 100, 2)
                if d.recommended_net_rate
                else 0.0,
                reason_code=d.reason_code,
                reason_label=reason_label(d.reason_code),
                note=d.note,
                engine_version=d.engine_version,
                config_version=d.config_version,
                operator=d.operator,
                currency=f.get("currency", "VND"),
            )
        )
    return rows
