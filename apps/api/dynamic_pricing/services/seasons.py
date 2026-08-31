"""Persisted, operator-editable seasons.

The client calendar is the seed, not the ceiling: an operator can redraw the
year, and the Rate page's picker and the pricing engine both follow. The
partition rule is enforced here rather than in the form, because a form is a
convenience and this is an invariant -- a month covered by no season leaves
those dates with no validated band.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Season
from ..pricing.rate_book import SEASONS, season_bounds_in
from ..pricing.seasons import PartitionError, validate_partition


def ensure_seasons(session: Session) -> int:
    """Seed the client calendar if absent. Idempotent."""
    if session.scalar(select(Season).limit(1)) is not None:
        return 0
    for position, season in enumerate(SEASONS):
        session.add(
            Season(
                key=season["key"],
                label=season["label"],
                months=list(season["months"]),
                position=position,
            )
        )
    session.commit()
    return len(SEASONS)


def season_calendar(session: Session) -> list[dict]:
    """The active calendar, falling back to the client one when unseeded."""
    rows = list(session.scalars(select(Season).order_by(Season.position, Season.id)).all())
    if not rows:
        return [dict(s) for s in SEASONS]
    return [{"key": r.key, "label": r.label, "months": list(r.months)} for r in rows]


def save_seasons(session: Session, seasons: list[dict]) -> list[dict]:
    """Replace the calendar wholesale, or raise PartitionError.

    Wholesale because the partition is a property of the WHOLE year: validating
    one season in isolation cannot see the gap its edit opened next door.
    """
    validate_partition(seasons)  # raises before anything is written

    existing = {r.key: r for r in session.scalars(select(Season)).all()}
    keep: set[str] = set()
    for position, season in enumerate(seasons):
        key = str(season["key"])
        keep.add(key)
        row = existing.get(key) or Season(key=key)
        row.label = str(season.get("label") or key)
        row.months = [int(m) for m in season["months"]]
        row.position = position
        session.add(row)
    for key, row in existing.items():
        if key not in keep:
            session.delete(row)
    session.commit()
    return season_calendar(session)


def season_on(session: Session, day: date) -> dict:
    """Which season a date falls in, and the days it runs between."""
    calendar = season_calendar(session)
    key = next(
        (s["key"] for s in calendar if day.month in (s.get("months") or [])),
        None,
    )
    if key is None:
        # Unreachable while the partition holds, and reported rather than
        # guessed if it ever does not.
        raise PartitionError(f"No season covers month {day.month}.")
    season = next(s for s in calendar if s["key"] == key)
    start, end = season_bounds_in(day, [int(m) for m in season["months"]])
    return {"key": key, "label": season["label"], "start": start, "end": end}
