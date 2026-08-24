"""SeasonalRateBook — CLIENT-VALIDATED business fact.

=============================================================================
 SOURCE: Luminous Luxury Apartments, "Business Assumptions" (client document).
 STATUS: CLIENT_VALIDATED — this is NOT a modelling assumption.

 These MIN / BASE / MAX figures are **NET rates**: what Luminous receives,
 not the guest-facing OTA price. They already encode seasonality, which is
 exactly why the pricing engine must NOT multiply a seasonality factor on top
 (that would double-count the season). Season selects the band; it does not
 scale it.

 The client's own conclusion, translated:
   "The base-rate layer does not need modelling and does not need to be
    inferred from history. It already exists and has been validated by real
    operation. Load the rate table as a lookup table.
    What is needed is the dynamic layer on top: booking pace, lead time,
    events, competitor response."
=============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

RATE_BOOK_SOURCE = "CLIENT_VALIDATED"
RATE_BASIS = "NET"

# --- room categories -------------------------------------------------------
CATEGORY_2BR_REGULAR = "2br_regular"
CATEGORY_2BR_PREMIUM = "2br_premium"
CATEGORY_3BR = "3br"

ROOM_CATEGORIES = [
    {"key": CATEGORY_2BR_REGULAR, "label": "2BR Regular", "label_vi": "2 phòng ngủ thường", "capacity": 4},
    {"key": CATEGORY_2BR_PREMIUM, "label": "2BR Premium", "label_vi": "2 phòng ngủ premium", "capacity": 4},
    {"key": CATEGORY_3BR, "label": "3BR", "label_vi": "3 phòng ngủ", "capacity": 6},
]
CATEGORY_LABELS = {c["key"]: c["label"] for c in ROOM_CATEGORIES}

# --- seasons ---------------------------------------------------------------
# NOTE: High Season 2 wraps the year end (Nov, Dec, Jan). January belongs to
# the Nov–Jan high season, NOT to a "start of year" season. This wrap is the
# single most error-prone part of the table and is covered by tests.
SEASONS = [
    {
        "key": "low_1",
        "label": "Low Season 1 (May–Jun)",
        "months": [5, 6],
        "note": "Mostly business travel, little tourism.",
    },
    {
        "key": "high_1",
        "label": "High Season 1 (Jul–Aug)",
        "months": [7, 8],
        "note": "Summer tourism — international and family travel.",
    },
    {
        "key": "low_2",
        "label": "Low Season 2 (Sep–Oct)",
        "months": [9, 10],
        "note": "Predominantly business travel.",
    },
    {
        "key": "high_2",
        "label": "High Season 2 (Nov–Jan)",
        "months": [11, 12, 1],
        "note": "Holiday season.",
    },
    {
        "key": "medium",
        "label": "Medium Season (Feb–Apr)",
        "months": [2, 3, 4],
        "note": "",
    },
]
SEASON_LABELS = {s["key"]: s["label"] for s in SEASONS}
SEASON_NOTES = {s["key"]: s["note"] for s in SEASONS}

# month -> season_key, derived once so lookup is O(1) and cannot drift.
MONTH_TO_SEASON: dict[int, str] = {}
for _season in SEASONS:
    for _m in _season["months"]:
        MONTH_TO_SEASON[_m] = _season["key"]
assert len(MONTH_TO_SEASON) == 12, "every month must map to exactly one season"

# --- the validated table ---------------------------------------------------
# (season_key, category) -> (MIN, BASE, MAX) NET VND
CLIENT_RATE_TABLE: dict[tuple[str, str], tuple[int, int, int]] = {
    # LOW SEASON 1 — May–June
    ("low_1", CATEGORY_2BR_REGULAR): (1_800_000, 2_000_000, 2_200_000),
    ("low_1", CATEGORY_2BR_PREMIUM): (2_000_000, 2_300_000, 2_500_000),
    ("low_1", CATEGORY_3BR):         (2_700_000, 2_800_000, 3_200_000),
    # HIGH SEASON 1 — July–August
    ("high_1", CATEGORY_2BR_REGULAR): (2_100_000, 2_300_000, 2_600_000),
    ("high_1", CATEGORY_2BR_PREMIUM): (2_400_000, 2_700_000, 2_900_000),
    ("high_1", CATEGORY_3BR):         (2_900_000, 3_300_000, 3_500_000),
    # LOW SEASON 2 — September–October
    ("low_2", CATEGORY_2BR_REGULAR): (1_800_000, 2_100_000, 2_300_000),
    ("low_2", CATEGORY_2BR_PREMIUM): (2_000_000, 2_400_000, 2_700_000),
    ("low_2", CATEGORY_3BR):         (2_600_000, 2_800_000, 3_000_000),
    # HIGH SEASON 2 — November–January
    ("high_2", CATEGORY_2BR_REGULAR): (2_100_000, 2_500_000, 3_200_000),
    ("high_2", CATEGORY_2BR_PREMIUM): (2_500_000, 3_000_000, 3_500_000),
    ("high_2", CATEGORY_3BR):         (3_200_000, 3_800_000, 4_300_000),
    # MEDIUM SEASON — February–April
    ("medium", CATEGORY_2BR_REGULAR): (2_000_000, 2_300_000, 2_500_000),
    ("medium", CATEGORY_2BR_PREMIUM): (2_200_000, 2_500_000, 2_700_000),
    ("medium", CATEGORY_3BR):         (2_700_000, 3_200_000, 3_500_000),
}
assert len(CLIENT_RATE_TABLE) == len(SEASONS) * len(ROOM_CATEGORIES) == 15


@dataclass(frozen=True)
class RateBand:
    """The MIN/BASE/MAX NET rates that apply to one room category on one date."""

    season_key: str
    season_label: str
    room_category: str
    min_net_rate: float
    base_net_rate: float
    max_net_rate: float
    currency: str = "VND"
    rate_basis: str = RATE_BASIS
    source: str = RATE_BOOK_SOURCE
    note: str | None = None

    def clamp(self, value: float) -> tuple[float, str | None]:
        """Clamp a rate into the band. Returns (value, 'min'|'max'|None)."""
        if value < self.min_net_rate:
            return self.min_net_rate, "min"
        if value > self.max_net_rate:
            return self.max_net_rate, "max"
        return value, None

    def to_dict(self) -> dict:
        return {
            "season_key": self.season_key,
            "season_label": self.season_label,
            "room_category": self.room_category,
            "min_net_rate": self.min_net_rate,
            "base_net_rate": self.base_net_rate,
            "max_net_rate": self.max_net_rate,
            "currency": self.currency,
            "rate_basis": self.rate_basis,
            "source": self.source,
            "note": self.note,
        }


def season_for(day: date) -> str:
    return MONTH_TO_SEASON[day.month]


def season_label_for(day: date) -> str:
    return SEASON_LABELS[season_for(day)]


class SeasonalRateBook:
    """Lookup of validated rate bands.

    Defaults to the client table; can be constructed from persisted rows so an
    operator edit in Settings takes effect without a code change.
    """

    def __init__(self, table: dict[tuple[str, str], tuple[float, float, float]] | None = None) -> None:
        self._table = dict(table) if table else dict(CLIENT_RATE_TABLE)

    @classmethod
    def from_rows(cls, rows) -> "SeasonalRateBook":
        return cls({(r.season_key, r.room_category): (r.min_net_rate, r.base_net_rate, r.max_net_rate) for r in rows})

    def lookup(self, room_category: str, stay_date: date) -> RateBand | None:
        season_key = season_for(stay_date)
        entry = self._table.get((season_key, room_category))
        if entry is None:
            return None
        minimum, base, maximum = entry
        return RateBand(
            season_key=season_key,
            season_label=SEASON_LABELS[season_key],
            room_category=room_category,
            min_net_rate=float(minimum),
            base_net_rate=float(base),
            max_net_rate=float(maximum),
            note=SEASON_NOTES.get(season_key) or None,
        )

    def all_bands(self) -> list[dict]:
        out = []
        for season in SEASONS:
            for category in ROOM_CATEGORIES:
                entry = self._table.get((season["key"], category["key"]))
                if entry is None:
                    continue
                minimum, base, maximum = entry
                out.append(
                    {
                        "season_key": season["key"],
                        "season_label": season["label"],
                        "months": season["months"],
                        "note": season["note"],
                        "room_category": category["key"],
                        "room_category_label": category["label"],
                        "min_net_rate": float(minimum),
                        "base_net_rate": float(base),
                        "max_net_rate": float(maximum),
                        "currency": "VND",
                        "rate_basis": RATE_BASIS,
                        "source": RATE_BOOK_SOURCE,
                    }
                )
        return out
