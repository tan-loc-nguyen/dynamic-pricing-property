"""PMS provider selection.

The rest of the app calls ``get_pms_provider()`` and never names a vendor.
"""

from __future__ import annotations

from datetime import date

from ...config import get_settings
from .base import PMSProvider
from .bluejay import BlueJayPMSProvider
from .mock import MockPMSProvider

_REGISTRY: dict[str, type[PMSProvider]] = {
    "mock": MockPMSProvider,
    "bluejay": BlueJayPMSProvider,
}


def get_pms_provider(name: str | None = None, today: date | None = None) -> PMSProvider:
    settings = get_settings()
    key = (name or settings.data_provider or "mock").lower()
    cls = _REGISTRY.get(key, MockPMSProvider)
    if cls is MockPMSProvider:
        return MockPMSProvider(seed=settings.demo_seed, today=today)
    return cls()


def list_pms_providers() -> list[str]:
    return sorted(_REGISTRY)
