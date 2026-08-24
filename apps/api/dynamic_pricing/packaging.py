"""Where things live, in a source checkout and inside a packaged binary.

PyInstaller's ``--onefile`` build unpacks itself into a temporary directory and
deletes it on exit. That makes exactly one distinction matter everywhere else
in the app:

* **read-only things** (the exported web bundle) ship INSIDE the binary;
* **the database** must not, or the operator loses every decision they
  recorded the moment they close the window.

Keeping both answers here means the rest of the code never has to ask whether
it is frozen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: The repository root in a source checkout. Meaningless in a frozen build --
#: use :func:`bundle_root` for read-only data and :func:`user_data_dir` for
#: anything written.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Directory name used under the platform's application-data location.
APP_DIR_NAME = "DynamicPricingProperty"


def is_frozen() -> bool:
    """True when running from a PyInstaller build rather than a checkout."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Root for READ-ONLY files that ship with the app.

    In a frozen build this is PyInstaller's extraction directory, which exists
    only for the lifetime of the process.
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return REPO_ROOT


def user_data_dir() -> Path:
    """Directory for files the app WRITES. Never inside the bundle.

    A source checkout keeps using ``data/`` at the repo root, so a developer's
    database does not move when this lands.
    """
    if not is_frozen():
        return REPO_ROOT / "data"

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")

    return base / APP_DIR_NAME


def web_dist() -> Path | None:
    """The exported Next.js bundle, or ``None`` when it has not been built.

    Absence is normal and must stay cheap to handle: ``make dev`` serves the
    frontend from Next's own dev server on :3000 and never exports at all.
    Returning a path that does not exist would make FastAPI raise at import.
    """
    candidate = bundle_root() / "web" if is_frozen() else REPO_ROOT / "apps" / "web" / "out"
    return candidate if candidate.is_dir() else None
