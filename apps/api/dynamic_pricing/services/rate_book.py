"""SeasonalRateBook persistence — CLIENT-VALIDATED data.

Seeded from the client document and editable by the operator, but kept in its
own table (and its own Settings section) so validated business fact is never
mixed with the unvalidated experimental strategy.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SeasonalRateBand
from ..pricing.rate_book import (
    CLIENT_RATE_TABLE,
    RATE_BASIS,
    RATE_BOOK_SOURCE,
    SEASON_LABELS,
    SEASON_NOTES,
    SEASONS,
    SeasonalRateBook,
)

_SEASON_MONTHS = {s["key"]: s["months"] for s in SEASONS}


def ensure_rate_book(session: Session) -> int:
    """Seed the validated rate bands if absent. Idempotent."""
    existing = session.scalar(select(SeasonalRateBand).limit(1))
    if existing is not None:
        return 0

    created = 0
    for (season_key, category), (minimum, base, maximum) in CLIENT_RATE_TABLE.items():
        session.add(
            SeasonalRateBand(
                season_key=season_key,
                season_label=SEASON_LABELS[season_key],
                months=_SEASON_MONTHS[season_key],
                room_category=category,
                min_net_rate=float(minimum),
                base_net_rate=float(base),
                max_net_rate=float(maximum),
                rate_basis=RATE_BASIS,
                source=RATE_BOOK_SOURCE,
                note=SEASON_NOTES.get(season_key) or None,
            )
        )
        created += 1
    session.commit()
    return created


def load_rate_book(session: Session) -> SeasonalRateBook:
    """Build the lookup from persisted rows, falling back to the client table."""
    rows = list(session.scalars(select(SeasonalRateBand)).all())
    if not rows:
        return SeasonalRateBook()
    return SeasonalRateBook.from_rows(rows)


def list_bands(session: Session) -> list[SeasonalRateBand]:
    return list(
        session.scalars(
            select(SeasonalRateBand).order_by(
                SeasonalRateBand.season_key, SeasonalRateBand.room_category
            )
        ).all()
    )


def update_band(
    session: Session, band_id: int, *, min_net_rate: float, base_net_rate: float, max_net_rate: float
) -> SeasonalRateBand | None:
    """Operator edit. Marks the row as operator-modified so provenance is kept."""
    row = session.get(SeasonalRateBand, band_id)
    if row is None:
        return None
    row.min_net_rate = float(min_net_rate)
    row.base_net_rate = float(base_net_rate)
    row.max_net_rate = float(max_net_rate)
    original = CLIENT_RATE_TABLE.get((row.season_key, row.room_category))
    if original and (float(min_net_rate), float(base_net_rate), float(max_net_rate)) != tuple(
        float(v) for v in original
    ):
        row.source = "OPERATOR_EDITED"
    else:
        row.source = RATE_BOOK_SOURCE
    session.commit()
    session.refresh(row)
    return row


def reset_rate_book(session: Session) -> int:
    """Restore every band to the client-validated values."""
    restored = 0
    for row in list_bands(session):
        original = CLIENT_RATE_TABLE.get((row.season_key, row.room_category))
        if not original:
            continue
        row.min_net_rate, row.base_net_rate, row.max_net_rate = (float(v) for v in original)
        row.source = RATE_BOOK_SOURCE
        restored += 1
    session.commit()
    return restored
