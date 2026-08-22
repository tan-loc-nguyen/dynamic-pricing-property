"""Serialisation helpers shared by routers.

Routers stay thin: they translate HTTP <-> services and never compute prices.
"""

from __future__ import annotations

from ..constants import OVERRIDE_REASONS
from ..models import OperatorDecision, PricingRecommendation

_REASON_LABELS = {r["code"]: r["label"] for r in OVERRIDE_REASONS}


def reason_label(code: str | None) -> str | None:
    if not code:
        return None
    return _REASON_LABELS.get(code, code)


def decision_dict(decision: OperatorDecision) -> dict:
    return {
        "id": decision.id,
        "decision": decision.decision,
        "recommended_price": decision.recommended_price,
        "final_price": decision.final_price,
        "previous_price": decision.previous_price,
        "reason_code": decision.reason_code,
        "reason_label": reason_label(decision.reason_code),
        "note": decision.note,
        "engine_version": decision.engine_version,
        "config_version": decision.config_version,
        "operator": decision.operator,
        "created_at": decision.created_at,
    }


def decisions_for_stay_date(session, rec: PricingRecommendation) -> list[OperatorDecision]:
    """Every decision ever made for this room + stay date, oldest first.

    Decisions belong to the stay date, not to one recommendation run, so this
    survives recalculation without duplicating anything.
    """
    from sqlalchemy import select

    return list(
        session.scalars(
            select(OperatorDecision)
            .join(PricingRecommendation, OperatorDecision.recommendation_id == PricingRecommendation.id)
            .where(
                PricingRecommendation.room_id == rec.room_id,
                PricingRecommendation.stay_date == rec.stay_date,
            )
            .order_by(OperatorDecision.created_at)
        ).all()
    )


def recommendation_dict(
    rec: PricingRecommendation,
    *,
    detail: bool = False,
    decisions: list[OperatorDecision] | None = None,
) -> dict:
    features = rec.features or {}
    payload = {
        "id": rec.id,
        "run_id": rec.run_id,
        "property_id": rec.property_id,
        "property_name": features.get("property_name", ""),
        "room_id": rec.room_id,
        "room_name": features.get("room_name", ""),
        "room_type": features.get("room_type", ""),
        "stay_date": rec.stay_date,
        "day_of_week": features.get("day_of_week"),
        "currency": features.get("currency", "VND"),
        "base_price": rec.base_price,
        "current_price": rec.current_price,
        "price_before_bounds": rec.price_before_bounds,
        "recommended_price": rec.recommended_price,
        "change_pct": rec.change_pct,
        "change_abs": round(rec.recommended_price - rec.current_price, 2),
        "total_multiplier": rec.total_multiplier,
        "occupancy": features.get("occupancy"),
        "units_sold": features.get("units_sold"),
        "units_total": features.get("units_total"),
        "days_to_checkin": features.get("days_to_checkin"),
        "booking_pace_index": features.get("booking_pace_index"),
        "market_price_index": features.get("market_price_index"),
        "market_reference_price": features.get("market_reference_price"),
        "market_observation_count": features.get("market_observation_count", 0) or 0,
        "is_event": bool(features.get("is_event")),
        "event_name": features.get("event_name"),
        "status": rec.status,
        "explanation": rec.explanation,
        "engine_version": rec.engine_version,
        "config_version": rec.config_version,
        "created_at": rec.created_at,
        "missing_signals": features.get("missing", []) or [],
    }
    if detail:
        payload["adjustments"] = [
            {
                "sequence": a.sequence,
                "code": a.code,
                "label": a.label,
                "factor": a.factor,
                "price_before": a.price_before,
                "price_after": a.price_after,
                "delta": a.delta,
                "reason": a.reason,
                "is_neutral": a.is_neutral,
            }
            for a in rec.adjustments
        ]
        payload["decisions"] = [
            decision_dict(d) for d in (decisions if decisions is not None else rec.decisions)
        ]
        payload["features"] = features
        payload["metadata"] = rec.extra or {}
    return payload
