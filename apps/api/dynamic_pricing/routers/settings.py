"""Pricing configuration API — the operator's control surface for assumptions."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..pricing.defaults import FACTOR_ORDER, default_config
from ..schemas import ConfigIn, ConfigOut, PreviewIn, PreviewOut
from ..services.configuration import (
    create_configuration,
    get_active_configuration,
    list_configurations,
    reset_to_defaults,
)
from ..services.recommendations import generate_recommendations, preview_price

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/config", response_model=ConfigOut)
def read_config(session: Session = Depends(get_session)):
    return get_active_configuration(session)


@router.get("/defaults")
def read_defaults():
    """The provisional demo defaults, for the 'Reset' action and diffing."""
    return {"payload": default_config(), "factor_order": FACTOR_ORDER}


@router.put("/config", response_model=ConfigOut)
def save_config(body: ConfigIn, session: Session = Depends(get_session)):
    config = create_configuration(session, body.payload, label=body.label, note=body.note)
    if body.regenerate:
        # Settings changes must affect recommendations without a code change.
        generate_recommendations(session)
    return config


@router.post("/reset", response_model=ConfigOut)
def reset(session: Session = Depends(get_session), regenerate: bool = True):
    config = reset_to_defaults(session)
    if regenerate:
        generate_recommendations(session)
    return config


@router.get("/versions", response_model=list[ConfigOut])
def versions(session: Session = Depends(get_session)):
    return list_configurations(session)


@router.post("/preview", response_model=PreviewOut | None)
def preview(body: PreviewIn, session: Session = Depends(get_session)):
    """Price one stay date against an UNSAVED configuration."""
    from ..pricing.defaults import merge_config

    config = merge_config(body.payload)
    context, result = preview_price(
        session, config=config, room_id=body.room_id, stay_date=body.stay_date
    )
    if context is None or result is None:
        return None
    return PreviewOut(
        room_id=context.room_id,
        room_name=context.room_name,
        stay_date=context.stay_date,
        currency=context.currency,
        base_price=result.base_price,
        current_price=result.current_price,
        recommended_price=result.recommended_price,
        change_pct=result.change_pct,
        price_before_bounds=result.price_before_bounds,
        adjustments=[
            {
                "sequence": i,
                "code": a.code,
                "label": a.label,
                "factor": a.factor,
                "price_before": a.price_before,
                "price_after": a.price_after,
                "delta": a.delta,
                "reason": a.reason,
                "is_neutral": a.is_neutral,
            }
            for i, a in enumerate(result.adjustments)
        ],
        explanation=result.explanation,
        engine_version=result.engine_version,
    )
