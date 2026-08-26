"""Serialisation helpers shared by routers.

Routers stay thin: they translate HTTP <-> services and never compute rates.
"""

from __future__ import annotations

from sqlalchemy import select

from ..constants import OVERRIDE_REASONS
from ..models import OperatorDecision, PricingRecommendation
from ..pricing.rate_book import CATEGORY_LABELS

_REASON_LABELS = {r["code"]: r["label"] for r in OVERRIDE_REASONS}


def reason_label(code: str | None) -> str | None:
    if not code:
        return None
    return _REASON_LABELS.get(code, code)


def category_label(category: str | None) -> str:
    if not category:
        return ""
    return CATEGORY_LABELS.get(category, category)


def decision_dict(decision: OperatorDecision) -> dict:
    return {
        "id": decision.id,
        "decision": decision.decision,
        "recommended_net_rate": decision.recommended_net_rate,
        "final_net_rate": decision.final_net_rate,
        "previous_net_rate": decision.previous_net_rate,
        "reason_code": decision.reason_code,
        "reason_label": reason_label(decision.reason_code),
        "note": decision.note,
        "engine_version": decision.engine_version,
        "config_version": decision.config_version,
        "operator": decision.operator,
        "created_at": decision.created_at,
    }


def decisions_for_stay_date(session, rec: PricingRecommendation) -> list[OperatorDecision]:
    """Every decision ever made for this room type + stay date, oldest first.

    Decisions belong to the stay date, not to one recommendation run, so this
    survives recalculation without duplicating anything.
    """
    return list(
        session.scalars(
            select(OperatorDecision)
            .join(
                PricingRecommendation,
                OperatorDecision.recommendation_id == PricingRecommendation.id,
            )
            .where(
                PricingRecommendation.room_type_id == rec.room_type_id,
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
    f = rec.features or {}
    meta = rec.extra or {}
    payload = {
        "id": rec.id,
        "run_id": rec.run_id,
        "mode": rec.mode,
        "property_id": rec.property_id,
        "property_name": f.get("property_name", ""),
        "room_type_id": rec.room_type_id,
        "room_type_name": f.get("room_type_name", ""),
        "room_category": f.get("room_category", ""),
        "room_category_label": f.get("room_category_label") or category_label(f.get("room_category")),
        "stay_date": rec.stay_date,
        "day_of_week": f.get("day_of_week"),
        "currency": f.get("currency", "VND"),
        "season_key": rec.season_key,
        "season_label": f.get("season_label"),
        "band_min_net_rate": rec.band_min_net_rate,
        "band_base_net_rate": rec.band_base_net_rate,
        "band_max_net_rate": rec.band_max_net_rate,
        "rate_band_source": f.get("rate_band_source"),
        "base_net_rate": rec.base_net_rate,
        "current_net_rate": rec.current_net_rate,
        "current_ota_price": f.get("current_ota_price"),
        "rate_provenance": f.get("rate_provenance") or "published",
        "net_rate_before_clamp": rec.net_rate_before_clamp,
        "recommended_net_rate": rec.recommended_net_rate,
        "change_pct": rec.change_pct,
        "change_abs": round(rec.recommended_net_rate - rec.current_net_rate, 2),
        "total_adjustment_pct": rec.total_adjustment_pct,
        "units_total": f.get("units_total"),
        "units_sold": f.get("units_sold"),
        "units_available": f.get("units_available"),
        "occupancy": f.get("occupancy"),
        "days_to_arrival": f.get("days_to_arrival"),
        "expected_occupancy": f.get("expected_occupancy"),
        "pace_gap": f.get("pace_gap"),
        "recent_pickup": f.get("recent_pickup"),
        "pickup_delta": f.get("pickup_delta"),
        "is_event": bool(f.get("is_event")),
        "event_name": f.get("event_name"),
        "event_impact_level": f.get("event_impact_level"),
        "market_price_index": f.get("market_price_index"),
        "market_reference_net_rate": f.get("market_reference_net_rate"),
        "market_confidence": f.get("market_confidence"),
        "market_observation_count": f.get("market_observation_count", 0) or 0,
        "market_qualified_count": f.get("market_qualified_count", 0) or 0,
        "market_ignored_count": f.get("market_ignored_count", 0) or 0,
        "status": rec.status,
        "engine_version": rec.engine_version,
        "config_version": rec.config_version,
        "created_at": rec.created_at,
        "missing_signals": f.get("missing", []) or [],
        "clamp_applied": meta.get("clamp_applied"),
        # The band the ENGINE selected, so the table cannot disagree with the
        # drawer by re-deriving it from thresholds in TypeScript (D28).
        "pace_label_key": meta.get("pace_label_key"),
        "pickup_label_key": meta.get("pickup_label_key"),
        "pace_label": meta.get("pace_label"),
        "pace_tone": meta.get("pace_tone"),
        "pickup_label": meta.get("pickup_label"),
        # An error row has no adjustments, so without this the drawer would show
        # an empty breakdown and never say the engine had failed on this date.
        # The reason itself stays English: it is an exception signature, aimed
        # at whoever fixes it rather than at the operator.
        "unpriced": bool(meta.get("unpriced")),
        "unpriced_reason": meta.get("error"),
    }
    if detail:
        payload["adjustments"] = [
            {
                "sequence": a.sequence,
                "code": a.code,
                "label": a.label,
                "label_key": a.label_key,
                "params": a.params or {},
                "adjustment_pct": a.adjustment_pct,
                "factor": a.factor,
                "price_before": a.price_before,
                "price_after": a.price_after,
                "delta": a.delta,
                "is_neutral": a.is_neutral,
                "is_ignored": a.is_ignored,
            }
            for a in rec.adjustments
        ]
        payload["decisions"] = [
            decision_dict(d) for d in (decisions if decisions is not None else rec.decisions)
        ]
        payload["outcomes"] = [
            {
                "id": o.id,
                "units_booked": o.units_booked,
                "final_occupancy": o.final_occupancy,
                "realized_net_rate": o.realized_net_rate,
                "realized_revenue": o.realized_revenue,
                "cancellations": o.cancellations,
                "is_synthetic": o.is_synthetic,
                "source": o.source,
                "captured_at": o.captured_at,
                "notes": o.notes,
            }
            for o in rec.outcomes
        ]
        payload["features"] = f
        payload["metadata"] = meta
    return payload
