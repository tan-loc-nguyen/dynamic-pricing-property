"""EXPERIMENTAL dynamic-strategy configuration.

The client-validated rate book is served by ``routers/rate_book.py``. Keeping
the endpoints separate is what lets the UI present validated fact and
unvalidated experiment as two different things.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..pricing.defaults import EXPERIMENTAL_SECTIONS, default_config
from ..schemas import ConfigIn, ConfigOut, PreviewIn, PreviewOut
from ..services.configuration import (
    create_configuration,
    get_active_configuration,
    list_configurations,
    reset_to_defaults,
)
from ..services.recommendations import generate_recommendations, preview_rate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/config", response_model=ConfigOut)
def read_config(session: Session = Depends(get_session)):
    return get_active_configuration(session)


@router.get("/defaults")
def read_defaults():
    return {
        "payload": default_config(),
        "experimental_sections": EXPERIMENTAL_SECTIONS,
        "status": "UNVALIDATED",
        "statement": (
            "Every value in this section was chosen by the engineering team to make the "
            "dynamic layer legible. None has been validated with Luminous."
        ),
    }


@router.put("/config", response_model=ConfigOut)
def save_config(body: ConfigIn, session: Session = Depends(get_session)):
    config = create_configuration(session, body.payload, label=body.label, note=body.note)
    if body.regenerate:
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
    context, result = preview_rate(
        session, config=config, room_type_id=body.room_type_id, stay_date=body.stay_date
    )
    if context is None or result is None:
        return None
    return PreviewOut(
        room_type_id=context.room_type_id,
        room_type_name=context.room_type_name,
        room_category_label=context.room_category_label,
        stay_date=context.stay_date,
        currency=context.currency,
        season_label=context.season_label,
        band_min_net_rate=context.band_min_net_rate,
        band_base_net_rate=context.band_base_net_rate,
        band_max_net_rate=context.band_max_net_rate,
        base_net_rate=result.base_net_rate,
        current_net_rate=result.current_net_rate,
        recommended_net_rate=result.recommended_net_rate,
        change_pct=result.change_pct,
        total_adjustment_pct=result.total_adjustment_pct,
        adjustments=[
            {
                "sequence": i,
                "code": a.code,
                "label": a.label,
                "adjustment_pct": a.adjustment_pct,
                "factor": a.factor,
                "price_before": a.price_before,
                "price_after": a.price_after,
                "delta": a.delta,
                "reason": a.reason,
                "is_neutral": a.is_neutral,
                "is_ignored": a.is_ignored,
            }
            for i, a in enumerate(result.adjustments)
        ],
        explanation=result.explanation,
        engine_version=result.engine_version,
    )
