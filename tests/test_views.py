"""Tests for terminal rendering views module."""

import pytest
from unittest.mock import MagicMock, patch

from pgmonitor.views import (
    Column,
    LineCounter,
    boxed,
    color_for_state,
    color_for_wait,
    color_for_lock_mode,
    get_default_columns,
    render_help,
    PINNED_COLOR,
    FOCUSED_COLOR,
)
from pgmonitor.types import (
    DurationMode,
    IOCounter,
    LoadAverage,
    MemoryInfo,
    QueryMode,
    RunningProcess,
    SelectableProcesses,
    SortKey,
    SwapInfo,
    SystemInfo,
)


class TestColorFunctions:
    """Tests for color helper functions."""

    def test_color_for_state_active(self):
        """Active state is green."""
        assert color_for_state("active") == "green"

    def test_color_for_state_idle_in_trans(self):
        """Idle in transaction is yellow."""
        assert color_for_state("idle in transaction") == "yellow"

    def test_color_for_state_idle_in_trans_aborted(self):
        """Idle in transaction aborted is red."""
        assert color_for_state("idle in transaction (aborted)") == "red"

    def test_color_for_state_idle(self):
        """Idle state has no color."""
        assert color_for_state("idle") is None

    def test_color_for_wait_true(self):
        """Waiting is red."""
        assert color_for_wait(True) == "red"

    def test_color_for_wait_false(self):
        """Not waiting is green."""
        assert color_for_wait(False) == "green"

    def test_color_for_lock_mode_exclusive(self):
        """Exclusive locks are red."""
        assert color_for_lock_mode("ExclusiveLock") == "bold_red"
        assert color_for_lock_mode("RowExclusiveLock") == "bold_red"
        assert color_for_lock_mode("AccessExclusiveLock") == "bold_red"

    def test_color_for_lock_mode_share(self):
        """Share locks are yellow."""
        assert color_for_lock_mode("ShareLock") == "bold_yellow"


class TestColumn:
    """Tests for Column class."""

    def test_basic_column(self):
        """Column with default settings."""
        col = Column("pid", "PID", min_width=6)
        assert col.key == "pid"
        assert col.name == "PID"
        assert col.min_width == 6

    def test_title_render_left(self):
        """Title renders with left justification."""
        col = Column("pid", "PID", min_width=8)
        assert col.title_render() == "PID     "

    def test_title_render_right(self):
        """Title renders with right justification."""
        col = Column("cpu", "CPU%", min_width=6, justify="right")
        assert col.title_render() == "  CPU%"

    def test_title_render_center(self):
        """Title renders with center justification."""
        col = Column("test", "TEST", min_width=8, justify="center")
        assert col.title_render() == "  TEST  "

    def test_render_value(self):
        """Column renders values."""
        col = Column("pid", "PID", min_width=6)
        assert col.render(1234) == "1234  "

    def test_render_with_transform(self):
        """Column applies transform function."""
        col = Column("cpu", "CPU%", min_width=6, transform=lambda v: f"{v:.1f}")
        assert col.render(12.34) == "12.3  "

    def test_render_truncates(self):
        """Column truncates long values."""
        col = Column("pid", "PID", min_width=4, max_width=4)
        assert col.render(123456) == "1234"

    def test_title_color_sorted(self):
        """Column shows cyan when it's the sort column."""
        col = Column("cpu", "CPU%", sort_key=SortKey.cpu)
        assert col.title_color(SortKey.cpu) == "cyan"

    def test_title_color_not_sorted(self):
        """Column shows green when not the sort column."""
        col = Column("cpu", "CPU%", sort_key=SortKey.cpu)
        assert col.title_color(SortKey.duration) == "green"

    def test_color_func(self):
        """Column uses color function for values."""
        col = Column("state", "STATE", color_func=lambda v: "green" if v == "active" else None)
        assert col.color("active") == "green"
        assert col.color("idle") is None


class TestLineCounter:
    """Tests for LineCounter class."""

    def test_initial_value(self):
        """LineCounter starts with initial value."""
        counter = LineCounter(10)
        assert counter.value == 10

    def test_next_decrements(self):
        """next() returns current and decrements."""
        counter = LineCounter(5)
        assert next(counter) == 5
        assert counter.value == 4
        assert next(counter) == 4
        assert counter.value == 3

    def test_repr(self):
        """LineCounter has repr."""
        counter = LineCounter(3)
        assert repr(counter) == "LineCounter(3)"


class TestBoxed:
    """Tests for boxed widget."""

    def test_boxed_basic(self):
        """boxed creates bordered box."""
        term = MagicMock()
        term.white = lambda x: x
        term.normal = ""

        result = boxed(term, "Hello")
        assert "Hello" in result
        assert "+" in result
        assert "-" in result
        assert "|" in result

    def test_boxed_centered(self):
        """boxed can center content."""
        term = MagicMock()
        term.white = lambda x: x
        term.normal = ""
        term.center = lambda x, width: x.center(width)

        result = boxed(term, "Test", center=True, width=40)
        assert "Test" in result


class TestGetDefaultColumns:
    """Tests for get_default_columns function."""

    def test_activities_local(self):
        """Activities mode with local has CPU/MEM columns."""
        cols = get_default_columns(QueryMode.activities, is_local=True)
        keys = [c.key for c in cols]
        assert "pid" in keys
        assert "cpu" in keys
        assert "mem" in keys
        assert "query" in keys

    def test_activities_remote(self):
        """Activities mode without local lacks CPU/MEM columns."""
        cols = get_default_columns(QueryMode.activities, is_local=False)
        keys = [c.key for c in cols]
        assert "pid" in keys
        assert "cpu" not in keys
        assert "mem" not in keys
        assert "query" in keys

    def test_waiting_mode(self):
        """Waiting mode has lock columns."""
        cols = get_default_columns(QueryMode.waiting)
        keys = [c.key for c in cols]
        assert "mode" in keys
        assert "type" in keys
        assert "relation" in keys

    def test_blocking_mode(self):
        """Blocking mode has lock columns."""
        cols = get_default_columns(QueryMode.blocking)
        keys = [c.key for c in cols]
        assert "mode" in keys
        assert "type" in keys


class TestRenderHelp:
    """Tests for render_help function."""

    def test_help_has_version(self):
        """Help shows version."""
        term = MagicMock()
        term.bold_green = lambda x: x
        term.normal = ""
        term.bright_cyan = lambda x: x

        lines = list(render_help.__wrapped__(term, "1.0.0", True))
        assert any("1.0.0" in line for line in lines)

    def test_help_shows_keys(self):
        """Help shows key bindings."""
        term = MagicMock()
        term.bold_green = lambda x: x
        term.normal = ""
        term.bright_cyan = lambda x: x

        lines = list(render_help.__wrapped__(term, "1.0.0", True))
        # Should have some key descriptions
        assert len(lines) > 5

    def test_help_filters_local_only(self):
        """Help filters local-only keys when not local."""
        term = MagicMock()
        term.bold_green = lambda x: x
        term.normal = ""
        term.bright_cyan = lambda x: x

        local_lines = list(render_help.__wrapped__(term, "1.0.0", True))
        remote_lines = list(render_help.__wrapped__(term, "1.0.0", False))

        # Remote should have fewer lines (no local-only keys)
        assert len(remote_lines) <= len(local_lines)


class TestRenderHeader:
    """Tests for render_header function."""

    def test_header_basic(self):
        """Header renders basic info."""
        from pgmonitor.views import render_header

        term = MagicMock()
        term.bold = ""
        term.normal = ""
        term.yellow = lambda x: x
        term.bold_green = lambda x: x

        lines = list(render_header.__wrapped__(
            term,
            pg_version="PostgreSQL 15.0",
            host="localhost",
            refresh_time=2.0,
            duration_mode=DurationMode.query,
        ))

        assert len(lines) >= 1
        assert "PostgreSQL 15.0" in lines[0]

    def test_header_with_system_info(self):
        """Header shows system info when provided."""
        from pgmonitor.views import render_header

        term = MagicMock()
        term.bold = ""
        term.normal = ""
        term.yellow = lambda x: x
        term.bold_green = lambda x: x

        system_info = SystemInfo(
            memory=MemoryInfo(1000, 500, 500, 2000),
            swap=SwapInfo(200, 800, 1000),
            load=LoadAverage(0.5, 1.0, 1.5),
            io_read=IOCounter(10, 1024),
            io_write=IOCounter(5, 512),
            max_iops=100,
        )

        lines = list(render_header.__wrapped__(
            term,
            pg_version="PostgreSQL 15.0",
            host="localhost",
            refresh_time=2.0,
            duration_mode=DurationMode.query,
            system_info=system_info,
        ))

        # Should have multiple lines with system info
        assert len(lines) > 1


class TestRenderQueryMode:
    """Tests for render_query_mode function."""

    def test_query_mode_activities(self):
        """Renders activities title."""
        from pgmonitor.views import render_query_mode

        term = MagicMock()
        term.green_bold = lambda x: x
        term.center = lambda x, fillchar: x.center(40, fillchar)

        lines = list(render_query_mode.__wrapped__(term, QueryMode.activities, False))
        assert any("RUNNING QUERIES" in line.upper() for line in lines)

    def test_query_mode_pause(self):
        """Renders PAUSE when paused."""
        from pgmonitor.views import render_query_mode

        term = MagicMock()
        term.black_on_yellow = lambda x: x
        term.center = lambda x, fillchar: x.center(40, fillchar)

        lines = list(render_query_mode.__wrapped__(term, QueryMode.activities, True))
        assert any("PAUSE" in line for line in lines)


class TestRenderColumnsHeader:
    """Tests for render_columns_header function."""

    def test_columns_header(self):
        """Renders column headers."""
        from pgmonitor.views import render_columns_header

        term = MagicMock()
        term.normal = ""
        term.black_on_green = lambda x: x
        term.black_on_cyan = lambda x: x
        term.ljust = lambda x, fillchar: x

        cols = [
            Column("pid", "PID", min_width=6),
            Column("cpu", "CPU%", min_width=6, sort_key=SortKey.cpu),
        ]

        lines = list(render_columns_header.__wrapped__(term, cols, SortKey.duration))
        assert len(lines) == 1
        assert "PID" in lines[0]
        assert "CPU%" in lines[0]


class TestRenderProcesses:
    """Tests for render_processes function."""

    def test_render_empty(self):
        """Renders empty process list."""
        from pgmonitor.views import render_processes

        term = MagicMock()
        term.width = 80
        term.normal = ""

        procs = SelectableProcesses([])
        cols = [Column("pid", "PID", min_width=6)]

        lines = list(render_processes.__wrapped__(term, cols, procs, width=80))
        assert lines == []

    def test_render_process(self):
        """Renders process row."""
        from pgmonitor.views import render_processes

        term = MagicMock()
        term.width = 80
        term.normal = ""
        term.green = lambda x: x

        proc = RunningProcess(
            pid=1234,
            application_name="test",
            database="testdb",
            user="postgres",
            client=None,
            duration=1.5,
            state="active",
            query="SELECT 1",
            wait=False,
        )
        procs = SelectableProcesses([proc])

        cols = [
            Column("pid", "PID", min_width=6),
            Column("database", "DATABASE", min_width=10),
        ]

        lines = list(render_processes.__wrapped__(term, cols, procs, width=80))
        assert len(lines) >= 1
        assert "1234" in lines[0]


class TestColorConstants:
    """Tests for color constants."""

    def test_pinned_color(self):
        """PINNED_COLOR is defined."""
        assert PINNED_COLOR == "bold_yellow"

    def test_focused_color(self):
        """FOCUSED_COLOR is defined."""
        assert FOCUSED_COLOR == "cyan_reverse"
