"""Operator decision history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import OperatorDecision, PricingRecommendation
from ..schemas import HistoryOut
from ._shared import reason_label

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistoryOut])
def list_history(
    session: Session = Depends(get_session),
    decision: str | None = None,
    property_id: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
):
    query = (
        select(OperatorDecision)
        .options(selectinload(OperatorDecision.recommendation))
        .order_by(OperatorDecision.created_at.desc())
        .limit(limit)
    )
    if decision and decision != "all":
        query = query.where(OperatorDecision.decision == decision)

    rows = []
    for d in session.scalars(query).all():
        rec: PricingRecommendation | None = d.recommendation
        if rec is None:
            continue
        if property_id and rec.property_id != property_id:
            continue
        features = rec.features or {}
        difference = round(d.final_price - d.recommended_price, 2)
        rows.append(
            HistoryOut(
                id=d.id,
                created_at=d.created_at,
                property_name=features.get("property_name", ""),
                room_name=features.get("room_name", ""),
                stay_date=rec.stay_date,
                decision=d.decision,
                recommended_price=d.recommended_price,
                final_price=d.final_price,
                previous_price=d.previous_price,
                difference=difference,
                difference_pct=round(difference / d.recommended_price * 100, 2)
                if d.recommended_price
                else 0.0,
                reason_code=d.reason_code,
                reason_label=reason_label(d.reason_code),
                note=d.note,
                engine_version=d.engine_version,
                config_version=d.config_version,
                operator=d.operator,
                currency=features.get("currency", "VND"),
            )
        )
    return rows
