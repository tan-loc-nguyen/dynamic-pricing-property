"""Database bootstrap: schema -> rate book -> portfolio -> market -> events -> recommendations.

Idempotent-ish by design: ``bootstrap()`` skips the work if data already
exists, so ``make dev`` is safe to run repeatedly. ``--force`` rebuilds.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .lookup import UnknownRegistryKey
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
from .pricing import get_engine
from .providers.market import get_market_provider
from .providers.pms import get_pms_provider
from .services.integration import get_category_map, get_pms_source
from .providers.pms.mock import HISTORY_DAYS, HORIZON_DAYS
from .services.configuration import get_active_configuration
from .services.outcomes import generate_demo_outcomes
from .services.rate_book import ensure_rate_book
from .services.seasons import ensure_seasons
from .services.recommendations import PricingRunFailed, generate_recommendations
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


def refresh_stale_run(session, today: date | None = None) -> bool:
    """Regenerate if the stored run came from a different engine build.

    The engine persists `params` on every adjustment, and those keys are part of
    its output contract: rename one and every stored row becomes unrenderable,
    because ICU refuses a message whose argument is missing. Nothing that runs
    the engine can catch that — fresh rows are always self-consistent — so the
    check is against what the DATABASE says produced it.

    `engine_version` recorded exactly this all along and nothing was reading it.
    Cheap, and it makes a demo laptop carrying an older database self-healing
    rather than showing an empty breakdown.
    """
    current = get_engine().version
    latest = session.scalars(
        select(PricingRecommendation).order_by(PricingRecommendation.id.desc()).limit(1)
    ).first()
    if latest is None or latest.engine_version == current:
        return False
    generate_recommendations(session, today=today)
    return True


def bootstrap(force: bool = False, today: date | None = None, quiet: bool = False) -> dict:
    """Create the schema and populate demo data if needed."""
    today = today or date.today()
    init_db()

    def log(message: str) -> None:
        if not quiet:
            print(f"  {message}")

    summary: dict = {"today": today.isoformat(), "skipped": False}

    with SessionLocal() as session:
        if has_data(session) and not force:
            summary["skipped"] = True
            if refresh_stale_run(session, today=today):
                summary["regenerated"] = True
                log("Existing data was priced by an older engine — recommendations regenerated.")
            else:
                log("Existing data found — leaving it alone (use --force to rebuild).")
            return summary

        if force:
            log("Wiping existing data…")
            wipe(session)

        start, end = default_window(today, HISTORY_DAYS, HORIZON_DAYS)

        # --- 1. CLIENT-VALIDATED rate book --------------------------------
        # Seasons FIRST: the rate book's calendar is read from them.
        ensure_seasons(session)
        bands = ensure_rate_book(session)
        summary["rate_bands"] = bands
        log(f"Seasonal Rate Book: {bands} CLIENT_VALIDATED bands (NET rates).")

        # --- 2. experimental dynamic strategy ------------------------------
        config = get_active_configuration(session)
        summary["config_version"] = config.version
        log(f"Dynamic strategy v{config.version} ({config.label}) — UNVALIDATED.")

        # --- 3. portfolio ---------------------------------------------------
        try:
            pms = get_pms_provider(
                get_pms_source(session), today=today, category_map=get_category_map(session)
            )
        except UnknownRegistryKey as exc:
            # Say it out loud, then keep the demo working. Silently running the
            # mock is how a typo in DATA_PROVIDER goes unnoticed for a week.
            log(f"! {exc}")
            log("  Falling back to the mock provider.")
            summary["pms_key_error"] = str(exc)
            pms = get_pms_provider("mock", today=today)

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
        try:
            market = get_market_provider(today=today)
        except UnknownRegistryKey as exc:
            log(f"! {exc}")
            log("  Falling back to the mock market provider.")
            summary["market_key_error"] = str(exc)
            market = get_market_provider("mock", today=today)

        market_report = sync_market(session, market, start=start, end=end)
        summary["market"] = market_report.as_dict()
        if market_report.ok:
            log(f"Market: {market_report.market_observations} observations via {market.name}.")
        else:
            log(f"! Market provider unavailable: {market_report.message}")
            log("  Recommendations will use a neutral market adjustment.")

        # --- 6a. historical run (DEMO ONLY) -----------------------------------
        # Priced first so it is never the "latest" run, and so the synthetic
        # outcomes below have past recommendations to attach to. Without this
        # the entire outcome-tracking path is unreachable in demo mode.
        # Demo-only, so a failure here must never abort the bootstrap: properties
        # are already committed, and has_data() would then skip the rebuild on
        # every subsequent start, permanently serving a portfolio with no
        # recommendations.
        try:
            history_run = generate_recommendations(
                session,
                today=today,
                stay_date_from=start,
                stay_date_to=today - timedelta(days=1),
            )
            summary["history_run"] = history_run.as_dict()
            log(f"Backfilled {history_run.created} historical recommendations (demo only).")
        except PricingRunFailed as exc:
            summary["history_run_error"] = str(exc)
            log(f"! Historical backfill skipped: {exc}")

        # --- 6b. live recommendations ------------------------------------------
        try:
            run = generate_recommendations(session, today=today)
            summary["run"] = run.as_dict()
        except PricingRunFailed as exc:
            # Leave the database in a state the next start will rebuild from,
            # rather than one has_data() considers complete.
            summary["run_error"] = str(exc)
            log(f"! Pricing failed: {exc}")
            log("  Wiping so the next start rebuilds rather than serving an empty portfolio.")
            wipe(session)
            return summary
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
