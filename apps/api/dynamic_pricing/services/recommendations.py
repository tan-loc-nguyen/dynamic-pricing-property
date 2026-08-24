"""RecommendationService — orchestrates one pricing run and persists snapshots.

    inventory -> FeatureEngine -> PricingEngine -> persisted recommendation

The service knows nothing about *how* rates are computed. Swapping the engine
is a single ``get_engine(key)`` lookup.

Every recommendation stores a full feature snapshot and rate-band snapshot, so
it stays reproducible after the underlying inventory moves on — the basis for
outcome analysis later.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..features.engine import FeatureEngine
from ..constants import STATUS_ERROR
from ..models import (
    PricingAdjustment,
    PricingRecommendation,
    RoomType,
    StayDateInventory,
)
from ..pricing import DEFAULT_ENGINE, get_engine
from .configuration import get_active_configuration
from .rate_book import load_rate_book


# A pricing failure is either about ONE bad inventory row, or about the
# configuration/code — and those need opposite handling. A row-shaped problem
# should be tolerated and shown; a systemic one should stop the run.
#
# We cannot tell them apart by counting failures, because every interesting
# factor in the engine is gated: a broken `market.sensitivity` only reaches the
# rows that HAVE qualified market data, so "all rows failed" never fires. What
# does distinguish them is repetition of the SAME error: 267 rows failing with
# one identical message is a config bug, one row failing alone is a bad row.
SYSTEMIC_ERROR_THRESHOLD = 3


class PricingRunFailed(RuntimeError):
    """The configuration cannot price this portfolio.

    Raised instead of committing a run that would silently drop stay dates.
    Carries the offending error and how many rows it hit.
    """

    def __init__(self, message: str, *, error: str | None = None, affected: int = 0) -> None:
        super().__init__(message)
        self.error = error
        self.affected = affected


@dataclass
class RunReport:
    run_id: str
    engine_version: str
    config_version: int
    mode: str
    created: int
    carried_over: int
    skipped: int
    first_error: str | None = None
    failures: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "engine_version": self.engine_version,
            "config_version": self.config_version,
            "mode": self.mode,
            "created": self.created,
            "carried_over": self.carried_over,
            "skipped": self.skipped,
            "first_error": self.first_error,
            "failures": self.failures,
        }


def latest_run_id(session: Session) -> str | None:
    # id.desc() as an explicit tiebreaker: bootstrap writes two runs back to
    # back, and created_at alone would be ordering-by-luck if they collided.
    return session.scalars(
        select(PricingRecommendation.run_id).order_by(
            PricingRecommendation.created_at.desc(), PricingRecommendation.id.desc()
        )
    ).first()


def generate_recommendations(
    session: Session,
    *,
    today: date | None = None,
    engine_key: str = DEFAULT_ENGINE,
    stay_date_from: date | None = None,
    stay_date_to: date | None = None,
) -> RunReport:
    """Run the pricing engine across every active room type x stay date.

    Defaults to the forward-looking window (today onwards). An explicit window
    is used only to backfill historical runs in demo mode, so that synthetic
    outcomes have past recommendations to attach to.
    """
    today = today or date.today()
    config_row = get_active_configuration(session)
    config = config_row.payload
    engine = get_engine(engine_key)
    mode = str(config.get("mode", "shadow"))

    previous_run = latest_run_id(session)
    previous: dict[tuple[int, date], PricingRecommendation] = {}
    if previous_run:
        for rec in session.scalars(
            select(PricingRecommendation).where(PricingRecommendation.run_id == previous_run)
        ).all():
            previous[(rec.room_type_id, rec.stay_date)] = rec

    active_ids = {
        r.id for r in session.scalars(select(RoomType).where(RoomType.is_active.is_(True))).all()
    }
    window_start = stay_date_from or today
    query = select(StayDateInventory).where(StayDateInventory.stay_date >= window_start)
    if stay_date_to is not None:
        query = query.where(StayDateInventory.stay_date <= stay_date_to)
    inventories = [
        inv
        for inv in session.scalars(
            query.order_by(StayDateInventory.stay_date, StayDateInventory.room_type_id)
        ).all()
        if inv.room_type_id in active_ids
    ]

    features = FeatureEngine(
        session, config, today=today, rate_book=load_rate_book(session)
    ).prepare()

    run_id = uuid.uuid4().hex[:16]
    created = carried_over = skipped = 0
    first_error: str | None = None
    error_signatures: Counter[str] = Counter()
    failures: list[dict] = []

    for inventory in inventories:
        context = features.build(inventory)
        try:
            result = engine.calculate(context, config)
        except Exception as exc:  # noqa: BLE001 - see SYSTEMIC_ERROR_THRESHOLD
            signature = f"{type(exc).__name__}: {exc}"
            skipped += 1
            error_signatures[signature] += 1
            if first_error is None:
                first_error = signature
            failures.append(
                {
                    "room_type_id": context.room_type_id,
                    "room_type_name": context.room_type_name,
                    "stay_date": context.stay_date.isoformat(),
                    "error": signature,
                }
            )

            # The same error repeating across rows is a configuration or code
            # fault, not a bad inventory row. Stop rather than quietly serving
            # a portfolio with stay dates missing from it.
            if error_signatures[signature] >= SYSTEMIC_ERROR_THRESHOLD:
                session.rollback()
                raise PricingRunFailed(
                    f"Pricing failed identically on {error_signatures[signature]} stay dates, so "
                    f"the configuration is unusable and the previous run was kept. Error: {signature}",
                    error=signature,
                    affected=error_signatures[signature],
                ) from exc

            # A one-off failure is tolerated, but the stay date must NOT vanish:
            # an omitted row is indistinguishable from one that was never in
            # scope. Record it in an error state so the operator sees WHICH
            # dates are unpriced, not merely how many.
            session.add(
                PricingRecommendation(
                    run_id=run_id,
                    mode=mode,
                    property_id=context.property_id,
                    room_type_id=context.room_type_id,
                    stay_date=context.stay_date,
                    season_key=context.season_key,
                    band_min_net_rate=context.band_min_net_rate,
                    band_base_net_rate=context.band_base_net_rate,
                    band_max_net_rate=context.band_max_net_rate,
                    base_net_rate=context.band_base_net_rate or context.current_net_rate,
                    current_net_rate=context.current_net_rate,
                    net_rate_before_clamp=context.current_net_rate,
                    recommended_net_rate=context.current_net_rate,
                    change_pct=0.0,
                    total_adjustment_pct=0.0,
                    explanation=f"This stay date could not be priced: {signature}",
                    engine_version=engine.version,
                    config_version=config_row.version,
                    features=context.to_dict(),
                    extra={"error": signature, "unpriced": True},
                    status=STATUS_ERROR,
                )
            )
            continue

        rec = PricingRecommendation(
            run_id=run_id,
            mode=mode,
            property_id=context.property_id,
            room_type_id=context.room_type_id,
            stay_date=context.stay_date,
            season_key=context.season_key,
            band_min_net_rate=context.band_min_net_rate,
            band_base_net_rate=context.band_base_net_rate,
            band_max_net_rate=context.band_max_net_rate,
            base_net_rate=result.base_net_rate,
            current_net_rate=result.current_net_rate,
            net_rate_before_clamp=result.net_rate_before_clamp,
            recommended_net_rate=result.recommended_net_rate,
            change_pct=result.change_pct,
            total_adjustment_pct=result.total_adjustment_pct,
            explanation=result.explanation,
            engine_version=result.engine_version,
            config_version=config_row.version,
            features=context.to_dict(),
            extra=result.metadata,
            status="pending",
        )

        # Carry a prior decision forward ONLY when the recommendation is
        # unchanged. If the number moved, the operator must review it again.
        prior = previous.get((context.room_type_id, context.stay_date))
        if (
            prior is not None
            and prior.status in ("accepted", "overridden")
            and abs(prior.recommended_net_rate - result.recommended_net_rate) < 1e-6
        ):
            rec.status = prior.status
            carried_over += 1

        session.add(rec)
        session.flush()

        for index, adj in enumerate(result.adjustments):
            session.add(
                PricingAdjustment(
                    recommendation_id=rec.id,
                    sequence=index,
                    code=adj.code,
                    label=adj.label,
                    adjustment_pct=adj.adjustment_pct,
                    factor=adj.factor,
                    price_before=adj.price_before,
                    price_after=adj.price_after,
                    delta=adj.delta,
                    reason=adj.reason,
                    is_neutral=adj.is_neutral,
                    is_ignored=adj.is_ignored,
                )
            )

        # Decisions are NOT copied forward: a decision is a historical fact
        # that happened once, and cloning it would inflate the audit trail.
        created += 1

    # NOTE: there is deliberately no "created == 0" check here. It cannot work:
    # every interesting factor in the engine is gated, so a broken setting only
    # reaches the subset of rows that use that factor and `created` stays > 0.
    # Repetition of one error signature is the signal that generalises.

    session.commit()
    return RunReport(
        run_id=run_id,
        engine_version=engine.version,
        config_version=config_row.version,
        mode=mode,
        created=created,
        carried_over=carried_over,
        skipped=skipped,
        first_error=first_error,
        failures=failures,
    )


def load_current_recommendations(session: Session) -> list[PricingRecommendation]:
    run_id = latest_run_id(session)
    if not run_id:
        return []
    return list(
        session.scalars(
            select(PricingRecommendation)
            .where(PricingRecommendation.run_id == run_id)
            .options(
                selectinload(PricingRecommendation.adjustments),
                selectinload(PricingRecommendation.decisions),
            )
            .order_by(PricingRecommendation.stay_date, PricingRecommendation.room_type_id)
        ).all()
    )


def preview_rate(
    session: Session,
    *,
    config: dict,
    room_type_id: int | None = None,
    stay_date: date | None = None,
    today: date | None = None,
    engine_key: str = DEFAULT_ENGINE,
):
    """Price a single stay date against an UNSAVED configuration.

    Powers the Settings live preview: the operator sees the effect of a change
    before committing it.
    """
    today = today or date.today()
    query = select(StayDateInventory).where(StayDateInventory.stay_date >= today)
    if room_type_id:
        query = query.where(StayDateInventory.room_type_id == room_type_id)
    if stay_date:
        query = query.where(StayDateInventory.stay_date == stay_date)
    inventory = session.scalars(
        query.order_by(StayDateInventory.stay_date, StayDateInventory.room_type_id)
    ).first()
    if inventory is None:
        return None, None

    features = FeatureEngine(session, config, today=today, rate_book=load_rate_book(session)).prepare()
    context = features.build(inventory)
    result = get_engine(engine_key).calculate(context, config)
    return context, result
