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

from ..models import Season, SeasonalRateBand
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
            # Bands belong to their season. Left behind they are counted in
            # the rate book, rendered by nothing, and re-adopted by any future
            # season that happens to reuse the key. Client-validated values are
            # recoverable regardless -- resetting the rate book restores them
            # from the validated table.
            for band in session.scalars(
                select(SeasonalRateBand).where(SeasonalRateBand.season_key == key)
            ).all():
                session.delete(band)
    session.commit()
    _seed_bands_for_new_seasons(session, seasons)
    return season_calendar(session)


def _seed_bands_for_new_seasons(session: Session, seasons: list[dict]) -> int:
    """Give a season the operator just added a band per room category.

    Every recommendation anchors on a validated band and is clamped to it, so a
    season with no bands is one the engine quietly falls back for on every date
    it covers -- and the operator has no way to notice, because the panel
    simply renders an empty table.

    Bands are copied from the season that PRECEDES the new one in calendar
    order, which is the season it was split out of: the panel splits the
    longest run at its midpoint, so the new start always lands inside its
    donor's months and sorts immediately after it.

    They are marked OPERATOR_EDITED, never CLIENT_VALIDATED. The numbers are a
    carry-over the engineering side invented, and the rate book is the one
    table this product treats as business fact -- putting a guess in it under
    the client's name is the mistake the whole provenance split exists to
    prevent.
    """
    ordered = [str(s["key"]) for s in seasons]
    having_bands = {
        key for (key,) in session.execute(select(SeasonalRateBand.season_key).distinct()).all()
    }
    missing = [key for key in ordered if key not in having_bands]
    if not missing:
        return 0

    labels = {str(s["key"]): str(s.get("label") or s["key"]) for s in seasons}
    months = {str(s["key"]): [int(m) for m in s["months"]] for s in seasons}
    seeded = 0
    for key in missing:
        donor_key = _donor_for(ordered, key, having_bands)
        if donor_key is None:
            # Nothing to copy from at all — a first-run empty book. The seed
            # path owns that case; inventing numbers here would be worse.
            continue
        for donor in session.scalars(
            select(SeasonalRateBand).where(SeasonalRateBand.season_key == donor_key)
        ).all():
            session.add(
                SeasonalRateBand(
                    season_key=key,
                    season_label=labels.get(key, key),
                    months=months.get(key, []),
                    room_category=donor.room_category,
                    min_net_rate=donor.min_net_rate,
                    base_net_rate=donor.base_net_rate,
                    max_net_rate=donor.max_net_rate,
                    currency=donor.currency,
                    rate_basis=donor.rate_basis,
                    source="OPERATOR_EDITED",
                    note=f"Carried over from {donor_key} when the season was added.",
                )
            )
            seeded += 1
        having_bands.add(key)
    if seeded:
        session.commit()
    return seeded


def _donor_for(ordered: list[str], key: str, having_bands: set[str]) -> str | None:
    """The nearest season before ``key`` that actually has bands, wrapping."""
    start = ordered.index(key)
    for step in range(1, len(ordered)):
        candidate = ordered[(start - step) % len(ordered)]
        if candidate in having_bands:
            return candidate
    return None


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
