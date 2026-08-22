"""MockMarketDataProvider — deterministic synthetic competitor prices."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from ..pms.base import ProviderStatus
from ..pms.mock import ROOM_SPECS, SCENARIO_PLAN
from .base import MarketDataProvider, MarketObservationDTO

COMPETITOR_SETS = {
    "LUM-D1": ["The Reverie Residences", "Saigon Sky Apartments", "Bason Riverfront Suites"],
    "LUM-D2": ["An Phu Garden Homes", "Thao Dien Village Stay", "Metropole Residences"],
    "LUM-DN": ["My Khe Bay Apartments", "Son Tra Sea Suites", "Danang Marina Lofts"],
}


class MockMarketDataProvider(MarketDataProvider):
    name = "MockMarketDataProvider"
    mode = "mock"

    def __init__(self, seed: int = 20260822, today: date | None = None) -> None:
        self.seed = seed
        self.today = today or date.today()

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            healthy=True,
            mode=self.mode,
            detail="Synthetic competitor observations for every room and stay date.",
        )

    def collect(self, start: date, end: date, **kwargs) -> list[MarketObservationDTO]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows: list[MarketObservationDTO] = []
        for spec in ROOM_SPECS:
            competitors = COMPETITOR_SETS.get(spec.property_external_id, ["Reference set"])
            rng = random.Random(f"{self.seed}:{spec.external_id}:market")
            current = start
            while current <= end:
                offset = (current - self.today).days
                plan = SCENARIO_PLAN.get(offset, {})
                market_mode = plan.get("market")

                if market_mode == "none":
                    # Deliberate blind spot: proves the neutral-factor fallback.
                    current += timedelta(days=1)
                    continue

                weekday_lift = 1.12 if current.weekday() >= 4 else 1.0
                level = {"strong": 1.22, "weak": 0.84}.get(market_mode, 1.0)
                if plan.get("event"):
                    level *= 1.15

                for competitor in competitors:
                    price = spec.base_price * weekday_lift * level * rng.uniform(0.90, 1.12)
                    rows.append(
                        MarketObservationDTO(
                            stay_date=current,
                            competitor_name=competitor,
                            observed_price=round(price / 10_000) * 10_000,
                            source="mock",
                            property_external_id=spec.property_external_id,
                            room_external_id=spec.external_id,
                            source_url=None,
                            notes="Synthetic demo observation.",
                            collected_at=now - timedelta(hours=rng.randint(1, 36)),
                        )
                    )
                current += timedelta(days=1)
        return rows
