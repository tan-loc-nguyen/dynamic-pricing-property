"""RecommendationService — orchestrates one pricing run and persists results.

    inventory rows -> FeatureEngine -> PricingEngine -> persisted recommendations

The service knows nothing about *how* prices are computed. Swapping the engine
is a single ``get_engine(key)`` lookup.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..features.engine import FeatureEngine
from ..models import (
    PricingAdjustment,
    PricingRecommendation,
    Room,
    StayDateInventory,
)
from ..pricing import get_engine
from .configuration import get_active_configuration


@dataclass
class RunReport:
    run_id: str
    engine_version: str
    config_version: int
    created: int
    carried_over: int
    skipped: int

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "engine_version": self.engine_version,
            "config_version": self.config_version,
            "created": self.created,
            "carried_over": self.carried_over,
            "skipped": self.skipped,
        }


def latest_run_id(session: Session) -> str | None:
    return session.scalars(
        select(PricingRecommendation.run_id).order_by(PricingRecommendation.created_at.desc())
    ).first()


def generate_recommendations(
    session: Session,
    *,
    today: date | None = None,
    engine_key: str = "v1",
    horizon_days: int = 60,
) -> RunReport:
    """Run the pricing engine across every active room x future stay date."""
    today = today or date.today()
    config_row = get_active_configuration(session)
    config = config_row.payload
    engine = get_engine(engine_key)

    previous_run = latest_run_id(session)
    previous: dict[tuple[int, date], PricingRecommendation] = {}
    if previous_run:
        for rec in session.scalars(
            select(PricingRecommendation).where(PricingRecommendation.run_id == previous_run)
        ).all():
            previous[(rec.room_id, rec.stay_date)] = rec

    active_room_ids = {
        r.id for r in session.scalars(select(Room).where(Room.is_active.is_(True))).all()
    }

    inventories = list(
        session.scalars(
            select(StayDateInventory)
            .where(StayDateInventory.stay_date >= today)
            .order_by(StayDateInventory.stay_date, StayDateInventory.room_id)
        ).all()
    )
    inventories = [inv for inv in inventories if inv.room_id in active_room_ids]

    features = FeatureEngine(session, config, today=today).prepare()

    run_id = uuid.uuid4().hex[:16]
    created = carried_over = skipped = 0

    for inventory in inventories:
        context = features.build(inventory)
        try:
            result = engine.calculate(context, config)
        except Exception:  # noqa: BLE001 - one bad row must not kill the run
            skipped += 1
            continue

        rec = PricingRecommendation(
            run_id=run_id,
            property_id=context.property_id,
            room_id=context.room_id,
            stay_date=context.stay_date,
            base_price=result.base_price,
            current_price=result.current_price,
            price_before_bounds=result.price_before_bounds,
            recommended_price=result.recommended_price,
            change_pct=result.change_pct,
            total_multiplier=result.total_multiplier,
            explanation=result.explanation,
            engine_version=result.engine_version,
            config_version=config_row.version,
            features=context.to_dict(),
            extra=result.metadata,
            status="pending",
        )

        # Carry a prior decision forward ONLY when the recommendation is
        # unchanged. If the number moved, the operator must review it again.
        # (docs/DECISIONS.md D7)
        prior = previous.get((context.room_id, context.stay_date))
        if (
            prior is not None
            and prior.status in ("accepted", "overridden")
            and abs(prior.recommended_price - result.recommended_price) < 1e-6
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
                    factor=adj.factor,
                    price_before=adj.price_before,
                    price_after=adj.price_after,
                    delta=adj.delta,
                    reason=adj.reason,
                    is_neutral=adj.is_neutral,
                )
            )

        # NOTE: decision rows are deliberately NOT copied onto the new
        # recommendation. A decision is a historical fact that happened once;
        # duplicating it per run would inflate the audit trail on every
        # recalculation. Decisions stay attached to the recommendation the
        # operator actually acted on and are looked up by (room, stay_date).

        created += 1

    session.commit()
    return RunReport(
        run_id=run_id,
        engine_version=engine.version,
        config_version=config_row.version,
        created=created,
        carried_over=carried_over,
        skipped=skipped,
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
            .order_by(PricingRecommendation.stay_date, PricingRecommendation.room_id)
        ).all()
    )


def preview_price(
    session: Session,
    *,
    config: dict,
    room_id: int | None = None,
    stay_date: date | None = None,
    today: date | None = None,
    engine_key: str = "v1",
):
    """Price a single stay date against an unsaved configuration.

    Powers the Settings live preview: the operator sees the effect of a change
    before committing it.
    """
    today = today or date.today()
    query = select(StayDateInventory).where(StayDateInventory.stay_date >= today)
    if room_id:
        query = query.where(StayDateInventory.room_id == room_id)
    if stay_date:
        query = query.where(StayDateInventory.stay_date == stay_date)
    inventory = session.scalars(
        query.order_by(StayDateInventory.stay_date, StayDateInventory.room_id)
    ).first()
    if inventory is None:
        return None, None

    features = FeatureEngine(session, config, today=today).prepare()
    context = features.build(inventory)
    result = get_engine(engine_key).calculate(context, config)
    return context, result
