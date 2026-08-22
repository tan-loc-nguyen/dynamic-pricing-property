"""Pricing engine interface + result types.

Any future engine (FinancePricingEngine, PricingEngineV2, ...) only has to
subclass ``PricingEngine`` and return a ``PricingResult``. Nothing else in the
system — UI, API, persistence, providers — needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from ..features.context import PricingContext


@dataclass(frozen=True)
class Adjustment:
    """One explainable step of the calculation."""

    code: str
    label: str
    factor: float
    price_before: float
    price_after: float
    delta: float
    reason: str = ""
    is_neutral: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PricingResult:
    recommended_price: float
    base_price: float
    current_price: float
    price_before_bounds: float
    total_multiplier: float
    adjustments: list[Adjustment]
    explanation: str
    engine_version: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def change_pct(self) -> float:
        if not self.current_price:
            return 0.0
        return round((self.recommended_price - self.current_price) / self.current_price * 100, 2)

    @property
    def change_abs(self) -> float:
        return round(self.recommended_price - self.current_price, 2)


class PricingEngine(ABC):
    """Stable contract. Implementations must be deterministic and side-effect free."""

    name: str = "abstract"
    version: str = "0"
    description: str = ""

    @abstractmethod
    def calculate(self, context: PricingContext, configuration: dict[str, Any]) -> PricingResult:
        """Return a recommendation for one room + stay date.

        MUST be pure: identical (context, configuration) -> identical result.
        MUST NOT raise because an optional signal is absent; apply a neutral
        factor and explain the absence instead.
        """
        raise NotImplementedError
