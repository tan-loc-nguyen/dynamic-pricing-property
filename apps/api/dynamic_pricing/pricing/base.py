"""Pricing engine interface + result types.

Any future engine (FinancePricingEngine, PricingEngineV3, ...) subclasses
``PricingEngine`` and returns a ``PricingResult``. Nothing else in the system —
UI, API, persistence, providers — needs to change.

V2 is **additive**: each step contributes a percentage of the validated BASE
net rate. ``factor`` is retained so legacy multiplicative breakdowns still
render in the same UI.
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
    price_before: float
    price_after: float
    delta: float
    adjustment_pct: float = 0.0
    factor: float = 1.0
    reason: str = ""
    is_neutral: bool = False
    # True when a signal was observed but deliberately NOT applied — e.g. a
    # low-confidence market price. The operator still sees it.
    is_ignored: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PricingResult:
    recommended_net_rate: float
    base_net_rate: float
    current_net_rate: float
    net_rate_before_clamp: float
    total_adjustment_pct: float
    adjustments: list[Adjustment]
    explanation: str
    engine_version: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def change_pct(self) -> float:
        if not self.current_net_rate:
            return 0.0
        return round(
            (self.recommended_net_rate - self.current_net_rate) / self.current_net_rate * 100, 2
        )

    @property
    def change_abs(self) -> float:
        return round(self.recommended_net_rate - self.current_net_rate, 2)


class PricingEngine(ABC):
    """Stable contract. Implementations must be deterministic and side-effect free."""

    name: str = "abstract"
    version: str = "0"
    description: str = ""

    @abstractmethod
    def calculate(self, context: PricingContext, configuration: dict[str, Any]) -> PricingResult:
        """Return a NET-rate recommendation for one room type + stay date.

        MUST be pure: identical (context, configuration) -> identical result.
        MUST NOT raise because an optional signal is absent; apply a neutral
        adjustment and explain the absence instead.
        """
        raise NotImplementedError
