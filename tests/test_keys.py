"""Tests for keyboard handling and action handlers."""

import curses
from unittest.mock import MagicMock

import pytest

from pgmonitor.keys import (
    Key,
    BINDINGS,
    MODES,
    KEYS_BY_QUERYMODE,
    QUERYMODE_FROM_KEYS,
    EXIT,
    HELP,
    SPACE,
    SORTBY_CPU,
    SORTBY_MEM,
    SORTBY_READ,
    SORTBY_WRITE,
    SORTBY_TIME,
    is_process_next,
    is_process_prev,
    is_process_nextpage,
    is_process_prevpage,
    is_process_first,
    is_process_last,
    is_toggle_header_system,
    is_toggle_header_instance,
    is_toggle_header_workers,
    handle_refresh_time,
    handle_duration_mode,
    handle_wrap_query,
    handle_query_mode,
    handle_sort_key,
)
from pgmonitor.config import ColumnFlag
from pgmonitor.types import DurationMode, QueryMode, SortKey


class TestKey:
    """Tests for Key class."""

    def test_basic_key(self):
        """Key has value and description."""
        key = Key("q", "quit")
        assert key.value == "q"
        assert key.description == "quit"
        assert key.name is None
        assert key.local_only is False

    def test_key_with_name(self):
        """Key can have optional name."""
        key = Key(" ", "pause", "Space")
        assert key.value == " "
        assert key.name == "Space"

    def test_key_local_only(self):
        """Key can be marked as local only."""
        key = Key("c", "sort by CPU", local_only=True)
        assert key.local_only is True

    def test_key_equality_with_string(self):
        """Key equals its value string."""
        key = Key("q", "quit")
        assert key == "q"
        assert key != "x"
        assert key != 123

    def test_key_hashable(self):
        """Key is hashable for use in sets/dicts."""
        key1 = Key("q", "quit")
        key2 = Key("q", "quit")
        # Key has consistent hash
        assert hash(key1) == hash(key2)
        # Key can be used as dict key
        d = {key1: "value"}
        assert d[key1] == "value"


class TestBindings:
    """Tests for key binding lists."""

    def test_bindings_not_empty(self):
        """BINDINGS list is not empty."""
        assert len(BINDINGS) > 0

    def test_bindings_are_keys(self):
        """BINDINGS contains Key instances."""
        for binding in BINDINGS:
            assert isinstance(binding, Key)

    def test_modes_not_empty(self):
        """MODES list is not empty."""
        assert len(MODES) > 0

    def test_keys_by_querymode(self):
        """KEYS_BY_QUERYMODE maps all query modes."""
        assert QueryMode.activities in KEYS_BY_QUERYMODE
        assert QueryMode.waiting in KEYS_BY_QUERYMODE
        assert QueryMode.blocking in KEYS_BY_QUERYMODE


class MockKey:
    """Mock key object for testing."""

    def __init__(self, name: str | None = None, val: str = "", code: int | None = None):
        self.name = name
        self._val = val
        self.code = code
        self.is_sequence = code is not None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self._val == other
        return False


class TestNavigationKeys:
    """Tests for navigation key detection."""

    def test_is_process_next_down_arrow(self):
        """Down arrow is process next."""
        key = MockKey(name="KEY_DOWN")
        assert is_process_next(key) is True

    def test_is_process_next_j(self):
        """j key is process next."""
        key = MockKey(val="j")
        assert is_process_next(key) is True

    def test_is_process_next_other(self):
        """Other keys are not process next."""
        key = MockKey(val="x")
        assert is_process_next(key) is False

    def test_is_process_prev_up_arrow(self):
        """Up arrow is process prev."""
        key = MockKey(name="KEY_UP")
        assert is_process_prev(key) is True

    def test_is_process_prev_k(self):
        """k key is process prev."""
        key = MockKey(val="k")
        assert is_process_prev(key) is True

    def test_is_process_prev_other(self):
        """Other keys are not process prev."""
        key = MockKey(val="x")
        assert is_process_prev(key) is False

    def test_is_process_nextpage(self):
        """Page down is process nextpage."""
        key = MockKey(name="KEY_NPAGE")
        assert is_process_nextpage(key) is True

    def test_is_process_prevpage(self):
        """Page up is process prevpage."""
        key = MockKey(name="KEY_PPAGE")
        assert is_process_prevpage(key) is True

    def test_is_process_first(self):
        """Home is process first."""
        key = MockKey(name="KEY_HOME")
        assert is_process_first(key) is True

    def test_is_process_last(self):
        """End is process last."""
        key = MockKey(name="KEY_END")
        assert is_process_last(key) is True


class TestHeaderToggleKeys:
    """Tests for header toggle key detection."""

    def test_is_toggle_header_system(self):
        """s toggles system header."""
        assert is_toggle_header_system("s") is True
        assert is_toggle_header_system("x") is False

    def test_is_toggle_header_instance(self):
        """i toggles instance header."""
        assert is_toggle_header_instance("i") is True
        assert is_toggle_header_instance("x") is False

    def test_is_toggle_header_workers(self):
        """o toggles workers header."""
        assert is_toggle_header_workers("o") is True
        assert is_toggle_header_workers("x") is False


class TestHandleRefreshTime:
    """Tests for handle_refresh_time function."""

    def test_increase(self):
        """+ increases refresh time."""
        assert handle_refresh_time("+", 1.0) == 2.0
        assert handle_refresh_time("+", 2.0) == 3.0

    def test_increase_max(self):
        """+ respects maximum."""
        assert handle_refresh_time("+", 5.0) == 5.0
        assert handle_refresh_time("+", 4.5) == 5.0

    def test_decrease(self):
        """- decreases refresh time."""
        assert handle_refresh_time("-", 2.0) == 1.0
        assert handle_refresh_time("-", 3.0) == 2.0

    def test_decrease_min(self):
        """- respects minimum."""
        assert handle_refresh_time("-", 0.5) == 0.5
        assert handle_refresh_time("-", 1.0) == 0.5

    def test_invalid_key(self):
        """Invalid key raises ValueError."""
        with pytest.raises(ValueError, match="invalid key"):
            handle_refresh_time("x", 1.0)


class TestHandleDurationMode:
    """Tests for handle_duration_mode function."""

    def test_cycles_modes(self):
        """T cycles through duration modes."""
        assert handle_duration_mode("T", DurationMode.query) == DurationMode.transaction
        assert handle_duration_mode("T", DurationMode.transaction) == DurationMode.backend
        assert handle_duration_mode("T", DurationMode.backend) == DurationMode.query

    def test_other_key_no_change(self):
        """Other keys don't change mode."""
        assert handle_duration_mode("x", DurationMode.query) == DurationMode.query
        assert handle_duration_mode("x", DurationMode.backend) == DurationMode.backend


class TestHandleWrapQuery:
    """Tests for handle_wrap_query function."""

    def test_toggles_wrap(self):
        """v toggles wrap."""
        assert handle_wrap_query("v", False) is True
        assert handle_wrap_query("v", True) is False

    def test_other_key_no_change(self):
        """Other keys don't change wrap."""
        assert handle_wrap_query("x", True) is True
        assert handle_wrap_query("x", False) is False


class TestHandleQueryMode:
    """Tests for handle_query_mode function."""

    def test_number_keys(self):
        """1/2/3 switch query modes."""
        assert handle_query_mode("1") == QueryMode.activities
        assert handle_query_mode("2") == QueryMode.waiting
        assert handle_query_mode("3") == QueryMode.blocking

    def test_function_keys(self):
        """F1/F2/F3 switch query modes."""
        key = MockKey(code=curses.KEY_F1)
        assert handle_query_mode(key) == QueryMode.activities

        key = MockKey(code=curses.KEY_F2)
        assert handle_query_mode(key) == QueryMode.waiting

        key = MockKey(code=curses.KEY_F3)
        assert handle_query_mode(key) == QueryMode.blocking

    def test_invalid_key(self):
        """Invalid keys return None."""
        assert handle_query_mode("x") is None
        assert handle_query_mode("9") is None


class TestHandleSortKey:
    """Tests for handle_sort_key function."""

    @pytest.fixture
    def all_flags(self):
        """Return all column flags enabled."""
        return ColumnFlag.all()

    def test_cpu_sort(self, all_flags):
        """c sorts by CPU in activities mode."""
        assert handle_sort_key("c", QueryMode.activities, all_flags) == SortKey.cpu

    def test_mem_sort(self, all_flags):
        """m sorts by memory in activities mode."""
        assert handle_sort_key("m", QueryMode.activities, all_flags) == SortKey.mem

    def test_read_sort(self, all_flags):
        """r sorts by read in activities mode."""
        assert handle_sort_key("r", QueryMode.activities, all_flags) == SortKey.read

    def test_write_sort(self, all_flags):
        """w sorts by write in activities mode."""
        assert handle_sort_key("w", QueryMode.activities, all_flags) == SortKey.write

    def test_time_sort(self, all_flags):
        """t sorts by time/duration in activities mode."""
        assert handle_sort_key("t", QueryMode.activities, all_flags) == SortKey.duration

    def test_invalid_key(self, all_flags):
        """Invalid keys return None in activities mode."""
        assert handle_sort_key("x", QueryMode.activities, all_flags) is None

    def test_non_activities_mode(self, all_flags):
        """In non-activities mode, always return duration."""
        assert handle_sort_key("c", QueryMode.waiting, all_flags) == SortKey.duration
        assert handle_sort_key("c", QueryMode.blocking, all_flags) == SortKey.duration

    def test_flag_not_enabled(self):
        """Sort key not returned if flag not enabled."""
        # Only TIME flag enabled
        flag = ColumnFlag.TIME
        assert handle_sort_key("c", QueryMode.activities, flag) is None
        assert handle_sort_key("t", QueryMode.activities, flag) == SortKey.duration
