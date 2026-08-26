"""SnapshotPMSProvider — sanitized real Blue Jay data, replayed offline.

This is intended to become the preferred CLIENT-DEMO source. Blue Jay's test
API is reachable for roughly ninety minutes a day, which is no basis for a
demo; a snapshot is real vendor data with none of that dependency.

The load-bearing property: a snapshot replays through **exactly the same
normaliser as a live response**. A snapshot that needed its own parser would
stop being evidence about the live one, and the whole point of capturing is to
learn what live actually returns.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from ....pricing.rate_book import SeasonalRateBook
from ..base import (
    BookingDTO,
    InventoryDTO,
    PhysicalRoomDTO,
    PMSProvider,
    PropertyDTO,
    ProviderStatus,
    ProviderUnavailable,
    RoomTypeDTO,
)
from . import normalize

PROVIDER_NAME = "SnapshotPMSProvider"

#: Files the probe writes. Named for the endpoint they came from so a reader
#: can line a snapshot up against the API documentation without a decoder ring.
RESERVATIONS_FILE = "reservation.json"
ROOM_TYPES_FILE = "roomtype-list.json"
ROOM_DETAILS_FILE = "roomdetail-list.json"
META_FILE = "meta.json"


class SnapshotPMSProvider(PMSProvider):
    name = PROVIDER_NAME
    mode = "snapshot"
    supports_rate_push = False

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        #: Populated as files are normalised, and read by sync_pms.
        self.report = normalize.NormalisationReport()

    # ------------------------------------------------------------------
    def _load(self, filename: str) -> Any:
        path = self.root / filename
        if not path.is_file():
            raise ProviderUnavailable(
                PROVIDER_NAME,
                f"Snapshot file {filename!r} is missing from {self.root}.",
                remediation=(
                    "Capture one during a Blue Jay testing window with "
                    "`python scripts/bluejay_probe.py --capture`, then point "
                    "BLUEJAY_SNAPSHOT_DIR at it. Snapshots are gitignored, so a fresh "
                    "clone never has one — copy it across out of band."
                ),
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ProviderUnavailable(
                PROVIDER_NAME,
                f"Snapshot file {filename!r} is not valid JSON: {exc}.",
                remediation="Re-capture it; a truncated write is the usual cause.",
            ) from None

    def _meta(self) -> dict:
        try:
            meta = self._load(META_FILE)
        except ProviderUnavailable:
            return {}
        return meta if isinstance(meta, dict) else {}

    def _category_map(self) -> dict[str, str]:
        """Room-type NAME -> our category, resolved THROUGH the captured ids.

        Keyed on id in meta.json for the reason set out in
        `normalize.build_name_category_map`: display names are editable and the
        reservation payload is name-only.
        """
        return normalize.build_name_category_map(
            self._rows(self._load(ROOM_TYPES_FILE)), self._meta().get("category_map") or {}
        )

    @staticmethod
    def _rows(payload: Any) -> list[dict]:
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
        return []


    def discover_room_types(self) -> list[dict]:
        """Captured room types the operator has not mapped. See the live
        provider for why the display name travels with the id."""
        try:
            rows = self._rows(self._load(ROOM_TYPES_FILE))
        except ProviderUnavailable:
            return []
        return [
            {"id": type_id, "name": name}
            for type_id, name in normalize.unmapped_room_type_ids(
                rows, self._meta().get("category_map") or {}
            )
        ]

    # ------------------------------------------------------------------
    def status(self) -> ProviderStatus:
        meta = self._meta()
        if not meta:
            return ProviderStatus(
                name=PROVIDER_NAME,
                healthy=False,
                mode=self.mode,
                detail=f"No snapshot found at {self.root}.",
                remediation="Capture one during a testing window, or switch to MOCK.",
            )

        captured = meta.get("captured_at") or "an unknown date"

        # A capture whose requests failed leaves a directory containing only
        # meta.json. Keying `healthy` on meta merely EXISTING reported a
        # confident "replaying a sanitized capture from ..." right up until
        # each fetch raised "file is missing".
        capture_errors = meta.get("errors") or []
        missing = [
            name
            for name in (RESERVATIONS_FILE, ROOM_TYPES_FILE, ROOM_DETAILS_FILE)
            if not (self.root / name).is_file()
        ]
        if capture_errors or missing:
            return ProviderStatus(
                name=PROVIDER_NAME,
                healthy=False,
                mode=self.mode,
                detail=(
                    f"The capture from {captured} is incomplete: "
                    + (f"{len(missing)} file(s) missing. " if missing else "")
                    + (f"{len(capture_errors)} request(s) failed." if capture_errors else "")
                ),
                remediation=(
                    "Re-capture during a full testing window. A partial capture would "
                    "read as an empty property, which prices every date to its floor."
                ),
                warnings=[str(e) for e in capture_errors],
            )

        notes: list[str] = []
        if not meta.get("salt_is_private", False):
            # A public salt plus 6-digit booking codes is a rainbow table.
            notes.append(
                "This snapshot was pseudonymised with the PUBLIC fixture salt, so its "
                "booking codes are trivially recoverable. Set BLUEJAY_PSEUDONYM_SALT and "
                "re-capture before sharing it."
            )
        if not meta.get("sanitised", False):
            notes.append("This snapshot is NOT marked sanitised — it may contain guest data.")

        return ProviderStatus(
            name=PROVIDER_NAME,
            healthy=True,
            mode=self.mode,
            detail=(
                f"Replaying a sanitized Blue Jay capture from {captured} "
                f"(hotelId {meta.get('hotel_id', '?')}). No network, no testing window."
            ),
            remediation="",
            warnings=notes,
        )

    # ------------------------------------------------------------------
    def fetch_properties(self) -> list[PropertyDTO]:
        meta = self._meta()
        return [
            PropertyDTO(
                external_id=str(meta.get("hotel_id") or "bluejay"),
                # Real-world names are never invented and never translated.
                name=str(meta.get("property_name") or "Blue Jay property (snapshot)"),
            )
        ]

    def fetch_room_types(self) -> list[RoomTypeDTO]:
        book = SeasonalRateBook()
        fallbacks = {
            category: band.base_net_rate
            for category, band in _base_rates_today(book).items()
        }
        return normalize.room_types_to_dtos(
            self._rows(self._load(ROOM_TYPES_FILE)),
            self._rows(self._load(ROOM_DETAILS_FILE)),
            category_map=self._category_map(),
            property_external_id=str(self._meta().get("hotel_id") or "bluejay"),
            fallback_rates=fallbacks,
            report=self.report,
        )

    def fetch_physical_rooms(self) -> list[PhysicalRoomDTO]:
        return normalize.physical_rooms_to_dtos(
            self._rows(self._load(ROOM_DETAILS_FILE)),
            self._rows(self._load(ROOM_TYPES_FILE)),
            category_map=self._category_map(),
        )

    def fetch_bookings(self, start: date, end: date) -> list[BookingDTO]:
        rows = normalize.reservations_to_bookings(
            self._load(RESERVATIONS_FILE),
            category_map=self._category_map(),
            report=self.report,
        )
        # The capture covers whatever window the probe asked for; the caller's
        # window is narrower or wider and must be honoured either way.
        return [b for b in rows if start <= b.stay_date <= end]

    def fetch_inventory(self, start: date, end: date) -> list[InventoryDTO]:
        bookings = self.fetch_bookings(start, end)
        room_types = self.fetch_room_types()
        book = SeasonalRateBook()
        stay_dates = [
            date.fromordinal(o) for o in range(start.toordinal(), end.toordinal() + 1)
        ]
        categories = [rt.external_id for rt in room_types]
        return normalize.build_inventory(
            stay_dates=stay_dates,
            categories=categories,
            units_total={rt.external_id: rt.units_total for rt in room_types},
            units_sold=normalize.units_sold_by_date(bookings),
            adr=normalize.derive_adr(bookings),
            # Per DATE (D17): each stay date belongs to its own seasonal band.
            fallback_rate=_seasonal_bases(book, categories, stay_dates),
        )


def _seasonal_bases(
    book: SeasonalRateBook, categories: list[str], stay_dates: list[date]
) -> dict[tuple[str, date], float]:
    """The validated BASE for each category on each date, per DATE."""
    out: dict[tuple[str, date], float] = {}
    for category in categories:
        for stay in stay_dates:
            band = book.lookup(category, stay)
            if band is not None:
                out[(category, stay)] = band.base_net_rate
    return out


def _base_rates_today(book: SeasonalRateBook) -> dict:
    """Seasonal BASE per category TODAY — used only for RoomTypeDTO fallbacks,
    which are a room-type property rather than a per-date one."""
    out = {}
    today = date.today()
    for category in ("2br_regular", "2br_premium", "3br"):
        band = book.lookup(category, today)
        if band is not None:
            out[category] = band
    return out
