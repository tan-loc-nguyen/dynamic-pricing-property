"""Operator-defined seasons, and the one rule they must obey.

A season is a contiguous run of whole months. The seasons together cover the
year exactly once -- no gaps, no overlaps -- because the Rate page refuses a
date range that crosses a season boundary. A gap is therefore a hole the
picker cannot describe, and a date in it has no validated band at all.
"""

from __future__ import annotations

from typing import Iterable, Mapping

ALL_MONTHS = frozenset(range(1, 13))


class PartitionError(ValueError):
    """The seasons do not tile the year exactly once."""


def _is_contiguous_run(months: list[int]) -> bool:
    """Do these months form ONE unbroken run, allowing a wrap past December?

    Walked from a start month rather than sorted, because sorting turns the
    legitimate Nov-Dec-Jan into [1, 11, 12] -- which looks broken -- and turns
    the genuinely broken [1, 3] into something a naive min/max range check
    would accept.
    """
    present = set(months)
    if len(present) != len(months) or not present:
        return False
    if present == ALL_MONTHS:
        return True
    # The run starts at the month whose predecessor is absent. Exactly one such
    # month exists in a single unbroken run; two or more means two runs.
    starts = [m for m in present if (m - 2) % 12 + 1 not in present]
    if len(starts) != 1:
        return False
    walked, month = set(), starts[0]
    for _ in range(len(present)):
        if month not in present:
            return False
        walked.add(month)
        month = month % 12 + 1
    return walked == present


def validate_partition(seasons: Iterable[Mapping]) -> None:
    """Raise unless the seasons tile the year exactly once.

    Reports the offending MONTHS rather than just failing, because the operator
    fixes this by dragging a boundary and needs to know which one.
    """
    seasons = list(seasons)
    if not seasons:
        raise PartitionError("At least one season is needed; every date must have a rate band.")

    seen: dict[int, str] = {}
    duplicated: dict[int, list[str]] = {}
    for season in seasons:
        months = [int(m) for m in season.get("months") or []]
        key = str(season.get("key") or "?")
        if not _is_contiguous_run(months):
            raise PartitionError(
                f"Season {key!r} covers months {sorted(months)}, which is not one unbroken "
                f"run. A season has to be a single stretch of the calendar."
            )
        for month in months:
            if month in seen:
                duplicated.setdefault(month, [seen[month]]).append(key)
            seen[month] = key

    if duplicated:
        detail = "; ".join(
            f"month {m} is claimed by {' and '.join(keys)}" for m, keys in sorted(duplicated.items())
        )
        raise PartitionError(f"Seasons overlap: {detail}.")

    missing = sorted(ALL_MONTHS - set(seen))
    if missing:
        raise PartitionError(
            f"No season covers month(s) {missing}. Every date needs a rate band, so a "
            f"gap in the year would leave those dates unpriced."
        )
