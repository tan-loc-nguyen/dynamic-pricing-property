"""BlueJayPMSProvider — the LIVE adapter.

=============================================================================
 STATUS: WIRED, BUT PROVISIONAL.
 Endpoint paths and request parameters come from Blue Jay's API document.
 Response FIELD NAMES for the filter endpoints are inferred, because that
 document gives no sample response for them. Everything here is expected to
 need correction against the real API; see docs/BLUEJAY_CONTRACT.md for the
 verification checklist and `scripts/bluejay_probe.py` for the tool that runs
 it.
=============================================================================

Read-only by construction: this class never reaches a write path because
``BlueJayClient`` does not expose one. Rate push stays disabled (D22).

One endpoint carries most of the load. ``/reservation`` with ``dateType=3``
("stay night") yields bookings, on-the-books occupancy AND a derived rate in a
single call, which matters when the testing window is thirty minutes long. The
occupancy report is a cross-check rather than a source, because its documented
sample contradicts its own arithmetic at the detail level.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from ....config import get_settings
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
from . import normalize, windows
from .client import BlueJayClient

#: `dateType=3` filters by STAY NIGHT, which is the grain this system prices at.
DATE_TYPE_STAY_NIGHT = 3

UNRESOLVED_MAPPINGS = [
    "WHICH HEADER carries the API key, and whether it is raw or 'Bearer <key>'. The "
    "document says only that it goes in 'the Header'. We default to X-API-KEY raw; "
    "BLUEJAY_AUTH_HEADER and BLUEJAY_AUTH_STYLE change it without a code edit.",
    "Confirm the '24:00-24:59' testing window — it is not clock notation.",
    "Response schema for roomtype-list and roomdetail-list (the document gives no sample).",
    "Whether `roomPrice` is a STAY TOTAL or a NIGHTLY rate — both samples are night=1, "
    "so the document cannot distinguish them (ASSUMPTIONS U14).",
    "Whether `roomPrice` is NET to Luminous or gross of OTA commission (ASSUMPTIONS U14).",
    "The full set of reservation status strings — only 'Đã huỷ' has ever been observed; "
    "the rest of our vocabulary is inferred and a wrong guess MISCOUNTS OCCUPANCY silently.",
    "Whether a reservation row is one physical room or a group booking.",
    "Which endpoint, if any, publishes a FORWARD-LOOKING rate. None is documented, so "
    "current_net_rate is reconstructed from bookings.",
    "Whether report-room-occupancy projects forward or only reports history.",
    "The correct endpoint for occupancy — the document's own example calls /reservation.",
    "Pagination beyond `limit`/`page`, and the maximum safe page size.",
    "Rate-limit and quota policy.",
    "How cancellations are represented over time (status change, or row disappearance).",
    "Whether Blue Jay's built-in rule-based Yield Management is active on this tenant.",
    "How far back reservation history can be exported (ASSUMPTIONS U15).",
    "Luminous' own hotelId — the documented tenant 1003 is a different property.",
]


class BlueJayPMSProvider(PMSProvider):
    name = "BlueJayPMSProvider"
    mode = "bluejay"
    supports_rate_push = False

    def __init__(
        self,
        client: BlueJayClient | None = None,
        category_map: dict[str, str] | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = settings.bluejay_base_url
        self.hotel_id = settings.bluejay_hotel_id
        # MUST match what _api() actually requires. When these two drifted,
        # status() reported a healthy integration while every fetch raised
        # "not configured" -- the same two-predicates-disagreeing shape as
        # the demo_mode bug, and BLUEJAY_HOTEL_ID is the newest setting so
        # it is the one most likely to be missing on a first run.
        self._configured = bool(
            settings.bluejay_base_url and settings.bluejay_api_key and settings.bluejay_hotel_id
        )
        self._client = client
        #: roomtypeId -> our category. Persisted in Settings, filled from probe
        #: discovery; see normalize.build_name_category_map for why it is keyed
        #: on the id rather than the display name.
        self.category_map = category_map or {}
        self.report = normalize.NormalisationReport()
        # Per-instance response caches. A provider is constructed per request or
        # per sync, so this never outlives one logical operation.
        self._room_types_cache: list[dict] | None = None
        self._room_details_cache: list[dict] | None = None
        self._bookings_cache: dict[tuple[date, date], list[BookingDTO]] = {}
        if client is not None:
            self._configured = True

    # ------------------------------------------------------------------
    def _api(self) -> BlueJayClient:
        if self._client is not None:
            return self._client
        settings = get_settings()
        if not (settings.bluejay_base_url and settings.bluejay_api_key and settings.bluejay_hotel_id):
            raise ProviderUnavailable(
                self.name,
                "Blue Jay is not configured.",
                remediation=(
                    "Set BLUEJAY_BASE_URL, BLUEJAY_API_KEY and BLUEJAY_HOTEL_ID in .env, "
                    "then restart the API. Until then run in SNAPSHOT or MOCK mode."
                ),
            )
        self._client = BlueJayClient(
            base_url=settings.bluejay_base_url,
            api_key=settings.bluejay_api_key,
            hotel_id=settings.bluejay_hotel_id,
            timeout=settings.bluejay_timeout_seconds,
            auth_header=settings.bluejay_auth_header,
            auth_style=settings.bluejay_auth_style,
        )
        return self._client

    @staticmethod
    def _rows(payload: Any) -> list[dict]:
        """Rows from a filter endpoint. Shape UNVERIFIED — accepts both a bare
        list and a `data`-wrapped one rather than guessing which arrives.

        The envelope is checked FIRST. An error response carrying ``data: []``
        is an ordinary API shape and it slipped straight through the
        unrecognised-shape guard: on roomtype-list it surfaced as "no room type
        is mapped, open Settings", blaming the operator for a revoked key while
        discarding the `message` that said so; on roomdetail-list it silently
        set units_total to 0 for every category.
        """
        if isinstance(payload, Mapping):
            try:
                normalize._check_envelope(payload)  # noqa: SLF001 - same package
            except normalize.VendorPayloadError as exc:
                raise ProviderUnavailable(
                    "BlueJayPMSProvider",
                    str(exc),
                    remediation=(
                        f"Blue Jay refused the request: {exc}. This is NOT an empty "
                        f"property — treating it as one would zero every unit count. "
                        f"Check the API key and quota."
                    ),
                ) from None
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for key in ("data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [r for r in value if isinstance(r, dict)]
        raise ProviderUnavailable(
            "BlueJayPMSProvider",
            "A Blue Jay filter endpoint returned a shape we do not recognise.",
            remediation=(
                "Capture it with scripts/bluejay_probe.py and update "
                "providers/pms/bluejay/normalize.py. Do NOT treat it as empty — an "
                "empty room-type list would zero every unit count."
            ),
        )

    def _room_type_rows(self) -> list[dict]:
        """Memoised per provider instance.

        Every fetch used to re-derive the room-type map, and fetch_inventory
        re-called fetch_bookings AND fetch_room_types, so ONE sync spent about
        ten GETs -- five of them this identical call, plus two identical
        `reservation?limit=5000` pulls. The window is thirty minutes and shared,
        and client.py warns against hammering it; duplication gets there just as
        fast as retrying does.
        """
        if self._room_types_cache is None:
            self._room_types_cache = self._rows(self._api().get("roomtype-list"))
        return self._room_types_cache

    def _room_detail_rows(self) -> list[dict]:
        if self._room_details_cache is None:
            self._room_details_cache = self._rows(self._api().get("roomdetail-list"))
        return self._room_details_cache

    def _require_mapping(self, room_types: list[dict]) -> dict[str, str]:
        names = normalize.build_name_category_map(room_types, self.category_map)
        if not names:
            raise ProviderUnavailable(
                self.name,
                "No Blue Jay room type is mapped to a pricing category.",
                remediation=(
                    "Open Settings -> Data and map each discovered room type to a "
                    "category. Without it every date would be unpriced, which is not "
                    "something to discover during a demo."
                ),
            )
        return names


    def discover_room_types(self) -> list[dict]:
        """Room types the operator has not mapped yet, with their display names.

        The panel that fixes an unmapped room type could not SEE one: it read
        only the persisted map, which by definition holds what is already done.
        A name travels with the id because choosing a pricing category for an
        opaque number is how the wrong one gets picked, and a wrong mapping
        misprices a whole category silently.
        """
        try:
            rows = self._room_type_rows()
        except ProviderUnavailable:
            # Discovery is best-effort. It must never be the thing that breaks
            # the settings screen, which is where you go to fix the outage.
            return []
        return [
            {"id": type_id, "name": name}
            for type_id, name in normalize.unmapped_room_type_ids(rows, self.category_map)
        ]

    # ------------------------------------------------------------------
    def status(self) -> ProviderStatus:
        # Use the client's clock when one was injected, so a test or the
        # documented escape hatch cannot end up with fetches succeeding
        # while the panel insists the window is closed.
        now = self._client._now() if self._client is not None else None  # noqa: SLF001
        window = windows.window_status(now)
        window_text = ", ".join(w.source_text for w in windows.confirmed_windows())
        opens = window.next_open_at.strftime("%H:%M %d %b") if window.next_open_at else "unknown"

        notes = list(UNRESOLVED_MAPPINGS)
        if self._configured:
            try:
                discovered = normalize.unmapped_room_type_ids(
                    self._room_type_rows(), self.category_map
                )
                notes = [
                    f"Room type {tid!r} ({name!r}) is not mapped to a pricing category."
                    for tid, name in discovered
                ] + notes
            except ProviderUnavailable:
                # Discovery is best-effort: status must never be the thing that
                # fails, or the UI cannot explain why anything else did.
                pass

        if not self._configured:
            return ProviderStatus(
                name=self.name,
                healthy=False,
                mode=self.mode,
                detail="Blue Jay credentials are not configured.",
                remediation=(
                    "Set BLUEJAY_BASE_URL, BLUEJAY_API_KEY and BLUEJAY_HOTEL_ID in .env. "
                    f"Calls are only accepted during {window_text} Vietnam time."
                ),
                unresolved_mappings=notes,
            )

        return ProviderStatus(
            name=self.name,
            healthy=window.is_open,
            mode=self.mode,
            detail=(
                f"Testing window {window_text} (Asia/Ho_Chi_Minh). "
                + ("OPEN now." if window.is_open else f"Closed; next opens {opens}.")
            ),
            remediation=(
                ""
                if window.is_open
                else f"Use SNAPSHOT mode until the window at {window_text} Vietnam time."
            ),
            unresolved_mappings=notes,
        )

    # ------------------------------------------------------------------
    def fetch_properties(self) -> list[PropertyDTO]:
        # No property endpoint is documented; the tenant IS the property.
        return [PropertyDTO(external_id=str(self.hotel_id or "bluejay"), name="Blue Jay property")]

    def fetch_room_types(self) -> list[RoomTypeDTO]:
        room_types = self._room_type_rows()
        names = self._require_mapping(room_types)
        book = SeasonalRateBook()
        fallbacks = {}
        for category in ("2br_regular", "2br_premium", "3br"):
            band = book.lookup(category, date.today())
            if band is not None:
                fallbacks[category] = band.base_net_rate
        return normalize.room_types_to_dtos(
            room_types,
            self._room_detail_rows(),
            category_map=names,
            property_external_id=str(self.hotel_id or "bluejay"),
            fallback_rates=fallbacks,
            report=self.report,
        )

    def fetch_physical_rooms(self) -> list[PhysicalRoomDTO]:
        room_types = self._room_type_rows()
        return normalize.physical_rooms_to_dtos(
            self._room_detail_rows(),
            room_types,
            category_map=self._require_mapping(room_types),
        )

    def fetch_bookings(self, start: date, end: date) -> list[BookingDTO]:
        if (start, end) in self._bookings_cache:
            return self._bookings_cache[(start, end)]
        names = self._require_mapping(self._room_type_rows())
        payload = self._api().get(
            "reservation",
            {
                "dateType": DATE_TYPE_STAY_NIGHT,
                "from": start.isoformat(),
                "to": end.isoformat(),
                # The documented default is 20 rows, which would silently
                # truncate a month of a 22-unit property to a few days.
                "limit": 5000,
                "page": 1,
            },
        )
        try:
            rows = normalize.reservations_to_bookings(
                payload, category_map=names, report=self.report
            )
            self._bookings_cache[(start, end)] = rows
            return rows
        except normalize.VendorPayloadError as exc:
            raise ProviderUnavailable(
                self.name,
                f"Blue Jay's reservation response could not be read: {exc}",
                remediation=(
                    "This is NOT an empty period — zero bookings would price every date "
                    "down to its floor. Capture the response with scripts/bluejay_probe.py "
                    "and compare it against docs/BLUEJAY_CONTRACT.md."
                ),
            ) from None

    def fetch_inventory(self, start: date, end: date) -> list[InventoryDTO]:
        bookings = self.fetch_bookings(start, end)
        room_types = self.fetch_room_types()
        book = SeasonalRateBook()
        stay_dates = [date.fromordinal(o) for o in range(start.toordinal(), end.toordinal() + 1)]
        # Per DATE, not once at the window start: a 90-day horizon crosses
        # season boundaries and each date belongs to its own band (D17).
        fallback = _seasonal_bases(book, [rt.external_id for rt in room_types], stay_dates)
        return normalize.build_inventory(
            stay_dates=stay_dates,
            categories=[rt.external_id for rt in room_types],
            units_total={rt.external_id: rt.units_total for rt in room_types},
            units_sold=normalize.units_sold_by_date(bookings),
            adr=normalize.derive_adr(bookings),
            fallback_rate=fallback,
        )


def _seasonal_bases(
    book: SeasonalRateBook, categories: list[str], stay_dates: list[date]
) -> dict[tuple[str, date], float]:
    """The validated BASE for each category on each date.

    Built per date because the seasonal band a date belongs to is a property of
    THAT date. Looking it up once for the window handed every date the band of
    whichever season the window happened to start in.
    """
    out: dict[tuple[str, date], float] = {}
    for category in categories:
        for stay in stay_dates:
            band = book.lookup(category, stay)
            if band is not None:
                out[(category, stay)] = band.base_net_rate
    return out
