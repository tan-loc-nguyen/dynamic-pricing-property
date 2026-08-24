"""PMS provider selection.

The rest of the app calls ``get_pms_provider()`` and never names a vendor.
"""

from __future__ import annotations

from datetime import date

from ...config import get_settings
from ...lookup import resolve
from .base import PMSProvider
from .bluejay import BlueJayPMSProvider
from .mock import MockPMSProvider

_REGISTRY: dict[str, type[PMSProvider]] = {
    "mock": MockPMSProvider,
    "bluejay": BlueJayPMSProvider,
}


def get_pms_provider(name: str | None = None, today: date | None = None) -> PMSProvider:
    """Resolve a PMS provider. An unknown key RAISES rather than substituting.

    A typo in DATA_PROVIDER previously ran the mock silently, and /api/status
    then reported the mock as the active provider without ever mentioning that
    the configured name was unrecognised.
    """
    settings = get_settings()
    cls = resolve(
        _REGISTRY, name or settings.data_provider, kind="PMS provider", default="mock"
    )
    if cls is MockPMSProvider:
        return MockPMSProvider(seed=settings.demo_seed, today=today)
    return cls()


def list_pms_providers() -> list[str]:
    return sorted(_REGISTRY)
