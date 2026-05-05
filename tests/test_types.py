"""Tests for core data models."""

import pytest
from dataclasses import dataclass
from ipaddress import ip_address

from pgmonitor.types import (
    QueryMode,
    SortKey,
    DurationMode,
    LockType,
    Filters,
    NO_FILTER,
    MemoryInfo,
    SwapInfo,
    LoadAverage,
    IOCounter,
    SystemInfo,
    RunningProcess,
    WaitingProcess,
    BlockingProcess,
    LocalRunningProcess,
    SelectableProcesses,
    BaseProcess,
    Percentage,
    enum_next,
    parse_lock_type,
)


class TestEnums:
    """Tests for enum types."""

    def test_query_mode_values(self):
        """QueryMode has three modes with readable values."""
        assert QueryMode.activities.value == "running queries"
        assert QueryMode.waiting.value == "waiting queries"
        assert QueryMode.blocking.value == "blocking queries"

    def test_query_mode_default(self):
        """QueryMode.default() returns activities."""
        assert QueryMode.default() == QueryMode.activities

    def test_sort_key_values(self):
        """SortKey has all expected values."""
        assert hasattr(SortKey, 'cpu')
        assert hasattr(SortKey, 'mem')
        assert hasattr(SortKey, 'read')
        assert hasattr(SortKey, 'write')
        assert hasattr(SortKey, 'duration')

    def test_sort_key_default(self):
        """SortKey.default() returns duration."""
        assert SortKey.default() == SortKey.duration

    def test_duration_mode_values(self):
        """DurationMode has integer values 1, 2, 3."""
        assert DurationMode.query == 1
        assert DurationMode.transaction == 2
        assert DurationMode.backend == 3

    def test_lock_type_str(self):
        """LockType __str__ returns the name."""
        assert str(LockType.relation) == "relation"
        assert str(LockType.transactionid) == "transactionid"


class TestEnumNext:
    """Tests for enum_next helper."""

    def test_enum_next_cycles(self):
        """enum_next cycles through enum values."""
        mode = DurationMode.query
        mode = enum_next(mode)
        assert mode == DurationMode.transaction
        mode = enum_next(mode)
        assert mode == DurationMode.backend
        mode = enum_next(mode)
        assert mode == DurationMode.query  # wraps around


class TestParseLockType:
    """Tests for parse_lock_type function."""

    def test_valid_lock_type(self):
        """parse_lock_type parses valid types."""
        assert parse_lock_type("relation") == LockType.relation
        assert parse_lock_type("tuple") == LockType.tuple

    def test_invalid_lock_type(self):
        """parse_lock_type raises on invalid type."""
        with pytest.raises(ValueError, match="invalid lock type"):
            parse_lock_type("invalid")


class TestFilters:
    """Tests for Filters class."""

    def test_empty_filters(self):
        """Empty filters list returns default Filters."""
        f = Filters.from_options([])
        assert f.dbname is None

    def test_dbname_filter(self):
        """dbname filter is parsed correctly."""
        f = Filters.from_options(["dbname:mydb"])
        assert f.dbname == "mydb"

    def test_malformatted_filter(self):
        """Malformatted filter raises ValueError."""
        with pytest.raises(ValueError, match="malformatted"):
            Filters.from_options(["invalid"])

    def test_empty_regex_filter(self):
        """Empty regex raises ValueError."""
        with pytest.raises(ValueError, match="empty regex"):
            Filters.from_options(["dbname:"])

    def test_unknown_filter(self):
        """Unknown filter field raises ValueError."""
        with pytest.raises(ValueError, match="unknown filter"):
            Filters.from_options(["unknown:test"])

    def test_duplicate_filter(self):
        """Duplicate filter raises ValueError."""
        with pytest.raises(ValueError, match="multiple filters"):
            Filters.from_options(["dbname:a", "dbname:b"])

    def test_no_filter_constant(self):
        """NO_FILTER is a Filters with no filters set."""
        assert NO_FILTER.dbname is None


class TestMemoryInfo:
    """Tests for MemoryInfo class."""

    def test_default(self):
        """default() returns all zeros."""
        m = MemoryInfo.default()
        assert m.used == 0
        assert m.buff_cached == 0
        assert m.free == 0
        assert m.total == 0

    def test_percentages(self):
        """Percentages are computed correctly."""
        m = MemoryInfo(used=50, buff_cached=25, free=25, total=100)
        assert m.pct_used == 50.0
        assert m.pct_free == 25.0
        assert m.pct_bc == 25.0

    def test_percentages_zero_total(self):
        """Percentages return None when total is zero."""
        m = MemoryInfo.default()
        assert m.pct_used is None
        assert m.pct_free is None
        assert m.pct_bc is None

    def test_percentage_type(self):
        """Percentage values are Percentage instances."""
        m = MemoryInfo(used=50, buff_cached=25, free=25, total=100)
        assert isinstance(m.pct_used, Percentage)


class TestSwapInfo:
    """Tests for SwapInfo class."""

    def test_default(self):
        """default() returns all zeros."""
        s = SwapInfo.default()
        assert s.used == 0
        assert s.free == 0
        assert s.total == 0

    def test_percentages(self):
        """Percentages are computed correctly."""
        s = SwapInfo(used=25, free=75, total=100)
        assert s.pct_used == 25.0
        assert s.pct_free == 75.0

    def test_percentages_zero_total(self):
        """Percentages return None when total is zero."""
        s = SwapInfo.default()
        assert s.pct_used is None
        assert s.pct_free is None


class TestLoadAverage:
    """Tests for LoadAverage class."""

    def test_default(self):
        """default() returns all zeros."""
        l = LoadAverage.default()
        assert l.avg1 == 0.0
        assert l.avg5 == 0.0
        assert l.avg15 == 0.0

    def test_values(self):
        """Values are stored correctly."""
        l = LoadAverage(avg1=0.5, avg5=1.0, avg15=1.5)
        assert l.avg1 == 0.5
        assert l.avg5 == 1.0
        assert l.avg15 == 1.5


class TestIOCounter:
    """Tests for IOCounter class."""

    def test_default(self):
        """default() returns all zeros."""
        io = IOCounter.default()
        assert io.count == 0
        assert io.bytes == 0

    def test_values(self):
        """Values are stored correctly."""
        io = IOCounter(count=100, bytes=4096)
        assert io.count == 100
        assert io.bytes == 4096


class TestSystemInfo:
    """Tests for SystemInfo class."""

    def test_default(self):
        """default() returns a SystemInfo with default components."""
        s = SystemInfo.default()
        assert s.memory == MemoryInfo.default()
        assert s.swap == SwapInfo.default()
        assert s.load == LoadAverage.default()
        assert s.io_read == IOCounter.default()
        assert s.io_write == IOCounter.default()
        assert s.max_iops == 0

    def test_with_custom_values(self):
        """default() accepts custom component values."""
        memory = MemoryInfo(100, 50, 50, 200)
        swap = SwapInfo(10, 90, 100)
        s = SystemInfo.default(memory=memory, swap=swap)
        assert s.memory == memory
        assert s.swap == swap
        assert s.load == LoadAverage.default()


class TestRunningProcess:
    """Tests for RunningProcess class."""

    def test_creation(self):
        """RunningProcess can be created with all fields."""
        p = RunningProcess(
            pid=1234,
            application_name="pgbench",
            database="test",
            user="postgres",
            client=ip_address("127.0.0.1"),
            duration=1.5,
            state="active",
            query="SELECT 1",
            wait=False,
            xmin=12345,
        )
        assert p.pid == 1234
        assert p.database == "test"
        assert p.duration == 1.5

    def test_default_values(self):
        """RunningProcess has sensible defaults."""
        p = RunningProcess(
            pid=1, application_name="", database=None, user="pg",
            client=None, duration=None, state="idle", query=None,
        )
        assert p.wait is None
        assert p.xmin == 0
        assert p.is_parallel_worker is False


class TestWaitingProcess:
    """Tests for WaitingProcess class."""

    def test_creation(self):
        """WaitingProcess can be created with lock info."""
        p = WaitingProcess(
            pid=1234,
            application_name="app",
            database="test",
            user="postgres",
            client=None,
            duration=1.0,
            state="active",
            query="UPDATE t SET x=1",
            mode="ExclusiveLock",
            type=LockType.relation,
            relation="public.t",
        )
        assert p.mode == "ExclusiveLock"
        assert p.type == LockType.relation
        assert p.relation == "public.t"


class TestBlockingProcess:
    """Tests for BlockingProcess class."""

    def test_creation(self):
        """BlockingProcess can be created with lock and wait info."""
        p = BlockingProcess(
            pid=1234,
            application_name="app",
            database="test",
            user="postgres",
            client=None,
            duration=1.0,
            state="active",
            query="UPDATE t SET x=1",
            mode="ExclusiveLock",
            type=LockType.relation,
            relation="public.t",
            wait="ClientRead",
        )
        assert p.wait == "ClientRead"


class TestLocalRunningProcess:
    """Tests for LocalRunningProcess class."""

    def test_from_process(self):
        """from_process creates LocalRunningProcess from RunningProcess."""
        rp = RunningProcess(
            pid=1234,
            application_name="app",
            database="test",
            user="postgres",
            client=None,
            duration=1.0,
            state="active",
            query="SELECT 1",
            wait=False,
            xmin=100,
        )
        lp = LocalRunningProcess.from_process(
            rp, cpu=5.0, mem=2.5, read=1024.0, write=512.0, io_wait=False
        )
        assert lp.pid == 1234
        assert lp.cpu == 5.0
        assert lp.mem == 2.5
        assert lp.read == 1024.0
        assert lp.write == 512.0
        assert lp.io_wait is False
        assert lp.wait is False
        assert lp.xmin == 100


class TestSelectableProcesses:
    """Tests for SelectableProcesses class."""

    @dataclass
    class MockProc:
        pid: int

    @pytest.fixture
    def procs(self):
        """Create a SelectableProcesses with mock processes."""
        return SelectableProcesses([
            self.MockProc(100),
            self.MockProc(200),
            self.MockProc(300),
        ])

    def test_len(self, procs):
        """len() returns number of items."""
        assert len(procs) == 3

    def test_iter(self, procs):
        """Iteration yields all items."""
        pids = [p.pid for p in procs]
        assert pids == [100, 200, 300]

    def test_getitem(self, procs):
        """Indexing returns correct items."""
        assert procs[0].pid == 100
        assert procs[-1].pid == 300
        assert [p.pid for p in procs[1:]] == [200, 300]

    def test_initial_state(self, procs):
        """Initial state has no focus or selection."""
        assert procs.focused is None
        assert procs.selected == []

    def test_focus_next(self, procs):
        """focus_next moves focus forward."""
        assert procs.focus_next()
        assert procs.focused == 100
        assert procs.focus_next()
        assert procs.focused == 200

    def test_focus_next_wraps(self, procs):
        """focus_next wraps at the end."""
        procs.focus_last()
        assert procs.focused == 300
        procs.focus_next()
        assert procs.focused == 100  # wrapped

    def test_focus_prev(self, procs):
        """focus_prev moves focus backward."""
        procs.focus_last()
        assert procs.focus_prev()
        assert procs.focused == 200

    def test_focus_prev_wraps(self, procs):
        """focus_prev wraps at the beginning."""
        procs.focus_first()
        procs.focus_prev()
        assert procs.focused == 300  # wrapped

    def test_focus_first(self, procs):
        """focus_first focuses the first item."""
        procs.focus_last()
        procs.focus_first()
        assert procs.focused == 100

    def test_focus_last(self, procs):
        """focus_last focuses the last item."""
        procs.focus_first()
        procs.focus_last()
        assert procs.focused == 300

    def test_selected_with_focus(self, procs):
        """selected returns focused PID when not pinned."""
        procs.focus_next()
        assert procs.selected == [100]

    def test_toggle_pin(self, procs):
        """toggle_pin_focused toggles pin status."""
        procs.focus_next()
        procs.toggle_pin_focused()
        assert 100 in procs.pinned
        procs.toggle_pin_focused()
        assert 100 not in procs.pinned

    def test_selected_with_pinned(self, procs):
        """selected returns pinned PIDs when pinned."""
        procs.focus_next()
        procs.toggle_pin_focused()
        procs.focus_next()
        procs.toggle_pin_focused()
        assert set(procs.selected) == {100, 200}

    def test_reset(self, procs):
        """reset clears focus and pinned."""
        procs.focus_next()
        procs.toggle_pin_focused()
        procs.reset()
        assert procs.focused is None
        assert len(procs.pinned) == 0
        assert procs.selected == []

    def test_set_items(self, procs):
        """set_items replaces the items list."""
        new_items = [self.MockProc(999)]
        procs.set_items(new_items)
        assert len(procs) == 1
        assert procs[0].pid == 999

    def test_position(self, procs):
        """position returns index of focused item."""
        assert procs.position() is None
        procs.focus_next()
        assert procs.position() == 0
        procs.focus_next()
        assert procs.position() == 1

    def test_empty_list_focus(self):
        """Focus operations return False on empty list."""
        procs = SelectableProcesses([])
        assert procs.focus_next() is False
        assert procs.focus_prev() is False
        assert procs.focus_first() is False
        assert procs.focus_last() is False
