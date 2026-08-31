"""PublicWebMarketDataProvider — a deliberately small, honest prototype.

PURPOSE
    Prove one thing end to end:
        external public source -> normalization -> market signal -> pricing engine
    It is NOT a scraping system and must never become one.

CONFIDENCE POSITION
    Everything this provider emits is LOW confidence, by construction. A public
    page rarely states the stay date, length of stay, room category, tax/fee
    basis or promotion status — without those, the number is not comparable to
    a Luminous NET rate. LOW-confidence evidence is stored and shown to the
    operator, but the pricing engine will not act on it.

WHAT IT DOES
    * fetches operator-configured public URLs (MARKET_PUBLIC_SOURCES)
    * checks robots.txt FIRST and obeys a disallow
    * identifies itself honestly via a descriptive User-Agent
    * extracts VND-shaped prices with a conservative regex
    * records source URL + collection timestamp on every observation

WHAT IT WILL NOT DO (hard limits, by design)
    * no CAPTCHA solving, no login/auth bypass, no anti-bot evasion
    * no identity/IP rotation
    * no Airbnb / Booking.com scraping (their terms prohibit it)
    * no retry storms — one attempt per URL, then give up
    * NEVER a functional dependency: disabled by default, and the app is fully
      usable on mock or manual market data.

KNOWN LIMITATION (documented, not worked around)
    Most public accommodation pages render prices client-side and/or vary
    markup per site, so a generic extractor is unreliable. When it fails it
    fails loudly and the system falls back to a neutral market factor.
    See docs/MARKET_DATA.md.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
import urllib.robotparser
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx

from ...config import get_settings
from ..pms.base import ProviderStatus, ProviderUnavailable
from .base import CONFIDENCE_LOW, MarketDataProvider, MarketObservationDTO

# Hosts we will not touch regardless of configuration.
BLOCKED_HOSTS = (
    "airbnb.com",
    "booking.com",
    "agoda.com",
    "expedia.com",
    "trip.com",
    "tripadvisor.com",
)

# VND amounts: "1.850.000", "1,850,000", "1850000 VND", "₫1.850.000"
_PRICE_PATTERN = re.compile(
    r"(?:₫|VND|vnd)?\s*([0-9]{1,3}(?:[.,\s][0-9]{3}){1,3})\s*(?:₫|VND|vnd|đ)?"
)
#: A source may be configured as a TEMPLATE carrying the stay dates into the
#: request. Without them the collector files a price under a night the site was
#: never asked about, so one number stands in for the whole range -- a flat line
#: wearing the costume of a market band.
CHECKIN_PLACEHOLDER = "{checkin}"
CHECKOUT_PLACEHOLDER = "{checkout}"

#: A 200-night range must not become 200 requests to a small hotel's website.
#: Exceeding it truncates, and the caller REPORTS the truncation rather than
#: presenting a short band as a complete one.
MAX_NIGHTS_PER_COLLECTION = 30


def is_dated_template(url: str) -> bool:
    return CHECKIN_PLACEHOLDER in url


def nightly_urls(url: str, start: date, end: date) -> list[tuple[date, str]]:
    """One (night, url) pair per night for a template; one pair otherwise.

    An undated URL is fetched ONCE. Requesting it per night would be thirty
    identical requests to somebody else's server for a single answer, and every
    one of them would be filed under a different night as though it differed.
    """
    if not is_dated_template(url):
        return [(start, url)]
    out: list[tuple[date, str]] = []
    night = start
    while night <= end and len(out) < MAX_NIGHTS_PER_COLLECTION:
        # checkout is the night AFTER checkin: this system prices one night at
        # a time, and checkin == checkout is a zero-night stay.
        checkout = date.fromordinal(night.toordinal() + 1)
        out.append(
            (
                night,
                url.replace(CHECKIN_PLACEHOLDER, night.isoformat()).replace(
                    CHECKOUT_PLACEHOLDER, checkout.isoformat()
                ),
            )
        )
        night = date.fromordinal(night.toordinal() + 1)
    return out


_MIN_PLAUSIBLE_VND = 200_000
_MAX_PLAUSIBLE_VND = 50_000_000


@dataclass
class CollectionReport:
    """What the last run actually did.

    Without it a collector that silently stopped extracting prices is
    indistinguishable from a market with nothing to say: the chart does not
    error, it just thins out. This is what lets the page say "12 fetches, 0
    prices found".
    """

    attempted: int = 0
    prices_found: int = 0
    errors: list[str] = field(default_factory=list)
    truncated_nights: int = 0
    ran_at: datetime | None = None


class PublicWebMarketDataProvider(MarketDataProvider):
    name = "PublicWebMarketDataProvider"
    mode = "public_web"
    # A generic web page cannot tell us the price basis, so this provider is
    # structurally incapable of producing evidence good enough to move a rate.
    max_confidence = CONFIDENCE_LOW

    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.market_public_enabled
        self.user_agent = settings.market_user_agent
        self.timeout = settings.market_http_timeout_seconds
        self.sources = [
            s.strip() for s in os.getenv("MARKET_PUBLIC_SOURCES", "").split(",") if s.strip()
        ]
        #: The last run, for the status line on the Market report.
        self.last_run: CollectionReport | None = None

    # ------------------------------------------------------------------
    def status(self) -> ProviderStatus:
        if not self.enabled:
            return ProviderStatus(
                name=self.name,
                healthy=False,
                mode=self.mode,
                detail="Public web collection is disabled (MARKET_PUBLIC_ENABLED=false).",
                remediation=(
                    "Set MARKET_PUBLIC_ENABLED=true and list permitted public URLs in "
                    "MARKET_PUBLIC_SOURCES. Prefer mock or manual market data for demos."
                ),
            )
        if not self.sources:
            return ProviderStatus(
                name=self.name,
                healthy=False,
                mode=self.mode,
                detail="Enabled, but no source URLs configured.",
                remediation="Set MARKET_PUBLIC_SOURCES to a comma-separated list of public URLs.",
            )
        return ProviderStatus(
            name=self.name,
            healthy=True,
            mode=self.mode,
            detail=f"{len(self.sources)} public source(s) configured. Extraction is best-effort.",
        )

    # ------------------------------------------------------------------
    def collect(self, start: date, end: date, **kwargs) -> list[MarketObservationDTO]:
        if not self.enabled:
            raise ProviderUnavailable(
                self.name,
                "Public web market collection is disabled.",
                remediation="Set MARKET_PUBLIC_ENABLED=true, or use the mock/manual provider.",
            )
        if not self.sources:
            raise ProviderUnavailable(
                self.name,
                "No public source URLs are configured.",
                remediation="Set MARKET_PUBLIC_SOURCES in .env.",
            )

        property_external_id = kwargs.get("property_external_id")
        room_type_external_id = kwargs.get("room_type_external_id")
        # An explicit stay_date pins the whole collection to one night, which is
        # what the single-date "collect now" action wants.
        pinned = kwargs.get("stay_date")
        first, last = (pinned, pinned) if pinned else (start, end)

        observations: list[MarketObservationDTO] = []
        errors: list[str] = []
        report = CollectionReport(ran_at=datetime.now(timezone.utc).replace(tzinfo=None))

        for url in self.sources:
            pairs = nightly_urls(url, first, last)
            wanted = (last - first).days + 1
            if is_dated_template(url) and wanted > len(pairs):
                # Say what was dropped. A silently short band reads as a quiet
                # market rather than as a truncated collection.
                skipped = wanted - len(pairs)
                report.truncated_nights = max(report.truncated_nights, skipped)
                errors.append(
                    f"{url}: capped at {MAX_NIGHTS_PER_COLLECTION} nights; {skipped} not fetched."
                )
            for night, resolved in pairs:
                report.attempted += 1
                try:
                    observations.extend(
                        self._collect_one(
                            resolved, night, property_external_id, room_type_external_id
                        )
                    )
                except ProviderUnavailable as exc:
                    errors.append(f"{resolved}: {exc.message}")
                except Exception as exc:  # network, parse, anything
                    errors.append(f"{resolved}: {type(exc).__name__}: {exc}")

        report.prices_found = len(observations)
        report.errors = errors
        self.last_run = report

        if not observations and errors:
            raise ProviderUnavailable(
                self.name,
                "No prices could be extracted from any configured public source. "
                + " | ".join(errors[:3]),
                remediation=(
                    "This prototype only handles server-rendered prices. Fall back to manual "
                    "market entry — see docs/MARKET_DATA.md."
                ),
            )
        return observations

    # ------------------------------------------------------------------
    def _collect_one(
        self,
        url: str,
        stay_date: date,
        property_external_id: str | None,
        room_type_external_id: str | None,
    ) -> list[MarketObservationDTO]:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()

        if any(blocked in host for blocked in BLOCKED_HOSTS):
            raise ProviderUnavailable(
                self.name,
                f"Refusing to collect from {host}: this OTA's terms prohibit automated access.",
                remediation="Use manual market entry for OTA reference prices.",
            )

        if not self._robots_allows(parsed):
            raise ProviderUnavailable(
                self.name,
                f"robots.txt at {host} disallows automated access to this path.",
                remediation="Respect the site's robots policy; enter this reference manually.",
            )

        prices = self._extract_prices(self._fetch_html(url))
        if not prices:
            raise ProviderUnavailable(
                self.name,
                "No VND-shaped prices found (page is likely client-rendered).",
                remediation="Use manual market entry for this source.",
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        label = host or "public-web"
        return [
            MarketObservationDTO(
                stay_date=stay_date,
                competitor_name=label,
                observed_price=price,
                source="public_web",
                property_external_id=property_external_id,
                room_type_external_id=room_type_external_id,
                source_url=url,
                notes="Best-effort extraction from a public, robots-permitted page.",
                room_category=None,
                confidence=CONFIDENCE_LOW,
                confidence_reason=(
                    "Generic web price: the page does not state stay date, length of stay, "
                    "room category, tax/fee basis or promotion status, so it is not "
                    "comparable to a Luminous NET rate."
                ),
                observed_at=now,
            )
            for price in prices
        ]

    # ------------------------------------------------------------------
    def _fetch_html(self, url: str) -> str:
        """The ONE place this provider touches the network.

        Its own method so collection logic can be exercised without a network,
        and so every refusal stays in a single readable place.
        """
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/json"}
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)

        if response.status_code in (401, 403, 429):
            # Explicitly do NOT retry, rotate, or work around this.
            raise ProviderUnavailable(
                self.name,
                f"Source returned HTTP {response.status_code}; treating it as 'do not collect'.",
                remediation="Do not attempt to bypass. Use manual market entry instead.",
            )
        response.raise_for_status()
        return response.text

    # ------------------------------------------------------------------
    def _robots_allows(self, parsed) -> bool:
        try:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
            rp.read()
            return rp.can_fetch(self.user_agent, parsed.geturl())
        except Exception:
            # If robots.txt is unreachable we do NOT assume permission.
            return False

    @staticmethod
    def _extract_prices(text: str) -> list[float]:
        found: list[float] = []
        for raw in _PRICE_PATTERN.findall(text):
            digits = re.sub(r"[^0-9]", "", raw)
            if not digits:
                continue
            value = float(digits)
            if _MIN_PLAUSIBLE_VND <= value <= _MAX_PLAUSIBLE_VND:
                found.append(value)
        # De-duplicate, keep a sane cap: this is a prototype, not a crawler.
        unique = sorted(set(found))
        return unique[:20]
