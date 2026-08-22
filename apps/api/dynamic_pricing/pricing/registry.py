"""Engine registry — the pluggability seam.

Swapping the active engine is a lookup, not a code change:

    from dynamic_pricing.pricing import get_engine
    engine = get_engine("v1")
"""

from __future__ import annotations

from .base import PricingEngine

_ENGINES: dict[str, type[PricingEngine]] = {}


def register_engine(key: str, engine_cls: type[PricingEngine]) -> type[PricingEngine]:
    _ENGINES[key.lower()] = engine_cls
    return engine_cls


def get_engine(key: str | None = None) -> PricingEngine:
    key = (key or "v1").lower()
    if key not in _ENGINES:
        raise KeyError(f"Unknown pricing engine '{key}'. Registered: {sorted(_ENGINES)}")
    return _ENGINES[key]()


def list_engines() -> list[dict[str, str]]:
    return [
        {"key": key, "name": cls.name, "version": cls.version, "description": cls.description}
        for key, cls in sorted(_ENGINES.items())
    ]
