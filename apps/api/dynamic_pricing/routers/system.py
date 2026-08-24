"""System status, portfolio listing, and demo controls."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..constants import (
    CONFIDENCE_LEVELS,
    EVENT_IMPACT_LEVELS,
    EVENT_TYPES,
    INCLUSION_OPTIONS,
    MODE_SHADOW,
    OVERRIDE_REASONS,
    PRICE_BASES,
    PROMOTION_OPTIONS,
)
from ..db import get_session
from ..lookup import UnknownRegistryKey
from ..models import (
    Booking,
    Competitor,
    Event,
    MarketObservation,
    OperatorDecision,
    PhysicalRoom,
    PricingRecommendation,
    Property,
    RecommendationOutcome,
    RoomType,
    SeasonalRateBand,
    StayDateInventory,
)
from ..pricing import DEFAULT_ENGINE, RATE_BOOK_SOURCE, ROOM_CATEGORIES, SEASONS, get_engine, list_engines
from ..providers.market import get_market_provider
from ..providers.pms import get_pms_provider
from ..providers.pms.base import ProviderStatus
from ..providers.pms.mock import HISTORY_DAYS, HORIZON_DAYS
from ..schemas import PropertyOut, SystemStatusOut
from ..services.configuration import get_active_configuration
from ..services.outcomes import outcome_summary
from ..services.recommendations import (
    PricingRunFailed,
    generate_recommendations,
    latest_run_id,
)
from ..services.sync import default_window, sync_market, sync_pms
from ._shared import category_label

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
            room_types=[
                {
                    "id": rt.id,
                    "external_id": rt.external_id,
                    "name": rt.name,
                    "category": rt.category,
                    "category_label": category_label(rt.category),
                    "capacity": rt.capacity,
                    "units_total": rt.units_total,
                    "is_active": rt.is_active,
                    "physical_rooms": [
                        {
                            "id": u.id,
                            "external_id": u.external_id,
                            "unit_label": u.unit_label,
                            "floor": u.floor,
                            "is_active": u.is_active,
                        }
                        for u in sorted(rt.physical_rooms, key=lambda x: x.unit_label)
                    ],
                }
                for rt in sorted(p.room_types, key=lambda x: x.name)
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
    engine = get_engine(DEFAULT_ENGINE)

    def _provider_status(getter, kind: str, configured: str):
        """Report an unrecognised provider name instead of crashing on it.

        /api/status must stay available precisely when the configuration is
        wrong -- it is where an operator looks to find out that it is.
        """
        try:
            return getter().status()
        except UnknownRegistryKey as exc:
            return ProviderStatus(
                name=f"unknown ({configured})",
                healthy=False,
                mode="unconfigured",
                detail=str(exc),
                remediation=f"Set a valid {kind} in .env, then restart the API.",
            )

    settings_ = get_settings()
    pms_status = _provider_status(get_pms_provider, "DATA_PROVIDER", settings_.data_provider)
    market_status = _provider_status(
        get_market_provider, "MARKET_PROVIDER", settings_.market_provider
    )

    def count(model) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    from ..features.booking_curve import get_booking_curve_provider

    curve = get_booking_curve_provider(config.payload)

    return SystemStatusOut(
        api_version=__version__,
        mode=str(config.payload.get("mode", MODE_SHADOW)),
        engine={
            "key": DEFAULT_ENGINE,
            "name": engine.name,
            "version": engine.version,
            "description": engine.description,
        },
        available_engines=list_engines(),
        booking_curve={
            "name": curve.name,
            "validated": curve.validated,
            "note": (
                "Demo curve — NOT Luminous data. Replace with historical curves once "
                "booking history is available."
            )
            if not curve.validated
            else "",
        },
        rate_book={
            "source": RATE_BOOK_SOURCE,
            "rate_basis": "NET",
            "bands": count(SeasonalRateBand),
            "seasons": len(SEASONS),
            "categories": len(ROOM_CATEGORIES),
        },
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
            "room_types": count(RoomType),
            "physical_rooms": count(PhysicalRoom),
            "rate_bands": count(SeasonalRateBand),
            "stay_dates": count(StayDateInventory),
            "bookings": count(Booking),
            "events": count(Event),
            "competitors": count(Competitor),
            "market_observations": count(MarketObservation),
            # ALL runs, including the demo-only historical backfill -- not the
            # current run. Rate Review shows the current run only.
            "recommendations_all_runs": count(PricingRecommendation),
            "decisions": count(OperatorDecision),
            "outcomes": count(RecommendationOutcome),
        },
        override_reasons=OVERRIDE_REASONS,
        vocabularies={
            "room_categories": ROOM_CATEGORIES,
            "seasons": SEASONS,
            "confidence_levels": CONFIDENCE_LEVELS,
            "price_bases": PRICE_BASES,
            "inclusion_options": INCLUSION_OPTIONS,
            "promotion_options": PROMOTION_OPTIONS,
            "event_impact_levels": EVENT_IMPACT_LEVELS,
            "event_types": EVENT_TYPES,
        },
        outcome_readiness=outcome_summary(session),
        demo_mode=settings.data_provider == "mock",
        last_run_id=latest_run_id(session),
    )


@router.post("/sync")
def sync(session: Session = Depends(get_session), regenerate: bool = True):
    """Re-pull the portfolio and market data from the configured providers."""
    today = date.today()
    start, end = default_window(today, HISTORY_DAYS, HORIZON_DAYS)

    try:
        pms = get_pms_provider(today=today)
    except UnknownRegistryKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pms_report = sync_pms(session, pms, start=start, end=end)
    fallback_used = False
    if not pms_report.ok:
        # Graceful degradation: never leave the operator with an empty product.
        fallback_used = True
        pms_report = sync_pms(session, get_pms_provider("mock", today=today), start=start, end=end)

    try:
        market = get_market_provider(today=today)
    except UnknownRegistryKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    market_report = sync_market(session, market, start=start, end=end)

    run = None
    run_error = None
    if regenerate:
        try:
            run = generate_recommendations(session, today=today)
        except PricingRunFailed as exc:
            # Sync must not fail wholesale because pricing is misconfigured --
            # the freshly synced portfolio is still worth keeping.
            run_error = str(exc)
    return {
        "pms": pms_report.as_dict(),
        "pms_fallback_to_mock": fallback_used,
        "market": market_report.as_dict(),
        "run": run.as_dict() if run else None,
        "run_error": run_error,
    }


@router.post("/demo/reset")
def reset_demo(session: Session = Depends(get_session)):
    """Rebuild the whole demo dataset from scratch."""
    from ..seed import bootstrap

    session.close()
    return {"ok": True, "summary": bootstrap(force=True, quiet=True)}
