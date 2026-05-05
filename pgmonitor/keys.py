"""Keyboard handling and key bindings for pg_monitor."""

from __future__ import annotations

import curses
from dataclasses import dataclass
from typing import Any

from .config import ColumnFlag
from .types import DurationMode, QueryMode, SortKey, enum_next


@dataclass(frozen=True)
class Key:
    """A keyboard binding.

    >>> key = Key("q", "quit application")
    >>> key.value
    'q'
    >>> key.description
    'quit application'
    >>> key == "q"
    True
    >>> key == "x"
    False
    """
    value: str
    description: str
    name: str | None = None
    local_only: bool = False

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value == other
        return False

    def __hash__(self) -> int:
        return hash((self.value, self.description, self.name))


# Key constants
EXIT = "q"
HELP = "h"
SPACE = " "
REFRESH_TIME_INCREASE = "+"
REFRESH_TIME_DECREASE = "-"
CHANGE_DURATION_MODE = "T"
WRAP_QUERY = "v"
REFRESH_DB_SIZE = "D"
PROCESS_CANCEL = "C"
PROCESS_KILL = "K"
COPY_TO_CLIPBOARD = "y"

# Navigation keys
PROCESS_NEXT = "KEY_DOWN"
PROCESS_PREV = "KEY_UP"
PROCESS_NEXT_VI = "j"
PROCESS_PREV_VI = "k"
PROCESS_NEXTPAGE = "KEY_NPAGE"
PROCESS_PREVPAGE = "KEY_PPAGE"
PROCESS_FIRST = "KEY_HOME"
PROCESS_LAST = "KEY_END"
CANCEL_SELECTION = "KEY_ESCAPE"

# Sort keys
SORTBY_CPU = "c"
SORTBY_MEM = "m"
SORTBY_READ = "r"
SORTBY_WRITE = "w"
SORTBY_TIME = "t"

# Header toggle keys
HEADER_TOGGLE_SYSTEM = "s"
HEADER_TOGGLE_INSTANCE = "i"
HEADER_TOGGLE_WORKERS = "o"


# Key bindings list for help display
EXIT_KEY = Key(EXIT, "quit")
PAUSE_KEY = Key(SPACE, "pause/unpause", "Space")
PROCESS_PIN = Key(SPACE, "tag/untag current query", "Space")

BINDINGS: list[Key] = [
    Key("Up/Down", "scroll process list"),
    PAUSE_KEY,
    Key(SORTBY_CPU, "sort by CPU% desc. (activities)", local_only=True),
    Key(SORTBY_MEM, "sort by MEM% desc. (activities)", local_only=True),
    Key(SORTBY_READ, "sort by READ/s desc. (activities)", local_only=True),
    Key(SORTBY_WRITE, "sort by WRITE/s desc. (activities)", local_only=True),
    Key(SORTBY_TIME, "sort by TIME+ desc. (activities)"),
    Key(REFRESH_TIME_INCREASE, "increase refresh time (max:5s)"),
    Key(REFRESH_TIME_DECREASE, "decrease refresh time (min:0.5s)"),
    Key(WRAP_QUERY, "toggle query wrap"),
    Key(CHANGE_DURATION_MODE, "change duration mode"),
    Key(REFRESH_DB_SIZE, "force refresh database size"),
    Key("R", "force refresh"),
    Key(HEADER_TOGGLE_SYSTEM, "Display system information in header", local_only=True),
    Key(HEADER_TOGGLE_INSTANCE, "Display general instance information in header"),
    Key(HEADER_TOGGLE_WORKERS, "Display worker information in header"),
    EXIT_KEY,
]


def _sequence_by_int(v: int) -> tuple[str, str, int]:
    """Get key sequence for function key.

    >>> _sequence_by_int(1)
    ('F1', '1', 265)
    >>> _sequence_by_int(3)
    ('F3', '3', 267)
    """
    assert 1 <= v <= 12, v
    return f"F{v}", str(v), getattr(curses, f"KEY_F{v}")


# Map query modes to function keys
KEYS_BY_QUERYMODE: dict[QueryMode, tuple[str, str, int]] = {
    QueryMode.activities: _sequence_by_int(1),
    QueryMode.waiting: _sequence_by_int(2),
    QueryMode.blocking: _sequence_by_int(3),
}

# Reverse mapping from key to query mode
QUERYMODE_FROM_KEYS: dict[str | int, QueryMode] = {
    k: qm for qm, keys in KEYS_BY_QUERYMODE.items() for k in keys[1:]
}

# Mode keys for help display
MODES: list[Key] = [
    Key("/".join(KEYS_BY_QUERYMODE[qm][:-1]), qm.value) for qm in QueryMode
]


def is_process_next(key: Any) -> bool:
    """Check if key is process next (down arrow or j).

    >>> class K:
    ...     def __init__(self, name=None, val=''):
    ...         self.name = name
    ...         self._val = val
    ...     def __eq__(self, other):
    ...         return self._val == other
    >>> is_process_next(K(name="KEY_DOWN"))
    True
    >>> is_process_next(K(val="j"))
    True
    >>> is_process_next(K(val="x"))
    False
    """
    if hasattr(key, 'name') and key.name == PROCESS_NEXT:
        return True
    if key == PROCESS_NEXT_VI:
        return True
    return False


def is_process_prev(key: Any) -> bool:
    """Check if key is process previous (up arrow or k).

    >>> class K:
    ...     def __init__(self, name=None, val=''):
    ...         self.name = name
    ...         self._val = val
    ...     def __eq__(self, other):
    ...         return self._val == other
    >>> is_process_prev(K(name="KEY_UP"))
    True
    >>> is_process_prev(K(val="k"))
    True
    """
    if hasattr(key, 'name') and key.name == PROCESS_PREV:
        return True
    if key == PROCESS_PREV_VI:
        return True
    return False


def is_process_nextpage(key: Any) -> bool:
    """Check if key is page down."""
    return hasattr(key, 'name') and key.name == PROCESS_NEXTPAGE


def is_process_prevpage(key: Any) -> bool:
    """Check if key is page up."""
    return hasattr(key, 'name') and key.name == PROCESS_PREVPAGE


def is_process_first(key: Any) -> bool:
    """Check if key is Home."""
    return hasattr(key, 'name') and key.name == PROCESS_FIRST


def is_process_last(key: Any) -> bool:
    """Check if key is End."""
    return hasattr(key, 'name') and key.name == PROCESS_LAST


def is_toggle_header_system(key: Any) -> bool:
    """Check if key toggles system header."""
    return key == HEADER_TOGGLE_SYSTEM


def is_toggle_header_instance(key: Any) -> bool:
    """Check if key toggles instance header."""
    return key == HEADER_TOGGLE_INSTANCE


def is_toggle_header_workers(key: Any) -> bool:
    """Check if key toggles workers header."""
    return key == HEADER_TOGGLE_WORKERS


def handle_refresh_time(
    key: str | None,
    current: float,
    minimum: float = 0.5,
    maximum: float = 5.0,
) -> float:
    """Adjust refresh time based on key press.

    >>> handle_refresh_time("+", 1.0)
    2.0
    >>> handle_refresh_time("+", 5.0)
    5.0
    >>> handle_refresh_time("-", 2.0)
    1.0
    >>> handle_refresh_time("-", 0.5)
    0.5
    >>> handle_refresh_time("x", 1.0)
    Traceback (most recent call last):
        ...
    ValueError: invalid key 'x'
    """
    if key == REFRESH_TIME_DECREASE:
        return max(current - 1, minimum)
    elif key == REFRESH_TIME_INCREASE:
        return min(float(current + 1), maximum)
    raise ValueError(f"invalid key {key!r}")


def handle_duration_mode(key: Any, current: DurationMode) -> DurationMode:
    """Change duration mode based on key press.

    >>> handle_duration_mode("T", DurationMode.query)
    <DurationMode.transaction: 2>
    >>> handle_duration_mode("T", DurationMode.transaction)
    <DurationMode.backend: 3>
    >>> handle_duration_mode("T", DurationMode.backend)
    <DurationMode.query: 1>
    >>> handle_duration_mode("x", DurationMode.query)
    <DurationMode.query: 1>
    """
    if key == CHANGE_DURATION_MODE:
        return enum_next(current)
    return current


def handle_wrap_query(key: Any, current: bool) -> bool:
    """Toggle query wrap based on key press.

    >>> handle_wrap_query("v", False)
    True
    >>> handle_wrap_query("v", True)
    False
    >>> handle_wrap_query("x", True)
    True
    """
    if key == WRAP_QUERY:
        return not current
    return current


def handle_query_mode(key: Any) -> QueryMode | None:
    """Get query mode from key press.

    >>> handle_query_mode("1")
    <QueryMode.activities: 'running queries'>
    >>> handle_query_mode("2")
    <QueryMode.waiting: 'waiting queries'>
    >>> handle_query_mode("3")
    <QueryMode.blocking: 'blocking queries'>
    >>> handle_query_mode("x") is None
    True
    """
    # Check for function key codes
    if hasattr(key, 'is_sequence') and key.is_sequence and hasattr(key, 'code'):
        try:
            return QUERYMODE_FROM_KEYS[key.code]
        except KeyError:
            pass
    # Check for string keys
    try:
        if isinstance(key, str):
            return QUERYMODE_FROM_KEYS[key]
        return QUERYMODE_FROM_KEYS.get(str(key))
    except (KeyError, TypeError):
        return None


def handle_sort_key(
    key: Any,
    query_mode: QueryMode,
    flag: ColumnFlag,
) -> SortKey | None:
    """Get sort key from key press.

    >>> handle_sort_key("c", QueryMode.activities, ColumnFlag.all())
    <SortKey.cpu: 1>
    >>> handle_sort_key("m", QueryMode.activities, ColumnFlag.all())
    <SortKey.mem: 2>
    >>> handle_sort_key("r", QueryMode.activities, ColumnFlag.all())
    <SortKey.read: 3>
    >>> handle_sort_key("w", QueryMode.activities, ColumnFlag.all())
    <SortKey.write: 4>
    >>> handle_sort_key("t", QueryMode.activities, ColumnFlag.all())
    <SortKey.duration: 5>
    >>> handle_sort_key("x", QueryMode.activities, ColumnFlag.all()) is None
    True
    >>> handle_sort_key("c", QueryMode.waiting, ColumnFlag.all())
    <SortKey.duration: 5>
    """
    # In non-activities mode, always return duration
    if query_mode != QueryMode.activities:
        return SortKey.default()

    # Map keys to sort keys with required flags
    key_map: dict[str, tuple[SortKey, ColumnFlag]] = {
        SORTBY_CPU: (SortKey.cpu, ColumnFlag.CPU),
        SORTBY_MEM: (SortKey.mem, ColumnFlag.MEM),
        SORTBY_READ: (SortKey.read, ColumnFlag.READ),
        SORTBY_WRITE: (SortKey.write, ColumnFlag.WRITE),
        SORTBY_TIME: (SortKey.duration, ColumnFlag.TIME),
    }

    key_str = str(key) if not isinstance(key, str) else key
    try:
        sort_key, required_flag = key_map[key_str]
    except KeyError:
        return None

    # Check if the required flag is enabled
    if flag & required_flag:
        return sort_key
    return None
