"""Read-only HTTP access to Blue Jay.

Two guarantees are structural here rather than conventional, because both
protect against mistakes that cannot be undone from our side:

* **Only GET.** Blue Jay documents POST for creating bookings. This client
  exposes no way to reach it — there is no ``post``, ``put``, ``patch``,
  ``delete``, ``request`` or ``send`` attribute to reach for. Whether Blue Jay
  operates a zero-data-retention policy is unknown, so a write is treated as
  potentially irreversible.
* **Only inside a testing window.** "Do not call outside the documented
  windows" is enforced where the request is issued, not left to whoever is
  writing the calling code at 08:15.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping

import httpx

from ..base import ProviderUnavailable
from . import windows

PROVIDER_NAME = "BlueJayPMSProvider"


class BlueJayClient:
    """A GET-only, window-gated Blue Jay client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        hotel_id: str,
        timeout: float = 15.0,
        auth_header: str = "X-API-KEY",
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], datetime] | None = None,
        ignore_window: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.hotel_id = str(hotel_id)
        self.timeout = timeout
        self.auth_header = auth_header
        # Single leading underscore and never rendered: see __repr__.
        self._api_key = api_key
        self._transport = transport
        self._now = now or (lambda: datetime.now(tz=windows.VIETNAM))
        #: Opt-in, per client, never the default. A hard block with no override
        #: becomes a blocker at the worst possible moment — Blue Jay saying
        #: "we've opened it for you now" during an integration call.
        self.ignore_window = ignore_window
        self.calls_made = 0

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<BlueJayClient base_url={self.base_url!r} hotel_id={self.hotel_id!r}>"

    # ------------------------------------------------------------------
    def _check_window(self) -> None:
        if self.ignore_window:
            return
        status = windows.window_status(self._now())
        if status.is_open:
            return
        opens = status.next_open_at.strftime("%H:%M on %d %b") if status.next_open_at else "unknown"
        raise ProviderUnavailable(
            PROVIDER_NAME,
            "Outside Blue Jay's testing window; the request was not sent.",
            remediation=(
                f"Blue Jay accepts testing calls at "
                f"{', '.join(w.source_text for w in windows.confirmed_windows())} Vietnam time. "
                f"The next window opens at {opens} (Asia/Ho_Chi_Minh). "
                f"Run with SNAPSHOT or MOCK until then."
            ),
        )

    def get(self, endpoint: str, params: Mapping[str, Any] | None = None) -> Any:
        """Issue one GET. The ONLY way this class talks to Blue Jay."""
        self._check_window()

        query: dict[str, Any] = {"hotelId": self.hotel_id}
        for key, value in (params or {}).items():
            if value is not None:
                query[key] = value

        headers = {self.auth_header: self._api_key, "Accept": "application/json"}
        # `with` closes the transport on exit, including one that was handed in.
        # Harmless today because production passes None, but a caller reusing an
        # injected transport across calls would find it closed after the first.
        with httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            transport=self._transport,
        ) as http:
            try:
                response = http.get(f"/{endpoint.lstrip('/')}", params=query)
            except httpx.HTTPError as exc:
                # Never interpolate the key; httpx errors can carry the request.
                raise ProviderUnavailable(
                    PROVIDER_NAME,
                    f"Blue Jay request to {endpoint!r} failed: {type(exc).__name__}.",
                    remediation="Check connectivity and BLUEJAY_BASE_URL. Fall back to SNAPSHOT.",
                ) from None
        self.calls_made += 1

        if response.status_code >= 400:
            raise ProviderUnavailable(
                PROVIDER_NAME,
                f"Blue Jay returned HTTP {response.status_code} for {endpoint!r}.",
                remediation=(
                    "401/403 means the API key is wrong or revoked; 429 means quota. "
                    "Do NOT retry in a loop — the testing windows are short and shared."
                ),
            )
        try:
            return response.json()
        except ValueError:
            raise ProviderUnavailable(
                PROVIDER_NAME,
                f"Blue Jay returned a non-JSON body for {endpoint!r}.",
                remediation="Capture the raw body with scripts/bluejay_probe.py and compare.",
            ) from None
