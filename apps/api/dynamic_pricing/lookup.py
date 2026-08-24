"""One resolution behaviour for every registry in the system.

The three registries had drifted into opposite failure modes: the engine
registry RAISED on an unknown key (surfacing as a 500), while the PMS and
market registries SILENTLY SUBSTITUTED a default. The same operator typo
therefore either crashed the API or quietly fabricated data, depending only on
which registry it landed in — and in neither case named the valid keys.

The rule here, applied everywhere:

  * an EXPLICIT key that is not registered  -> raise, listing what is valid
  * an ABSENT key (None or blank)           -> use the declared default
  * a default that is itself not registered -> raise, because that is a bug

Silent substitution is never correct for a key a human supplied. It was
producing synthetic market observations reported as a successful collection.
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


class UnknownRegistryKey(LookupError):
    """An explicitly-supplied key that no registry entry matches.

    Carries the valid keys so callers can put them straight in a 422 body
    rather than discarding the one piece of information the user needs.
    """

    def __init__(self, kind: str, key: str, registered: list[str]) -> None:
        self.kind = kind
        self.key = key
        self.registered = registered
        super().__init__(
            f"Unknown {kind} '{key}'. Valid options: {', '.join(registered) or 'none registered'}."
        )


def resolve(
    registry: dict[str, T],
    key: str | None,
    *,
    kind: str,
    default: str,
) -> T:
    """Look up ``key``, falling back to ``default`` only when nothing was asked for."""
    requested = (key or "").strip().lower()
    if not requested:
        requested = default
    if requested not in registry:
        raise UnknownRegistryKey(kind, requested, sorted(registry))
    return registry[requested]
