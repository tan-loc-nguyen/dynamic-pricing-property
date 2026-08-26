"""Operator-changeable integration settings: which PMS source, and the map.

The environment SEEDS these; the database owns them afterwards. See
``models.IntegrationSetting`` for why that boundary is drawn here and not in
``config.py``.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import IntegrationSetting
from ..pricing.rate_book import ROOM_CATEGORIES

PMS_SOURCE_KEY = "pms_source"
CATEGORY_MAP_KEY = "bluejay_category_map"
LAST_SYNC_FINDINGS_KEY = "last_sync_findings"

VALID_CATEGORIES = frozenset(c["key"] for c in ROOM_CATEGORIES)


def _get(session: Session, key: str, default: Any) -> Any:
    row = session.scalars(
        select(IntegrationSetting).where(IntegrationSetting.key == key)
    ).one_or_none()
    if row is None:
        return default
    try:
        value = json.loads(row.value_json)
    except ValueError:
        return default
    return default if value is None else value


def _set(session: Session, key: str, value: Any) -> None:
    row = session.scalars(
        select(IntegrationSetting).where(IntegrationSetting.key == key)
    ).one_or_none()
    if row is None:
        row = IntegrationSetting(key=key)
        session.add(row)
    row.value_json = json.dumps(value)
    session.commit()


def get_pms_source(session: Session) -> str:
    """The active PMS source, falling back to DATA_PROVIDER for a fresh install."""
    return str(_get(session, PMS_SOURCE_KEY, get_settings().data_provider))


def set_pms_source(session: Session, source: str) -> None:
    _set(session, PMS_SOURCE_KEY, source)


def get_category_map(session: Session) -> dict[str, str]:
    """Blue Jay ``roomtypeId`` -> our pricing category.

    Keyed on the ID, never the display name: the reservation payload references
    room types by localised name only, and those names are editable in Blue
    Jay's UI. Rebuilding name->category from ``roomtype-list`` on each sync
    means a rename cannot silently unmap a category.
    """
    value = _get(session, CATEGORY_MAP_KEY, {})
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def set_category_map(session: Session, mapping: dict[str, str]) -> None:
    _set(session, CATEGORY_MAP_KEY, {str(k): str(v) for k, v in mapping.items()})


def invalid_categories(mapping: dict[str, str]) -> list[str]:
    """Categories the pricing engine does not know. A typo here silently
    unmaps a whole room type, so it is rejected rather than stored."""
    return sorted({v for v in mapping.values() if v not in VALID_CATEGORIES})


def get_last_sync_findings(session: Session) -> dict:
    """What the last sync could not fully vouch for.

    Persisted rather than left in the `POST /api/sync` response body, because
    nothing consumed that body — so a warning that occupancy is OVERSTATED and
    recommendations biased upward travelled one hop further than before and
    still stopped short of a person.
    """
    value = _get(session, LAST_SYNC_FINDINGS_KEY, {})
    return value if isinstance(value, dict) else {}


def set_last_sync_findings(session: Session, findings: dict) -> None:
    _set(session, LAST_SYNC_FINDINGS_KEY, findings or {})
