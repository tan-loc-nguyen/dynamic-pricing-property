"""Engine registry — the pluggability seam.

Swapping the active engine is a lookup, not a code change:

    from dynamic_pricing.pricing import get_engine
    engine = get_engine()          # the default
    engine = get_engine("finance") # or a specific one
"""

from __future__ import annotations

from ..lookup import resolve
from .base import PricingEngine

# The single source of truth for which engine is active. Previously duplicated
# as a hardcoded fallback here AND as DEFAULT_ENGINE in __init__, and the two
# drifted: this one still said "v1" after the rename, so the documented
# no-argument call raised.
DEFAULT_ENGINE = "default"

_ENGINES: dict[str, type[PricingEngine]] = {}


def register_engine(key: str, engine_cls: type[PricingEngine]) -> type[PricingEngine]:
    _ENGINES[key.lower()] = engine_cls
    return engine_cls


def get_engine(key: str | None = None) -> PricingEngine:
    return resolve(_ENGINES, key, kind="pricing engine", default=DEFAULT_ENGINE)()


def list_engines() -> list[dict[str, str]]:
    return [
        {"key": key, "name": cls.name, "version": cls.version, "description": cls.description}
        for key, cls in sorted(_ENGINES.items())
    ]
