"""Core data models for PostgreSQL activity monitoring."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Iterator, MutableSet, Sequence, TypeVar, Union


class Percentage(float):
    """Float subclass to distinguish percentage values."""
    pass


E = TypeVar("E", bound=enum.IntEnum)


def enum_next(e: E) -> E:
    """Return the next value in an enum, wrapping to the first value at the end.

    >>> class Seasons(enum.IntEnum):
    ...     winter = 1
    ...     spring = 2
    ...     summer = 3
    ...     autumn = 4
    >>> enum_next(Seasons.winter).name
    'spring'
    >>> enum_next(Seasons.autumn).name
    'winter'
    """
    members = list(e.__class__)
    max_val = max(m.value for m in members)
    next_val = (e.value % max_val) + 1
    return e.__class__(next_val)


@enum.unique
class QueryMode(enum.Enum):
    """Mode for displaying queries."""
    activities = "running queries"
    waiting = "waiting queries"
    blocking = "blocking queries"

    @classmethod
    def default(cls) -> QueryMode:
        return cls.activities


class SortKey(enum.Enum):
    """Keys for sorting processes."""
    cpu = enum.auto()
    mem = enum.auto()
    read = enum.auto()
    write = enum.auto()
    duration = enum.auto()

    @classmethod
    def default(cls) -> SortKey:
        return cls.duration


@enum.unique
class DurationMode(enum.IntEnum):
    """Mode for computing query duration."""
    query = 1
    transaction = 2
    backend = 3


class LockType(enum.Enum):
    """Type of lockable object in PostgreSQL."""
    relation = enum.auto()
    extend = enum.auto()
    page = enum.auto()
    tuple = enum.auto()
    transactionid = enum.auto()
    virtualxid = enum.auto()
    object = enum.auto()
    userlock = enum.auto()
    advisory = enum.auto()

    def __str__(self) -> str:
        return self.name


def parse_lock_type(value: str) -> LockType:
    """Parse a lock type string to enum value.

    >>> parse_lock_type("relation")
    <LockType.relation: 1>
    >>> parse_lock_type("invalid")
    Traceback (most recent call last):
        ...
    ValueError: invalid lock type 'invalid'
    """
    try:
        return LockType[value]
    except KeyError:
        raise ValueError(f"invalid lock type '{value}'")


@dataclass(frozen=True)
class Filters:
    """Activity filters."""
    dbname: str | None = None

    @classmethod
    def from_options(cls, filters: Sequence[str]) -> Filters:
        """Parse filter options in 'field:regex' format.

        >>> Filters.from_options(["dbname:test"])
        Filters(dbname='test')
        >>> Filters.from_options([])
        Filters(dbname=None)
        >>> Filters.from_options(["invalid"])
        Traceback (most recent call last):
            ...
        ValueError: malformatted filter value 'invalid'
        >>> Filters.from_options(["dbname:"])
        Traceback (most recent call last):
            ...
        ValueError: empty regex in filter 'dbname:'
        >>> Filters.from_options(["unknown:test"])
        Traceback (most recent call last):
            ...
        ValueError: unknown filter 'unknown'
        >>> Filters.from_options(["dbname:a", "dbname:b"])
        Traceback (most recent call last):
            ...
        ValueError: got multiple filters 'dbname'
        """
        known_fields = {'dbname'}
        attrs: dict[str, str] = {}
        for f in filters:
            try:
                fname, regex = f.split(":", 1)
            except ValueError:
                raise ValueError(f"malformatted filter value '{f}'")
            if not regex:
                raise ValueError(f"empty regex in filter '{f}'")
            if fname in attrs:
                raise ValueError(f"got multiple filters '{fname}'")
            if fname not in known_fields:
                raise ValueError(f"unknown filter '{fname}'")
            attrs[fname] = regex
        return cls(**attrs)


NO_FILTER = Filters()


@dataclass(frozen=True)
class MemoryInfo:
    """Memory usage information."""
    used: int
    buff_cached: int
    free: int
    total: int

    @classmethod
    def default(cls) -> MemoryInfo:
        return cls(0, 0, 0, 0)

    @property
    def pct_used(self) -> Percentage | None:
        if self.total == 0:
            return None
        return Percentage(self.used * 100 / self.total)

    @property
    def pct_free(self) -> Percentage | None:
        if self.total == 0:
            return None
        return Percentage(self.free * 100 / self.total)

    @property
    def pct_bc(self) -> Percentage | None:
        if self.total == 0:
            return None
        return Percentage(self.buff_cached * 100 / self.total)


@dataclass(frozen=True)
class SwapInfo:
    """Swap usage information."""
    used: int
    free: int
    total: int

    @classmethod
    def default(cls) -> SwapInfo:
        return cls(0, 0, 0)

    @property
    def pct_used(self) -> Percentage | None:
        if self.total == 0:
            return None
        return Percentage(self.used * 100 / self.total)

    @property
    def pct_free(self) -> Percentage | None:
        if self.total == 0:
            return None
        return Percentage(self.free * 100 / self.total)


@dataclass
class LoadAverage:
    """System load average."""
    avg1: float
    avg5: float
    avg15: float

    @classmethod
    def default(cls) -> LoadAverage:
        return cls(0.0, 0.0, 0.0)


@dataclass(frozen=True)
class IOCounter:
    """I/O counter for read/write operations."""
    count: int
    bytes: int

    @classmethod
    def default(cls) -> IOCounter:
        return cls(0, 0)


@dataclass(frozen=True)
class SystemInfo:
    """System-level information."""
    memory: MemoryInfo
    swap: SwapInfo
    load: LoadAverage
    io_read: IOCounter
    io_write: IOCounter
    max_iops: int = 0

    @classmethod
    def default(
        cls,
        *,
        memory: MemoryInfo | None = None,
        swap: SwapInfo | None = None,
        load: LoadAverage | None = None,
    ) -> SystemInfo:
        """Create a default SystemInfo with zero values."""
        return cls(
            memory or MemoryInfo.default(),
            swap or SwapInfo.default(),
            load or LoadAverage.default(),
            IOCounter.default(),
            IOCounter.default(),
            0,
        )


@dataclass
class BaseProcess:
    """Base class for process information."""
    pid: int
    application_name: str
    database: str | None
    user: str
    client: None | IPv4Address | IPv6Address
    duration: float | None
    state: str
    query: str | None
    is_parallel_worker: bool = False
    query_leader_pid: int | None = None


@dataclass
class RunningProcess(BaseProcess):
    """Process for a running query."""
    wait: bool | None | str = None
    xmin: int = 0


@dataclass
class WaitingProcess(BaseProcess):
    """Process for a waiting query with lock information."""
    mode: str = ""
    type: LockType = LockType.relation
    relation: str = ""


@dataclass
class BlockingProcess(BaseProcess):
    """Process for a blocking query with lock information."""
    mode: str = ""
    type: LockType = LockType.relation
    relation: str = ""
    wait: bool | None | str = None


@dataclass
class SystemProcess:
    """System process information from psutil."""
    meminfo: tuple[int, ...]
    io_read: IOCounter
    io_write: IOCounter
    io_time: float
    mem_percent: float
    cpu_percent: float
    cpu_times: tuple[float, ...]
    read_delta: float
    write_delta: float
    io_wait: bool
    psutil_proc: Any = None  # psutil.Process


@dataclass
class LocalRunningProcess(RunningProcess):
    """Running process with local system metrics."""
    cpu: float = 0.0
    mem: float = 0.0
    read: float = 0.0
    write: float = 0.0
    io_wait: bool = False

    @classmethod
    def from_process(
        cls, process: RunningProcess, **kwargs: float | bool
    ) -> LocalRunningProcess:
        """Create a LocalRunningProcess from a RunningProcess."""
        return cls(
            pid=process.pid,
            application_name=process.application_name,
            database=process.database,
            user=process.user,
            client=process.client,
            duration=process.duration,
            state=process.state,
            query=process.query,
            is_parallel_worker=process.is_parallel_worker,
            query_leader_pid=process.query_leader_pid,
            wait=process.wait,
            xmin=process.xmin,
            **kwargs,
        )


@dataclass
class SelectableProcesses:
    """A list of processes that supports selection and navigation.

    >>> @dataclass
    ... class Proc:
    ...     pid: int
    >>> procs = SelectableProcesses([Proc(456), Proc(123), Proc(789)])
    >>> len(procs)
    3
    >>> procs.focused
    >>> procs.focus_next()
    True
    >>> procs.focused
    456
    >>> procs.focus_next()
    True
    >>> procs.focused
    123
    >>> procs.focus_prev()
    True
    >>> procs.focused
    456
    >>> procs.focus_first()
    True
    >>> procs.focused
    456
    >>> procs.focus_last()
    True
    >>> procs.focused
    789
    >>> procs.selected
    [789]
    >>> procs.toggle_pin_focused()
    >>> procs.selected
    [789]
    >>> procs.toggle_pin_focused()
    >>> procs.selected
    [789]
    >>> procs.reset()
    >>> procs.focused
    >>> procs.selected
    []
    """
    items: list[BaseProcess]
    focused: int | None = None
    pinned: MutableSet[int] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[BaseProcess]:
        return iter(self.items)

    def __getitem__(self, val: int | slice) -> BaseProcess | list[BaseProcess]:
        return self.items[val]

    @property
    def selected(self) -> list[int]:
        """Return list of selected PIDs (pinned or focused)."""
        if self.pinned:
            return list(self.pinned)
        elif self.focused:
            return [self.focused]
        else:
            return []

    def reset(self) -> None:
        """Reset focus and pinned selections."""
        self.focused = None
        self.pinned.clear()

    def set_items(self, new_items: Sequence[BaseProcess]) -> None:
        """Replace items list."""
        self.items[:] = list(new_items)

    def position(self) -> int | None:
        """Return the index of the focused process."""
        if self.focused is None:
            return None
        for idx, proc in enumerate(self.items):
            if proc.pid == self.focused:
                return idx
        return None

    def focus_next(self, offset: int = 1) -> bool:
        """Move focus to the next process."""
        if not self.items:
            return False
        idx = self.position()
        bottom = len(self.items) - 1
        if idx is None or (offset == 1 and idx == bottom):
            next_idx = 0
        else:
            next_idx = min(bottom, idx + offset)
        self.focused = self.items[next_idx].pid
        return True

    def focus_prev(self, offset: int = 1) -> bool:
        """Move focus to the previous process."""
        if not self.items:
            return False
        idx = self.position() or 0
        if offset == 1:
            next_idx = idx - offset
        else:
            next_idx = max(idx - offset, 0)
        self.focused = self.items[next_idx].pid
        return True

    def focus_first(self) -> bool:
        """Move focus to the first process."""
        if not self.items:
            return False
        self.focused = self.items[0].pid
        return True

    def focus_last(self) -> bool:
        """Move focus to the last process."""
        if not self.items:
            return False
        self.focused = self.items[-1].pid
        return True

    def toggle_pin_focused(self) -> None:
        """Toggle pin status of the focused process."""
        if self.focused is None:
            return
        if self.focused in self.pinned:
            self.pinned.remove(self.focused)
        else:
            self.pinned.add(self.focused)


# Type alias for activity statistics
ActivityStats = Union[
    list[WaitingProcess],
    list[RunningProcess],
    tuple[list[WaitingProcess], SystemInfo],
    tuple[list[BlockingProcess], SystemInfo],
    tuple[list[LocalRunningProcess], SystemInfo],
]
