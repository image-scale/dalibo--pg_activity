"""Terminal rendering views for pg_monitor."""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from textwrap import TextWrapper
from typing import Any, Literal

from blessed import Terminal

from . import utils
from .keys import BINDINGS, EXIT_KEY, HELP, KEYS_BY_QUERYMODE, MODES, PAUSE_KEY, Key
from .types import (
    DurationMode,
    IOCounter,
    LocalRunningProcess,
    MemoryInfo,
    QueryMode,
    RunningProcess,
    SelectableProcesses,
    SortKey,
    SwapInfo,
    SystemInfo,
)


# Color constants
PINNED_COLOR = "bold_yellow"
FOCUSED_COLOR = "cyan_reverse"


def color_for_state(state: str) -> str | None:
    """Return color name for process state.

    >>> color_for_state("active")
    'green'
    >>> color_for_state("idle in trans")
    'yellow'
    >>> color_for_state("idle in trans (a)")
    'red'
    >>> color_for_state("idle") is None
    True
    """
    state = utils.short_state(state)
    if state == "active":
        return "green"
    elif state == "idle in trans":
        return "yellow"
    elif state == "idle in trans (a)":
        return "red"
    return None


def color_for_wait(value: bool) -> str:
    """Return color for wait value.

    >>> color_for_wait(True)
    'red'
    >>> color_for_wait(False)
    'green'
    """
    return "red" if value else "green"


def color_for_lock_mode(mode: str) -> str:
    """Return color for lock mode.

    >>> color_for_lock_mode("ExclusiveLock")
    'bold_red'
    >>> color_for_lock_mode("ShareLock")
    'bold_yellow'
    """
    if mode in ("ExclusiveLock", "RowExclusiveLock", "AccessExclusiveLock"):
        return "bold_red"
    return "bold_yellow"


@dataclass(frozen=True)
class Column:
    """A column in the process table.

    >>> c = Column("pid", "PID", min_width=6, max_width=6)
    >>> c.title_render()
    'PID   '
    >>> c.render(1234)
    '1234  '
    >>> c.render(12345678)
    '123456'

    >>> c = Column("cpu", "CPU%", min_width=5, max_width=5, justify="right",
    ...            transform=lambda v: f"{v:.1f}")
    >>> c.title_render()
    ' CPU%'
    >>> c.render(12.34)
    ' 12.3'
    """

    key: str
    name: str
    min_width: int = 8
    max_width: int | None = None
    justify: Literal["left", "right", "center"] = "left"
    transform: Callable[[Any], str] = field(default=lambda v: str(v) if v is not None else "")
    sort_key: SortKey | None = None
    color_func: Callable[[Any], str | None] | None = None

    def _justify_text(self, text: str) -> str:
        """Apply justification and width constraints."""
        max_w = self.max_width or self.min_width
        if self.justify == "left":
            result = text.ljust(self.min_width)
        elif self.justify == "right":
            result = text.rjust(self.min_width)
        else:  # center
            result = text.center(self.min_width)
        return result[:max_w]

    def title_render(self) -> str:
        """Render column title with proper width."""
        return self._justify_text(self.name)

    def title_color(self, current_sort: SortKey) -> str:
        """Return color for column title based on sort state.

        >>> c = Column("cpu", "CPU%", sort_key=SortKey.cpu)
        >>> c.title_color(SortKey.cpu)
        'cyan'
        >>> c.title_color(SortKey.duration)
        'green'
        """
        if self.sort_key == current_sort:
            return "cyan"
        return "green"

    def render(self, value: Any) -> str:
        """Render cell value with proper formatting."""
        text = self.transform(value)
        return self._justify_text(text)

    def color(self, value: Any) -> str | None:
        """Return color for cell value."""
        if self.color_func is not None:
            return self.color_func(value)
        return None


class LineCounter:
    """Counter for tracking available lines in terminal.

    >>> counter = LineCounter(5)
    >>> counter.value
    5
    >>> next(counter)
    5
    >>> counter.value
    4
    """

    def __init__(self, start: int) -> None:
        self.value = start

    def __repr__(self) -> str:
        return f"LineCounter({self.value})"

    def __next__(self) -> int:
        current = self.value
        self.value -= 1
        return current


def limit(func: Callable[..., Iterable[str]]) -> Callable[..., None]:
    """Decorator that limits output to available screen lines.

    >>> term = Terminal()
    >>> def view(term, n):
    ...     for i in range(n):
    ...         yield f"line {i}"
    >>> counter = LineCounter(2)
    >>> limit(view)(term, 5, lines_counter=counter)
    line 0
    line 1
    >>> counter.value
    0
    """
    @functools.wraps(func)
    def wrapper(term: Terminal, *args: Any, **kwargs: Any) -> None:
        counter = kwargs.pop("lines_counter", None)
        width = kwargs.pop("width", None)
        for line in func(term, *args, **kwargs):
            if width:
                # Truncate line to width
                line = line[:width]
            print(line + term.clear_eol)
            if counter is not None and next(counter) == 1:
                break

    return wrapper


@functools.lru_cache(maxsize=512)
def shorten(term: Terminal, text: str, width: int) -> str:
    """Truncate text to fit in width, handling terminal sequences."""
    if not text:
        return ""
    wrapped = term.wrap(text, width=width, max_lines=1)
    if wrapped:
        return wrapped[0] + term.normal
    return ""


def boxed(
    term: Terminal,
    content: str,
    *,
    border_color: str = "white",
    center: bool = False,
    width: int | None = None,
) -> str:
    """Draw a bordered box around content."""
    border_width = len(content) + 2
    color = getattr(term, border_color)
    lines = [
        color("+" + "-" * border_width + "+"),
        " ".join([color("|") + term.normal, content, color("|")]),
        color("+" + "-" * border_width + "+") + term.normal,
    ]
    if center and width:
        lines = [term.center(line, width=width) for line in lines]
    return "\n".join(lines)


def get_default_columns(query_mode: QueryMode, is_local: bool = True) -> list[Column]:
    """Get default columns for the given query mode.

    >>> cols = get_default_columns(QueryMode.activities, is_local=True)
    >>> [c.key for c in cols[:4]]
    ['pid', 'database', 'appname', 'user']
    """
    # Base columns for all modes
    base_cols = [
        Column("pid", "PID", min_width=7, max_width=7),
        Column("database", "DATABASE", min_width=10, max_width=16),
        Column("appname", "APP", min_width=10, max_width=16,
               transform=lambda v: utils.ellipsis(v or "", 16)),
        Column("user", "USER", min_width=10, max_width=16),
        Column("client", "CLIENT", min_width=16, max_width=22,
               transform=lambda v: str(v) if v else "local"),
    ]

    if query_mode == QueryMode.activities:
        if is_local:
            # Add local-only columns
            base_cols.extend([
                Column("cpu", "CPU%", min_width=6, max_width=6, justify="right",
                       transform=lambda v: f"{v:.1f}" if v is not None else "-",
                       sort_key=SortKey.cpu),
                Column("mem", "MEM%", min_width=6, max_width=6, justify="right",
                       transform=lambda v: f"{v:.1f}" if v is not None else "-",
                       sort_key=SortKey.mem),
                Column("read", "READ/s", min_width=9, max_width=9, justify="right",
                       transform=lambda v: utils.naturalsize(v) if v else "-",
                       sort_key=SortKey.read),
                Column("write", "WRITE/s", min_width=9, max_width=9, justify="right",
                       transform=lambda v: utils.naturalsize(v) if v else "-",
                       sort_key=SortKey.write),
            ])
        base_cols.extend([
            Column("duration", "TIME+", min_width=12, max_width=12, justify="right",
                   transform=lambda v: utils.format_duration(v)[0] if v is not None else "-",
                   color_func=lambda v: utils.format_duration(v)[1] if v is not None else None,
                   sort_key=SortKey.duration),
            Column("wait", "W", min_width=1, max_width=1,
                   transform=lambda v: utils.wait_status(v),
                   color_func=lambda v: color_for_wait(v) if isinstance(v, bool) else None),
            Column("state", "STATE", min_width=14, max_width=14,
                   transform=utils.short_state,
                   color_func=color_for_state),
        ])
    elif query_mode in (QueryMode.waiting, QueryMode.blocking):
        base_cols.extend([
            Column("mode", "MODE", min_width=20, max_width=20,
                   color_func=color_for_lock_mode),
            Column("type", "TYPE", min_width=15, max_width=15),
            Column("relation", "RELATION", min_width=20, max_width=20),
            Column("duration", "TIME+", min_width=12, max_width=12, justify="right",
                   transform=lambda v: utils.format_duration(v)[0] if v is not None else "-",
                   color_func=lambda v: utils.format_duration(v)[1] if v is not None else None,
                   sort_key=SortKey.duration),
        ])

    # Query column is always last
    base_cols.append(
        Column("query", "Query", min_width=20, max_width=None,
               transform=lambda v: utils.clean_str(v) if v else "")
    )

    return base_cols


@limit
def render_header(
    term: Terminal,
    *,
    pg_version: str,
    host: str,
    refresh_time: float,
    duration_mode: DurationMode,
    system_info: SystemInfo | None = None,
    show_instance: bool = True,
    show_system: bool = True,
) -> Iterator[str]:
    """Render header with server information.

    >>> term = Terminal()
    >>> from pgmonitor.types import DurationMode
    >>> list(render_header.__wrapped__(term, pg_version="PostgreSQL 15.0",
    ...     host="localhost", refresh_time=2.0, duration_mode=DurationMode.query))
    ['PostgreSQL 15.0 - localhost - Ref.: 2.0s - Duration mode: query']
    """

    def bold_green(text: str) -> str:
        return term.bold_green(text)

    # First line: version, host, refresh, duration mode
    line_parts = [
        pg_version,
        f"{term.bold}{host}{term.normal}",
        f"Ref.: {term.yellow}{refresh_time}s{term.normal}",
        f"Duration mode: {term.yellow}{duration_mode.name}{term.normal}",
    ]
    yield " - ".join(line_parts)

    # System info (if local)
    if system_info is not None and show_system:
        mem = system_info.memory
        swap = system_info.swap
        load = system_info.load

        # Memory line
        mem_parts = [
            f"* Mem.: {bold_green(utils.naturalsize(mem.total))} total",
            f"{bold_green(utils.naturalsize(mem.free))} ({bold_green(f'{mem.pct_free:.1f}%')}) free",
            f"{bold_green(utils.naturalsize(mem.used))} ({bold_green(f'{mem.pct_used:.1f}%')}) used",
            f"{bold_green(utils.naturalsize(mem.buff_cached))} ({bold_green(f'{mem.pct_bc:.1f}%')}) buff+cached",
        ]
        yield f"  {', '.join(mem_parts)}"

        # Swap line
        swap_parts = [
            f"  Swap: {bold_green(utils.naturalsize(swap.total))} total",
            f"{bold_green(utils.naturalsize(swap.free))} ({bold_green(f'{swap.pct_free:.1f}%')}) free",
            f"{bold_green(utils.naturalsize(swap.used))} ({bold_green(f'{swap.pct_used:.1f}%')}) used",
        ]
        yield f"  {', '.join(swap_parts)}"

        # IO line
        io_parts = [
            f"  IO: {bold_green(str(system_info.max_iops) + '/s')} max iops",
            f"{bold_green(utils.naturalsize(system_info.io_read.bytes) + '/s')} read",
            f"{bold_green(utils.naturalsize(system_info.io_write.bytes) + '/s')} write",
        ]
        yield f"  {', '.join(io_parts)}"

        # Load line
        yield f"  Load average: {bold_green(f'{load.avg1:.2f}')} {bold_green(f'{load.avg5:.2f}')} {bold_green(f'{load.avg15:.2f}')}"


@limit
def render_query_mode(term: Terminal, query_mode: QueryMode, in_pause: bool = False) -> Iterator[str]:
    """Render query mode title.

    >>> term = Terminal()
    >>> list(render_query_mode.__wrapped__(term, QueryMode.activities, False))
    ['...']
    """
    if in_pause:
        yield term.black_on_yellow(term.center("PAUSE", fillchar=" "))
    else:
        title = query_mode.value.upper()
        yield term.green_bold(term.center(title, fillchar=" ").rstrip())


@limit
def render_columns_header(
    term: Terminal,
    columns: list[Column],
    sort_key: SortKey,
) -> Iterator[str]:
    """Render column headers.

    >>> term = Terminal()
    >>> cols = [Column("pid", "PID", min_width=6), Column("user", "USER", min_width=10)]
    >>> list(render_columns_header.__wrapped__(term, cols, SortKey.duration))
    ['...']
    """
    headers = []
    for col in columns:
        color = getattr(term, f"black_on_{col.title_color(sort_key)}")
        headers.append(f"{color}{col.title_render()}")
    yield term.ljust(" ".join(headers), fillchar=" ") + term.normal


@limit
def render_processes(
    term: Terminal,
    columns: list[Column],
    processes: SelectableProcesses,
    wrap_query: bool = False,
    width: int | None = None,
) -> Iterator[str]:
    """Render process rows."""
    if width is None:
        width = term.width or 80

    focused = processes.focused
    pinned = processes.pinned

    for process in processes:
        cursor: Literal["focused", "pinned"] | None = None
        if process.pid == focused:
            cursor = "focused"
        elif process.pid in pinned:
            cursor = "pinned"

        cells: list[str] = []
        query_col = None

        for col in columns:
            if col.key == "query":
                query_col = col
                continue

            value = getattr(process, col.key, None)

            # Determine color
            if cursor == "pinned":
                color_name = PINNED_COLOR
            elif cursor == "focused":
                color_name = FOCUSED_COLOR
            else:
                color_name = col.color(value) or "normal"

            color = getattr(term, color_name)
            cells.append(f"{color}{col.render(value)}{term.normal}")

        # Get indent for query (sum of all column widths)
        indent = sum(c.min_width + 1 for c in columns if c.key != "query")
        query_width = width - indent - 1

        # Render query
        if query_col and query_width > 0:
            query_text = getattr(process, "query", "") or ""
            is_parallel = getattr(process, "is_parallel_worker", False)
            if is_parallel:
                query_text = r"\_ " + query_text
            query_text = utils.clean_str(query_text)

            if cursor == "pinned":
                color_name = PINNED_COLOR
            elif cursor == "focused":
                color_name = FOCUSED_COLOR
            else:
                color_name = "normal"

            color = getattr(term, color_name)

            if not wrap_query:
                query_text = query_text[:query_width]
                cells.append(f"{color}{query_text}{term.normal}")
                yield " ".join(cells)
            else:
                wrapped = TextWrapper(query_width).wrap(query_text) or [""]
                cells.append(f"{color}{wrapped[0]}{term.normal}")
                yield " ".join(cells)
                # Additional wrapped lines
                indent_str = " " * indent
                for line in wrapped[1:]:
                    yield f"{indent_str}{color}{line}{term.normal}"
        else:
            yield " ".join(cells)


def render_footer_help(term: Terminal, width: int | None = None) -> None:
    """Render footer with help keys."""
    if width is None:
        width = term.width or 80

    # Build footer items
    footer_items = []

    # Query mode keys
    for qm, keys in KEYS_BY_QUERYMODE.items():
        key_str = "/".join(keys[:-1])  # Exclude the curses code
        footer_items.append((key_str, qm.value[:10]))  # Truncate description

    # Standard keys
    footer_items.extend([
        (PAUSE_KEY.name or PAUSE_KEY.value, PAUSE_KEY.description),
        (EXIT_KEY.value, EXIT_KEY.description),
        (HELP, "help"),
    ])

    ncols = len(footer_items)
    if ncols == 0:
        return

    col_width = (width - ncols - 1) // ncols

    def render_col(key: str, desc: str) -> str:
        desc_width = col_width - len(key) - 1
        if desc_width <= 0:
            return ""
        desc = desc[:desc_width].ljust(desc_width)
        return f"{key} {term.cyan_reverse(desc)}"

    row = " ".join(render_col(k, d.capitalize()) for k, d in footer_items)
    print(term.ljust(row, width=width, fillchar=term.cyan_reverse(" ")), end="")


def render_footer_interactive(term: Terminal, width: int | None = None) -> None:
    """Render footer for interactive mode (process selected)."""
    if width is None:
        width = term.width or 80

    footer_items = [
        ("C", "cancel query"),
        ("K", "terminate"),
        ("Space", "tag/untag"),
        ("Other", "back"),
        ("q", "quit"),
    ]

    ncols = len(footer_items)
    col_width = (width - ncols - 1) // ncols

    def render_col(key: str, desc: str) -> str:
        desc_width = col_width - len(key) - 1
        if desc_width <= 0:
            return ""
        desc = desc[:desc_width].ljust(desc_width)
        return f"{key} {term.cyan_reverse(desc)}"

    row = " ".join(render_col(k, d) for k, d in footer_items)
    print(term.ljust(row, width=width, fillchar=term.cyan_reverse(" ")), end="")


def render_footer_message(term: Terminal, message: str, width: int | None = None) -> None:
    """Render footer with a message."""
    if width is None:
        width = term.width or 80
    print(term.center(message[:width]) + term.normal, end="")


@limit
def render_help(term: Terminal, version: str, is_local: bool = True) -> Iterator[str]:
    """Render help screen.

    >>> term = Terminal()
    >>> lines = list(render_help.__wrapped__(term, "1.0.0", True))
    >>> len(lines) > 0
    True
    """
    yield f"{term.bold_green}pg_monitor {version}"
    yield f"{term.normal}Released under PostgreSQL License."
    yield ""

    def key_line(key: Key) -> str:
        key_name = key.name or key.value
        return f"{term.bright_cyan}{key_name.rjust(10)}{term.normal}: {key.description}"

    # Filter bindings based on local mode
    bindings = BINDINGS
    if not is_local:
        bindings = [b for b in bindings if not b.local_only]

    for binding in bindings:
        yield key_line(binding)

    yield ""
    yield "Mode"
    for mode_key in MODES:
        yield key_line(mode_key)

    yield ""
    yield "Press any key to exit."


def screen(
    term: Terminal,
    *,
    pg_version: str,
    host: str,
    refresh_time: float,
    duration_mode: DurationMode,
    query_mode: QueryMode,
    sort_key: SortKey,
    processes: SelectableProcesses,
    system_info: SystemInfo | None = None,
    message: str | None = None,
    in_pause: bool = False,
    interactive: bool = False,
    wrap_query: bool = False,
    is_local: bool = True,
    show_header: bool = True,
    show_footer: bool = True,
    width: int | None = None,
) -> None:
    """Render the complete screen."""
    if width is None:
        width = term.width or 80

    print(term.home, end="")
    top_height = term.height - (1 if show_footer else 0)
    counter = LineCounter(top_height)

    if show_header:
        render_header(
            term,
            pg_version=pg_version,
            host=host,
            refresh_time=refresh_time,
            duration_mode=duration_mode,
            system_info=system_info,
            lines_counter=counter,
            width=width,
        )

    render_query_mode(term, query_mode, in_pause, lines_counter=counter, width=width)

    columns = get_default_columns(query_mode, is_local)
    render_columns_header(term, columns, sort_key, lines_counter=counter, width=width)

    render_processes(
        term,
        columns,
        processes,
        wrap_query=wrap_query,
        width=width,
        lines_counter=counter,
    )

    # Clear remaining lines
    print(f"{term.clear_eol}\n" * counter.value, end="")

    if show_footer:
        with term.location(x=0, y=top_height):
            if message is not None:
                render_footer_message(term, message, width)
            elif interactive:
                render_footer_interactive(term, width)
            else:
                render_footer_help(term, width)
