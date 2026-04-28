"""Color utilities module."""
from __future__ import annotations

# Constants for special UI states
PINNED_COLOR = "on_bright_yellow"
FOCUSED_COLOR = "on_bright_cyan"


def wait(value: bool | str | None) -> str | None:
    """Return color for wait status.

    >>> wait(True)
    'red'
    >>> wait(False)
    >>> wait('ClientRead')
    'red'
    >>> wait(None)
    """
    if value:
        return "red"
    return None


def lock_mode(value: str | None) -> str | None:
    """Return color for lock mode.

    >>> lock_mode('ExclusiveLock')
    'red'
    >>> lock_mode('ShareLock')
    'green'
    >>> lock_mode(None)
    """
    if value is None:
        return None
    if "Exclusive" in value:
        return "red"
    if "Share" in value:
        return "green"
    return None


def short_state(value: str | None) -> str | None:
    """Return color for query state.

    >>> short_state('active')
    'green'
    >>> short_state('idle')
    >>> short_state('idle in trans')
    'yellow'
    >>> short_state('idle in trans (a)')
    'red'
    """
    if value is None:
        return None
    if value == "active":
        return "green"
    if "abort" in value.lower() or "(a)" in value:
        return "red"
    if "idle in trans" in value.lower():
        return "yellow"
    return None
