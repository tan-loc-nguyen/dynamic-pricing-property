"""MockMarketDataProvider — deterministic synthetic comp-set observations."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from ...pricing.rate_book import SeasonalRateBook
from ..pms.base import ProviderStatus
from ..pms.mock import PROPERTY, ROOM_TYPE_SPECS, SCENARIO_PLAN
from .base import (
    BASIS_NET,
    BASIS_OTA_SELL,
    CONFIDENCE_HIGH,
    MarketDataProvider,
    MarketObservationDTO,
)

# The demo comp set — deliberately selected comparable properties, not
# arbitrary search results. Names are invented; the real comp set must come
# from the operator (see ASSUMPTIONS.md U12).
DEMO_COMP_SET = [
    {"name": "The Riverside Residences", "location": "District 1", "basis": BASIS_NET},
    {"name": "Metropole Serviced Apartments", "location": "District 1", "basis": BASIS_NET},
    {"name": "Saigon Sky Suites", "location": "Binh Thanh", "basis": BASIS_OTA_SELL},
]


class MockMarketDataProvider(MarketDataProvider):
    name = "MockMarketDataProvider"
    mode = "mock"
    max_confidence = CONFIDENCE_HIGH

    def __init__(self, seed: int = 20260822, today: date | None = None) -> None:
        self.seed = seed
        self.today = today or date.today()
        self.rate_book = SeasonalRateBook()

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            healthy=True,
            mode=self.mode,
            detail=(
                f"Synthetic comp-set observations from {len(DEMO_COMP_SET)} comparable "
                f"properties, with full basis metadata."
            ),
        )

    def collect(self, start: date, end: date, **kwargs) -> list[MarketObservationDTO]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows: list[MarketObservationDTO] = []

        for ext_id, category, _name, _capacity, _units in ROOM_TYPE_SPECS:
            rng = random.Random(f"{self.seed}:{ext_id}:market")
            current = start
            while current <= end:
                offset = (current - self.today).days
                plan = SCENARIO_PLAN.get(offset, {})
                market_mode = plan.get("market")

                if market_mode == "none":
                    current += timedelta(days=1)
                    continue

                band = self.rate_book.lookup(category, current)
                anchor = band.base_net_rate if band else 2_000_000
                level = {"strong": 1.18, "weak": 0.86}.get(market_mode, 1.0)

                for comp in DEMO_COMP_SET:
                    price = anchor * level * rng.uniform(0.92, 1.10)
                    if market_mode == "low_conf":
                        # Deliberate scenario: only uninterpretable evidence exists.
                        rows.append(
                            MarketObservationDTO(
                                stay_date=current,
                                competitor_name=comp["name"],
                                competitor_name_key=comp["name"],
                                observed_price=round(price / 10_000) * 10_000,
                                # NOT "public_web": a mock sync replaces rows by
                                # source, and borrowing that name would delete
                                # genuinely collected public-web observations.
                                # It still scores LOW because the metadata below
                                # is deliberately absent.
                                source="mock_low_confidence",
                                property_external_id=PROPERTY.external_id,
                                room_type_external_id=ext_id,
                                room_category=None,
                                notes="Headline web price, basis unknown.",
                                observed_at=now - timedelta(hours=rng.randint(1, 30)),
                            )
                        )
                        continue

                    rows.append(
                        MarketObservationDTO(
                            stay_date=current,
                            competitor_name=comp["name"],
                            competitor_name_key=comp["name"],
                            observed_price=round(price / 10_000) * 10_000,
                            source="mock",
                            property_external_id=PROPERTY.external_id,
                            room_type_external_id=ext_id,
                            room_category=category,
                            length_of_stay=1,
                            guests=2,
                            price_basis=comp["basis"],
                            tax_inclusion="EXCLUSIVE",
                            fee_inclusion="EXCLUSIVE",
                            promotion_status="NONE",
                            is_refundable=True,
                            notes="Synthetic comp-set observation.",
                            observed_at=now - timedelta(hours=rng.randint(1, 30)),
                        )
                    )
                current += timedelta(days=1)
        return rows
