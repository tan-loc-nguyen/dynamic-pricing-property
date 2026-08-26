"""The developer/data panel: which PMS source is live, and can we call Blue Jay.

Deliberately small. It reports the ACTIVE source rather than assuming one, and
it always says when Blue Jay's testing window next opens — an integration you
can only reach for ninety minutes a day is one where "why is this failing?"
has a boring answer most of the time.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..providers.pms import get_pms_provider, list_pms_providers
from ..providers.pms.bluejay import windows
from ..services.integration import (
    VALID_CATEGORIES,
    get_category_map,
    get_pms_source,
    invalid_categories,
    set_category_map,
    set_pms_source,
)

router = APIRouter(prefix="/api/pms", tags=["pms"])


class SourceIn(BaseModel):
    source: str


class CategoryMapIn(BaseModel):
    map: dict[str, str]


def _window_payload() -> dict:
    status = windows.window_status()
    return {
        "timezone": "Asia/Ho_Chi_Minh",
        "now": status.now_vn.isoformat(),
        "is_open": status.is_open,
        "next_open_at": status.next_open_at.isoformat() if status.next_open_at else None,
        "seconds_until_open": status.seconds_until_open,
        "windows": [
            {
                "text": w.source_text,
                "confirmed": w.confirmed,
                # The note explains an ambiguity in Blue Jay's own document; it
                # is developer-facing (D30) and shown verbatim.
                "note": w.note,
            }
            for w in windows.TESTING_WINDOWS
        ],
    }


@router.get("/source")
def read_source(session: Session = Depends(get_session)) -> dict:
    active = get_pms_source(session)
    return {
        "active": active,
        "available": list_pms_providers(),
        # label_key, not a sentence: the operator reads this in Vietnamese (D30).
        "sources": [
            {"key": key, "label_key": f"dataSource.{key}.label", "hint_key": f"dataSource.{key}.hint"}
            for key in list_pms_providers()
        ],
        "bluejay_window": _window_payload(),
    }


@router.put("/source")
def write_source(payload: SourceIn, session: Session = Depends(get_session)) -> dict:
    if payload.source not in list_pms_providers():
        # Names the valid options rather than discarding the one piece of
        # information the caller needs (see lookup.UnknownRegistryKey).
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown PMS source {payload.source!r}. "
                f"Valid options: {', '.join(list_pms_providers())}."
            ),
        )
    set_pms_source(session, payload.source)
    return {"active": payload.source}


@router.get("/category-map")
def read_category_map(session: Session = Depends(get_session)) -> dict:
    """The map, the categories to choose from, AND what still needs choosing.

    Without the third the panel can only edit mappings that already exist, and
    the room type that is going unpriced right now is invisible on the one
    screen built to fix it.
    """
    mapping = get_category_map(session)
    unmapped: list[dict] = []
    try:
        provider = get_pms_provider(get_pms_source(session), category_map=mapping)
        # Duck-typed: only a Blue Jay-backed provider has room types to
        # discover, and MOCK legitimately has none.
        discover = getattr(provider, "discover_room_types", None)
        if callable(discover):
            unmapped = discover()
    except Exception:  # noqa: BLE001
        # Never let discovery break the settings screen — it is where an
        # operator goes to fix precisely the outage that would break it.
        unmapped = []
    return {
        "map": mapping,
        "categories": sorted(VALID_CATEGORIES),
        "unmapped": unmapped,
    }


@router.put("/category-map")
def write_category_map(payload: CategoryMapIn, session: Session = Depends(get_session)) -> dict:
    unknown = invalid_categories(payload.map)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown pricing categor{'y' if len(unknown) == 1 else 'ies'}: "
                f"{', '.join(unknown)}. Valid options: {', '.join(sorted(VALID_CATEGORIES))}."
            ),
        )
    set_category_map(session, payload.map)
    return {"map": payload.map}
