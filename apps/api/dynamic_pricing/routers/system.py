"""System status, portfolio listing, and demo controls.

The status endpoint is what lets the UI show an honest integration banner
instead of pretending everything is fine.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..constants import OVERRIDE_REASONS
from ..db import get_session
from ..models import (
    Booking,
    MarketObservation,
    OperatorDecision,
    PricingRecommendation,
    Property,
    Room,
    StayDateInventory,
)
from ..pricing import get_engine, list_engines
from ..providers.market import get_market_provider
from ..providers.pms import get_pms_provider
from ..providers.pms.mock import HISTORY_DAYS, HORIZON_DAYS
from ..schemas import PropertyOut, SystemStatusOut
from ..services.configuration import get_active_configuration
from ..services.recommendations import generate_recommendations, latest_run_id
from ..services.sync import default_window, sync_market, sync_pms

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/properties", response_model=list[PropertyOut])
def properties(session: Session = Depends(get_session)):
    rows = session.scalars(select(Property).order_by(Property.name)).all()
    return [
        PropertyOut(
            id=p.id,
            external_id=p.external_id,
            name=p.name,
            city=p.city,
            district=p.district,
            currency=p.currency,
            rooms=[
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "name": r.name,
                    "room_type": r.room_type,
                    "capacity": r.capacity,
                    "units_total": r.units_total,
                    "base_price": r.base_price,
                    "min_price": r.min_price,
                    "max_price": r.max_price,
                    "is_active": r.is_active,
                }
                for r in sorted(p.rooms, key=lambda x: x.name)
            ],
        )
        for p in rows
    ]


@router.get("/engines")
def engines():
    return list_engines()


@router.get("/status", response_model=SystemStatusOut)
def status(session: Session = Depends(get_session)):
    settings = get_settings()
    config = get_active_configuration(session)
    engine = get_engine("v1")

    pms_status = get_pms_provider().status()
    market_status = get_market_provider().status()

    def count(model) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    return SystemStatusOut(
        api_version=__version__,
        engine={
            "key": "v1",
            "name": engine.name,
            "version": engine.version,
            "description": engine.description,
        },
        available_engines=list_engines(),
        config_version=config.version,
        config_label=config.label,
        pms={
            "name": pms_status.name,
            "healthy": pms_status.healthy,
            "mode": pms_status.mode,
            "detail": pms_status.detail,
            "remediation": pms_status.remediation,
            "unresolved_mappings": pms_status.unresolved_mappings,
        },
        market={
            "name": market_status.name,
            "healthy": market_status.healthy,
            "mode": market_status.mode,
            "detail": market_status.detail,
            "remediation": market_status.remediation,
            "unresolved_mappings": market_status.unresolved_mappings,
        },
        data_provider_setting=settings.data_provider,
        market_provider_setting=settings.market_provider,
        counts={
            "properties": count(Property),
            "rooms": count(Room),
            "stay_dates": count(StayDateInventory),
            "bookings": count(Booking),
            "market_observations": count(MarketObservation),
            "recommendations": count(PricingRecommendation),
            "decisions": count(OperatorDecision),
        },
        override_reasons=OVERRIDE_REASONS,
        demo_mode=settings.data_provider == "mock",
        last_run_id=latest_run_id(session),
    )


@router.post("/sync")
def sync(session: Session = Depends(get_session), regenerate: bool = True):
    """Re-pull the portfolio and market data from the configured providers."""
    today = date.today()
    start, end = default_window(today, HISTORY_DAYS, HORIZON_DAYS)

    pms = get_pms_provider(today=today)
    pms_report = sync_pms(session, pms, start=start, end=end)
    fallback_used = False
    if not pms_report.ok:
        # Graceful degradation: never leave the operator with an empty product.
        fallback_used = True
        pms_report = sync_pms(session, get_pms_provider("mock", today=today), start=start, end=end)

    market = get_market_provider(today=today)
    market_report = sync_market(session, market, start=start, end=end)

    run = generate_recommendations(session, today=today) if regenerate else None
    return {
        "pms": pms_report.as_dict(),
        "pms_fallback_to_mock": fallback_used,
        "market": market_report.as_dict(),
        "run": run.as_dict() if run else None,
    }


@router.post("/demo/reset")
def reset_demo(session: Session = Depends(get_session)):
    """Rebuild the whole demo dataset from scratch."""
    from ..seed import bootstrap

    session.close()
    summary = bootstrap(force=True, quiet=True)
    return {"ok": True, "summary": summary}
