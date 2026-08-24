"""BlueJayPMSProvider — integration boundary for Blue Jay PMS.

=============================================================================
 STATUS: BOUNDARY ONLY -- NOT WIRED TO A LIVE API.
 The Blue Jay API documentation was NOT present in this repository (or
 anywhere on the machine) at build time. Per the project brief, endpoints,
 request schemas, response fields and auth mechanisms have therefore NOT been
 invented. See docs/BLUEJAY.md for the full list of unresolved mappings and
 the exact questions needed to finish this adapter.
=============================================================================

What IS implemented here:
  * the class conforms to the PMSProvider contract, so switching
    DATA_PROVIDER=bluejay is a config change and nothing else;
  * credentials are read from the environment only, never from source;
  * an authenticated HTTP client is constructed the moment a base URL and key
    exist, with the auth *style* left configurable because the real scheme is
    unconfirmed;
  * every fetch raises ProviderUnavailable with actionable remediation, which
    the API surfaces as a banner and then falls back to demo data.

What is NOT implemented (deliberately):
  * concrete endpoint paths
  * response -> DTO field mapping
Both are one small commit away once the docs land; the TODO markers below show
exactly where each goes.
"""

from __future__ import annotations

import os
from datetime import date

import httpx

from ...config import get_settings
from .base import (
    BookingDTO,
    InventoryDTO,
    PhysicalRoomDTO,
    PMSProvider,
    PropertyDTO,
    ProviderStatus,
    ProviderUnavailable,
    RoomTypeDTO,
)

UNRESOLVED_MAPPINGS = [
    "Base URL and API version prefix for the Luminous tenant.",
    "Authentication scheme (Bearer token / X-API-Key header / OAuth2 client credentials?).",
    "Endpoint that lists properties, and its pagination contract.",
    "Endpoint that lists ROOM TYPES (2BR Regular / 2BR Premium / 3BR) and how the category is keyed.",
    "Endpoint that lists PHYSICAL ROOMS, and how many units belong to each room type.",
    "Endpoint for per-date availability, and whether it returns units sold or units remaining.",
    "Endpoint for reservations, and whether a booking CREATION timestamp is exposed "
    "(hard requirement for booking pace and for fitting historical booking curves).",
    "Whether cancellation status and cancellation timestamps are available.",
    "Booking source / channel field.",
    "Which field carries the NET revenue to Luminous, versus the guest-facing OTA sell price.",
    "Which field carries the currently published rate, and whether it is NET or gross.",
    "Whether rate plans / length-of-stay pricing exist and how they collapse to one nightly rate.",
    "How far back reservation history can be extracted (the client reports Blue Jay has no "
    "data retention, but that history can be exported with time).",
    "Whether Blue Jay's built-in rule-based Yield Management is active, and whether it would "
    "conflict with rates recommended by this system.",
    "Rate-limit and quota policy.",
]


class BlueJayPMSProvider(PMSProvider):
    name = "BlueJayPMSProvider"
    mode = "bluejay"
    supports_rate_push = False

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.bluejay_base_url
        self._api_key = settings.bluejay_api_key
        self.timeout = settings.bluejay_timeout_seconds
        self.property_ids = settings.bluejay_property_ids
        # Auth style is configurable because the real scheme is unconfirmed.
        self.auth_style = os.getenv("BLUEJAY_AUTH_STYLE", "bearer").strip().lower()
        self.auth_header_name = os.getenv("BLUEJAY_AUTH_HEADER", "Authorization")

    # ------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.base_url and self._api_key)

    def _client(self) -> httpx.Client:
        """Build an authenticated client. Never logs or echoes the key."""
        if not self.configured:
            raise ProviderUnavailable(
                self.name,
                "Blue Jay credentials are not configured.",
                remediation="Set BLUEJAY_BASE_URL and BLUEJAY_API_KEY in .env (see .env.example).",
            )
        if self.auth_style == "bearer":
            headers = {self.auth_header_name: f"Bearer {self._api_key}"}
        else:
            headers = {self.auth_header_name: self._api_key or ""}
        headers["Accept"] = "application/json"
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout)

    def status(self) -> ProviderStatus:
        if not self.configured:
            return ProviderStatus(
                name=self.name,
                healthy=False,
                mode=self.mode,
                detail="Blue Jay credentials are not configured.",
                remediation="Set BLUEJAY_BASE_URL and BLUEJAY_API_KEY in .env, then restart the API.",
                unresolved_mappings=UNRESOLVED_MAPPINGS,
            )
        return ProviderStatus(
            name=self.name,
            healthy=False,
            mode=self.mode,
            detail=(
                "Credentials are present, but the Blue Jay adapter is not wired to live "
                "endpoints: the API documentation was not available at build time, so no "
                "endpoint paths or field mappings have been assumed."
            ),
            remediation=(
                "Provide the Blue Jay API documentation, then implement the TODO markers in "
                "providers/pms/bluejay.py. See docs/BLUEJAY.md."
            ),
            unresolved_mappings=UNRESOLVED_MAPPINGS,
        )

    # ------------------------------------------------------------------
    def _not_implemented(self, what: str) -> ProviderUnavailable:
        return ProviderUnavailable(
            self.name,
            f"Blue Jay {what} is not implemented: the API contract is unconfirmed.",
            remediation=(
                "Supply the Blue Jay API documentation. Endpoints and field mappings were "
                "deliberately not guessed. Meanwhile run with DATA_PROVIDER=mock."
            ),
        )

    def fetch_properties(self) -> list[PropertyDTO]:
        # TODO(bluejay): GET <properties endpoint> -> map into PropertyDTO.
        #   Required mapping: id, name, city/district, currency, timezone.
        raise self._not_implemented("property listing")

    def fetch_room_types(self) -> list[RoomTypeDTO]:
        # TODO(bluejay): GET <room-types endpoint> -> map into RoomDTO.
        #   Required mapping: id, parent property id, display name, occupancy
        #   capacity, number of physical units, published base rate.
        raise self._not_implemented("room-type listing")

    def fetch_physical_rooms(self) -> list[PhysicalRoomDTO]:
        # TODO(bluejay): GET <physical rooms endpoint> -> map into PhysicalRoomDTO.
        #   Required mapping: unit id, parent room-type id, unit label/number.
        #   Needed for inventory and occupancy; units do NOT carry their own rate.
        raise self._not_implemented("physical room listing")

    def fetch_inventory(self, start: date, end: date) -> list[InventoryDTO]:
        # TODO(bluejay): GET <availability/calendar endpoint>?from=..&to=..
        #   Required mapping: stay date, units total, units sold (or units
        #   remaining -> derive), currently published nightly rate.
        raise self._not_implemented("inventory/availability retrieval")

    def fetch_bookings(self, start: date, end: date) -> list[BookingDTO]:
        # TODO(bluejay): GET <reservations endpoint>?from=..&to=..
        #   Required mapping: reservation id, room type id, stay date(s),
        #   CREATED-AT timestamp (needed for booking pace), rate, channel.
        raise self._not_implemented("booking retrieval")
