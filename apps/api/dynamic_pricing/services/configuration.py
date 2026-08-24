"""EXPERIMENTAL dynamic-strategy configuration lifecycle.

Only the unvalidated dynamic layer lives here. The client-validated
SeasonalRateBook is managed separately in ``services/rate_book.py`` so the
two categories can never be confused.

Original notes follow.

Every save creates a NEW version rather than mutating the active row, so any
past recommendation can always be traced back to the exact rule set that
produced it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PricingConfiguration
from ..pricing.defaults import default_config, prepare_config


def get_active_configuration(session: Session) -> PricingConfiguration:
    row = session.scalars(
        select(PricingConfiguration).where(PricingConfiguration.is_active.is_(True))
    ).first()
    if row is None:
        row = create_configuration(
            session,
            default_config(),
            label="demo-defaults",
            note="Seeded provisional demo assumptions. All values UNVALIDATED.",
        )
    return row


def create_configuration(
    session: Session,
    payload: dict,
    *,
    label: str = "operator-edit",
    note: str | None = None,
) -> PricingConfiguration:
    """Persist a new active configuration version.

    Rejects a configuration that would price incorrectly rather than saving it
    and discovering the problem one pricing run later.
    """
    # merge -> coerce numeric leaves -> validate logic. Raises
    # ConfigurationInvalid listing every bad field path.
    merged = prepare_config(payload)

    latest = session.scalars(
        select(PricingConfiguration).order_by(PricingConfiguration.version.desc())
    ).first()
    next_version = (latest.version + 1) if latest else 1

    for row in session.scalars(
        select(PricingConfiguration).where(PricingConfiguration.is_active.is_(True))
    ).all():
        row.is_active = False

    config = PricingConfiguration(
        version=next_version,
        label=label,
        payload=merged,
        is_active=True,
        note=note,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def reset_to_defaults(session: Session) -> PricingConfiguration:
    return create_configuration(
        session,
        default_config(),
        label="demo-defaults",
        note="Reset to provisional demo defaults.",
    )


def list_configurations(session: Session, limit: int = 25) -> list[PricingConfiguration]:
    return list(
        session.scalars(
            select(PricingConfiguration)
            .order_by(PricingConfiguration.version.desc())
            .limit(limit)
        ).all()
    )


def activate_configuration(session: Session, config_id: int) -> PricingConfiguration | None:
    """Make one existing version active again.

    Used to roll back an activation when the newly-saved config turns out to be
    unusable, so the app is never left advertising a version it cannot price
    with.
    """
    target = session.get(PricingConfiguration, config_id)
    if target is None:
        return None
    for row in session.scalars(
        select(PricingConfiguration).where(PricingConfiguration.is_active.is_(True))
    ).all():
        row.is_active = False
    target.is_active = True
    session.commit()
    session.refresh(target)
    return target
