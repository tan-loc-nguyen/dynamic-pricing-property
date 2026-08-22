"""Database bootstrap: schema -> portfolio -> market data -> recommendations.

Idempotent-ish by design: ``bootstrap()`` skips the work if data already
exists, so ``make dev`` is safe to run repeatedly. ``--force`` rebuilds.
"""

from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, engine, init_db
from .models import (
    Base,
    Booking,
    MarketObservation,
    OperatorDecision,
    PricingAdjustment,
    PricingConfiguration,
    PricingRecommendation,
    Property,
    Room,
    StayDateInventory,
)
from .providers.market import get_market_provider
from .providers.pms import get_pms_provider
from .providers.pms.mock import HISTORY_DAYS, HORIZON_DAYS
from .services.configuration import get_active_configuration
from .services.recommendations import generate_recommendations
from .services.sync import default_window, sync_market, sync_pms


def has_data(session: Session) -> bool:
    return bool(session.scalar(select(func.count()).select_from(Property)))


def wipe(session: Session) -> None:
    for model in (
        OperatorDecision,
        PricingAdjustment,
        PricingRecommendation,
        PricingConfiguration,
        MarketObservation,
        Booking,
        StayDateInventory,
        Room,
        Property,
    ):
        session.execute(delete(model))
    session.commit()


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

        config = get_active_configuration(session)
        summary["config_version"] = config.version
        log(f"Pricing configuration v{config.version} ({config.label}) active.")

        # --- PMS -------------------------------------------------------
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
            f"Portfolio: {pms_report.properties} properties, {pms_report.rooms} rooms, "
            f"{pms_report.inventory} stay-date rows, {pms_report.bookings} bookings."
        )

        # --- Market ----------------------------------------------------
        market = get_market_provider(today=today)
        market_report = sync_market(session, market, start=start, end=end)
        summary["market"] = market_report.as_dict()
        if market_report.ok:
            log(f"Market: {market_report.market_observations} observations via {market.name}.")
        else:
            log(f"! Market provider unavailable: {market_report.message}")
            log("  Recommendations will use a neutral market factor.")

        # --- Recommendations -------------------------------------------
        run = generate_recommendations(session, today=today, horizon_days=HORIZON_DAYS)
        summary["run"] = run.as_dict()
        log(
            f"Generated {run.created} recommendations "
            f"(engine {run.engine_version}, config v{run.config_version})."
        )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo database.")
    parser.add_argument("--force", action="store_true", help="wipe and rebuild all data")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    print("Dynamic Pricing Property — database bootstrap")
    summary = bootstrap(force=args.force, quiet=args.quiet)
    if summary.get("skipped"):
        print("Done (no changes).")
    else:
        print("Done.")


if __name__ == "__main__":
    main()
