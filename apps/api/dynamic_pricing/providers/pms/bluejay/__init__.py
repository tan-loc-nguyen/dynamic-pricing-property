"""Blue Jay PMS adapter.

Nothing outside this package may know Blue Jay exists (see ../base.py). The
package is split so the parts that can be tested without a network — window
arithmetic, normalisation, sanitisation — are separable from the client.
"""

from __future__ import annotations

from . import client, normalize, sanitize, windows
from .snapshot import SnapshotPMSProvider
from .provider import UNRESOLVED_MAPPINGS, BlueJayPMSProvider

__all__ = [
    "BlueJayPMSProvider", "SnapshotPMSProvider", "UNRESOLVED_MAPPINGS",
    "client", "normalize", "sanitize", "windows",
]
