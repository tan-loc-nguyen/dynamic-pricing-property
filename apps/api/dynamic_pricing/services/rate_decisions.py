"""Record one decision per night for a whole date range.

The Rate page prices a RANGE and accepts it in one action, but a decision still
belongs to a stay date -- that is what Shadow Mode measures and what an outcome
attaches to. So a bulk action writes one row per night and ties them together
with a group id, which is what lets the activity log show a fortnight as one
entry instead of fourteen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import (
    DECISION_ACCEPTED,
    DECISION_OVERRIDDEN,
    STATUS_ACCEPTED,
    STATUS_ERROR,
    STATUS_OVERRIDDEN,
)
from ..models import OperatorDecision, PricingRecommendation, StayDateInventory
from .recommendations import latest_run_id


@dataclass(frozen=True)
class BulkResult:
    group_id: str
    net_rate: float
    decisions_written: int
    nights: int
    skipped_unpriced: int


def apply_to_range(
    session: Session,
    *,
    room_type_id: int,
    start: date,
    end: date,
    net_rate: float,
    decision: str,
    reason_code: str | None = None,
    note: str | None = None,
    operator: str = "demo-operator",
) -> BulkResult:
    """Write ``net_rate`` to every priced night in the range.

    Existing decisions are REPLACED without prompting -- the operator asked for
    a bulk action and gets one. A night the engine could not price is skipped
    rather than given a fabricated decision, because the audit trail is the one
    dataset this product cannot afford noise in, and it is REPORTED rather than
    passed over silently.
    """
    run_id = latest_run_id(session)
    rows = (
        list(
            session.scalars(
                select(PricingRecommendation).where(
                    PricingRecommendation.run_id == run_id,
                    PricingRecommendation.room_type_id == room_type_id,
                    PricingRecommendation.stay_date >= start,
                    PricingRecommendation.stay_date <= end,
                )
            ).all()
        )
        if run_id
        else []
    )

    inventory = {
        row.stay_date: row
        for row in session.scalars(
            select(StayDateInventory).where(
                StayDateInventory.room_type_id == room_type_id,
                StayDateInventory.stay_date >= start,
                StayDateInventory.stay_date <= end,
            )
        ).all()
    }

    group_id = uuid.uuid4().hex
    status = STATUS_ACCEPTED if decision == DECISION_ACCEPTED else STATUS_OVERRIDDEN
    written = 0
    skipped = 0

    for rec in rows:
        if rec.status == STATUS_ERROR:
            skipped += 1
            continue
        held = inventory.get(rec.stay_date)
        previous = held.current_net_rate if held else rec.current_net_rate
        if held:
            # SHADOW MODE: our own view only. Blue Jay stays the system of
            # record; the operator applies the rate there.
            held.current_net_rate = net_rate
        session.add(
            OperatorDecision(
                recommendation_id=rec.id,
                decision=decision,
                recommended_net_rate=rec.recommended_net_rate,
                final_net_rate=net_rate,
                previous_net_rate=previous,
                reason_code=reason_code,
                note=note,
                engine_version=rec.engine_version,
                config_version=rec.config_version,
                operator=operator,
                group_id=group_id,
            )
        )
        rec.status = status
        written += 1

    session.commit()
    return BulkResult(
        group_id=group_id,
        net_rate=net_rate,
        decisions_written=written,
        nights=len(rows),
        skipped_unpriced=skipped,
    )


__all__ = ["BulkResult", "apply_to_range", "DECISION_ACCEPTED", "DECISION_OVERRIDDEN"]
