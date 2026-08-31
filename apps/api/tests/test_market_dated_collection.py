"""Per-night market collection.

The Market report plots a band per night across the next 30 days. A URL fetched
verbatim cannot answer that: the collector stamps it with a stay date it never
asked the site for, so one number stands in for every night — a flat line
wearing the costume of a market band.

A source configured as a TEMPLATE carries the dates into the request, so the
price it returns belongs to the night it is filed under.
"""

from __future__ import annotations

from datetime import date

import pytest

from dynamic_pricing.providers.pms.base import ProviderUnavailable
from dynamic_pricing.providers.market.public_web import (
    MAX_NIGHTS_PER_COLLECTION,
    is_dated_template,
    nightly_urls,
)


def test_a_template_is_recognised_by_its_placeholders():
    assert is_dated_template("https://h.example/book?checkin={checkin}&checkout={checkout}")
    assert not is_dated_template("https://h.example/rooms")


def test_a_template_becomes_one_url_per_night_with_real_dates():
    """checkout is the night AFTER checkin -- a one-night stay, which is the
    grain this system prices at. Asking for checkin==checkout would return
    either nothing or a zero-night quote."""
    urls = nightly_urls(
        "https://h.example/book?checkin={checkin}&checkout={checkout}",
        date(2026, 9, 1),
        date(2026, 9, 3),
    )

    assert urls == [
        (date(2026, 9, 1), "https://h.example/book?checkin=2026-09-01&checkout=2026-09-02"),
        (date(2026, 9, 2), "https://h.example/book?checkin=2026-09-02&checkout=2026-09-03"),
        (date(2026, 9, 3), "https://h.example/book?checkin=2026-09-03&checkout=2026-09-04"),
    ]


def test_an_undated_url_is_fetched_once_for_the_range_start():
    """Not once per night. Requesting the same URL thirty times would be thirty
    identical requests to somebody else's server for one answer."""
    urls = nightly_urls("https://h.example/rooms", date(2026, 9, 1), date(2026, 9, 30))

    assert urls == [(date(2026, 9, 1), "https://h.example/rooms")]


def test_a_long_range_is_capped_and_the_cap_is_visible():
    """A 200-night range must not become 200 requests to a small hotel's site.

    The cap is REPORTED by returning fewer urls than nights asked for, so the
    caller can say which nights were skipped rather than presenting a short
    band as a complete one.
    """
    urls = nightly_urls(
        "https://h.example/book?checkin={checkin}&checkout={checkout}",
        date(2026, 9, 1),
        date(2027, 3, 1),
    )

    assert len(urls) == MAX_NIGHTS_PER_COLLECTION
    assert urls[0][0] == date(2026, 9, 1)


def _templated_provider(monkeypatch, html="Phòng từ 2.450.000 ₫ / đêm"):
    """A provider wired to a fake page, so no test touches the network."""
    import os

    from dynamic_pricing.config import get_settings
    from dynamic_pricing.providers.market.public_web import PublicWebMarketDataProvider

    monkeypatch.setenv("MARKET_PUBLIC_ENABLED", "true")
    monkeypatch.setenv(
        "MARKET_PUBLIC_SOURCES",
        "https://h.example/book?checkin={checkin}&checkout={checkout}",
    )
    get_settings.cache_clear()
    provider = PublicWebMarketDataProvider()
    get_settings.cache_clear()
    os.environ.pop("MARKET_PUBLIC_ENABLED", None)

    monkeypatch.setattr(provider, "_robots_allows", lambda _parsed: True)
    fetched: list[str] = []

    def fake_fetch(url: str) -> str:
        fetched.append(url)
        return html

    monkeypatch.setattr(provider, "_fetch_html", fake_fetch)
    return provider, fetched


def test_each_night_is_filed_under_the_date_it_was_asked_about(monkeypatch):
    provider, fetched = _templated_provider(monkeypatch)

    observations = provider.collect(date(2026, 9, 1), date(2026, 9, 3))

    assert len(fetched) == 3, "a dated template is fetched once per night"
    assert "checkin=2026-09-02" in fetched[1]
    assert {o.stay_date for o in observations} == {
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    }


def test_the_collection_reports_what_it_attempted_and_what_it_found(monkeypatch):
    """A dead collector and a calm market must not render the same.

    If a competitor's site changes its markup the chart does not error -- it
    just thins out, which looks exactly like a quiet market. The run report is
    what lets the page say "12 fetches, 0 prices found" instead.
    """
    provider, _ = _templated_provider(monkeypatch, html="<p>no prices here</p>")

    # Named, not blind: extracting nothing from every source must raise
    # ProviderUnavailable rather than return an empty list, because zero
    # observations and a failed collection are different answers.
    with pytest.raises(ProviderUnavailable):
        provider.collect(date(2026, 9, 1), date(2026, 9, 3))

    assert provider.last_run is not None
    assert provider.last_run.attempted == 3
    assert provider.last_run.prices_found == 0
