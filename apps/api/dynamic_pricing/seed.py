"""Database bootstrap: schema -> rate book -> portfolio -> market -> events -> recommendations.

Idempotent-ish by design: ``bootstrap()`` skips the work if data already
exists, so ``make dev`` is safe to run repeatedly. ``--force`` rebuilds.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, init_db
from .models import (
    Booking,
    Competitor,
    Event,
    MarketObservation,
    OperatorDecision,
    PhysicalRoom,
    PricingAdjustment,
    PricingConfiguration,
    PricingRecommendation,
    Property,
    RecommendationOutcome,
    RoomType,
    SeasonalRateBand,
    StayDateInventory,
)
from .providers.market import get_market_provider
from .providers.pms import get_pms_provider
from .providers.pms.mock import HISTORY_DAYS, HORIZON_DAYS
from .services.configuration import get_active_configuration
from .services.outcomes import generate_demo_outcomes
from .services.rate_book import ensure_rate_book
from .services.recommendations import generate_recommendations
from .services.sync import default_window, sync_market, sync_pms

# Manually-curated demo events, offsets from "today". Real events must come
# from the operator — automated event scraping is an explicit non-goal.
DEMO_EVENTS = [
    (16, 18, "Ho Chi Minh City Marathon", "sport", "high", None),
    (30, 32, "Vietnam International Travel Mart", "conference", "medium", None),
    (58, 59, "Saigon River Music Festival", "concert", "medium", None),
    (84, 88, "National Day long weekend", "holiday", "high", None),
]


def has_data(session: Session) -> bool:
    return bool(session.scalar(select(func.count()).select_from(Property)))


def wipe(session: Session) -> None:
    for model in (
        RecommendationOutcome,
        OperatorDecision,
        PricingAdjustment,
        PricingRecommendation,
        PricingConfiguration,
        MarketObservation,
        Competitor,
        Event,
        Booking,
        StayDateInventory,
        PhysicalRoom,
        RoomType,
        SeasonalRateBand,
        Property,
    ):
        session.execute(delete(model))
    session.commit()


def seed_events(session: Session, today: date) -> int:
    if session.scalar(select(func.count()).select_from(Event)):
        return 0
    prop = session.scalars(select(Property)).first()
    created = 0
    for start_off, end_off, name, event_type, impact, adjustment in DEMO_EVENTS:
        session.add(
            Event(
                property_id=prop.id if prop else None,
                name=name,
                start_date=today + timedelta(days=start_off),
                end_date=today + timedelta(days=end_off),
                impact_level=impact,
                adjustment_pct=adjustment,
                event_type=event_type,
                source="demo",
                notes="Demo event — replace with the operator's real event calendar.",
            )
        )
        created += 1
    session.commit()
    return created


def bootstrap(force: bool = False, today: date | None = None, quiet: bool = False) -> dict:
    """Create the schema and populate demo data if needed."""
    settings = get_settings()
    today = today or date.today()
    init_db()

    def log(message: str) -> None:
        if not quiet:
            print(f"  {message}")

    summary: dict = {"today": today.isoformat(), "skipped": False}

    with SessionLocal() as session:
        if has_data(session) and not force:
            summary["skipped"] = True
            log("Existing data found — leaving it alone (use --force to rebuild).")
            return summary

        if force:
            log("Wiping existing data…")
            wipe(session)

        start, end = default_window(today, HISTORY_DAYS, HORIZON_DAYS)

        # --- 1. CLIENT-VALIDATED rate book --------------------------------
        bands = ensure_rate_book(session)
        summary["rate_bands"] = bands
        log(f"Seasonal Rate Book: {bands} CLIENT_VALIDATED bands (NET rates).")

        # --- 2. experimental dynamic strategy ------------------------------
        config = get_active_configuration(session)
        summary["config_version"] = config.version
        log(f"Dynamic strategy v{config.version} ({config.label}) — UNVALIDATED.")

        # --- 3. portfolio ---------------------------------------------------
        pms = get_pms_provider(today=today)
        pms_report = sync_pms(session, pms, start=start, end=end)
        summary["pms"] = pms_report.as_dict()
        if not pms_report.ok:
            log(f"! {pms.name} unavailable: {pms_report.message}")
            log("  Falling back to the mock provider so demo mode still works.")
            pms = get_pms_provider("mock", today=today)
            pms_report = sync_pms(session, pms, start=start, end=end)
            summary["pms_fallback"] = pms_report.as_dict()
        log(
            f"Portfolio: {pms_report.room_types} room types, "
            f"{pms_report.physical_rooms} apartments, "
            f"{pms_report.inventory} stay-date rows, {pms_report.bookings} bookings."
        )

        # --- 4. events -------------------------------------------------------
        events = seed_events(session, today)
        summary["events"] = events
        log(f"Events: {events} demo events (manually curated).")

        # --- 5. market -------------------------------------------------------
        market = get_market_provider(today=today)
        market_report = sync_market(session, market, start=start, end=end)
        summary["market"] = market_report.as_dict()
        if market_report.ok:
            log(f"Market: {market_report.market_observations} observations via {market.name}.")
        else:
            log(f"! Market provider unavailable: {market_report.message}")
            log("  Recommendations will use a neutral market adjustment.")

        # --- 6. recommendations ----------------------------------------------
        run = generate_recommendations(session, today=today)
        summary["run"] = run.as_dict()
        log(
            f"Generated {run.created} recommendations "
            f"(engine {run.engine_version}, config v{run.config_version}, mode={run.mode})."
        )

        # --- 7. synthetic outcomes for past dates ----------------------------
        outcomes = generate_demo_outcomes(session, today=today)
        summary["outcomes"] = outcomes
        if outcomes:
            log(f"Outcomes: {outcomes} SYNTHETIC demo outcomes (flagged, not real data).")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo database.")
    parser.add_argument("--force", action="store_true", help="wipe and rebuild all data")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    print("Dynamic Pricing Property — database bootstrap")
    summary = bootstrap(force=args.force, quiet=args.quiet)
    print("Done (no changes)." if summary.get("skipped") else "Done.")


if __name__ == "__main__":
    main()
