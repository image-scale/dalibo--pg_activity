"""Tests for utility functions."""

import tempfile
from datetime import timedelta

import pytest

from pgmonitor.utils import (
    format_duration,
    naturalsize,
    yn,
    clean_str,
    ellipsis,
    short_state,
    wait_status,
    get_duration,
    MessagePile,
    csv_write,
    naturaltimedelta,
)


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_none_duration(self):
        """None duration returns N/A in green."""
        result, color = format_duration(None)
        assert "N/A" in result
        assert color == "green"

    def test_negative_duration(self):
        """Negative duration is treated as 0."""
        result, color = format_duration(-1.0)
        assert result == "0.000000"
        assert color == "green"

    def test_subsecond_duration(self):
        """Sub-second duration shows microseconds."""
        result, color = format_duration(0.5)
        assert result == "0.500000"
        assert color == "green"

    def test_short_duration_yellow(self):
        """Duration 1-3 seconds is yellow."""
        result, color = format_duration(2.0)
        assert "00:02" in result
        assert color == "yellow"

    def test_medium_duration_red(self):
        """Duration > 3 seconds is red."""
        result, color = format_duration(5.0)
        assert "00:05" in result
        assert color == "red"

    def test_long_duration_hours(self):
        """Duration > 60000 seconds shows hours."""
        result, color = format_duration(72000)  # 20 hours
        assert "20 h" in result
        assert color == "red"

    def test_exact_minute(self):
        """60 seconds formats correctly."""
        result, color = format_duration(60.0)
        assert result == "01:00.00"


class TestNaturalsize:
    """Tests for naturalsize function."""

    def test_bytes(self):
        """Small values show bytes."""
        result = naturalsize(100)
        assert "100" in result.lower()

    def test_kilobytes(self):
        """KB values format correctly."""
        result = naturalsize(1024)
        assert "K" in result or "k" in result.lower()

    def test_megabytes(self):
        """MB values format correctly."""
        result = naturalsize(1024 * 1024)
        assert "M" in result

    def test_gigabytes(self):
        """GB values format correctly."""
        result = naturalsize(1024 * 1024 * 1024)
        assert "G" in result


class TestYn:
    """Tests for yn function."""

    def test_true_returns_y(self):
        """True returns 'Y'."""
        assert yn(True) == "Y"

    def test_false_returns_n(self):
        """False returns 'N'."""
        assert yn(False) == "N"


class TestCleanStr:
    """Tests for clean_str function."""

    def test_newlines_removed(self):
        """Newlines are replaced with spaces."""
        assert clean_str("hello\nworld") == "hello world"

    def test_multiple_spaces_collapsed(self):
        """Multiple spaces collapse to one."""
        assert clean_str("hello    world") == "hello world"

    def test_tabs_collapsed(self):
        """Tabs are collapsed."""
        assert clean_str("hello\t\tworld") == "hello world"

    def test_leading_trailing_stripped(self):
        """Leading/trailing whitespace is removed."""
        assert clean_str("  hello  ") == "hello"

    def test_empty_after_strip(self):
        """Empty string after stripping returns empty."""
        assert clean_str("   \n   ") == ""


class TestEllipsis:
    """Tests for ellipsis function."""

    def test_short_text_unchanged(self):
        """Short text is returned unchanged."""
        assert ellipsis("hello", 10) == "hello"

    def test_exact_width(self):
        """Text at exact width is unchanged."""
        assert ellipsis("hello", 5) == "hello"

    def test_truncated_with_ellipsis(self):
        """Long text is truncated with ... in middle."""
        result = ellipsis("longerthanwidth", 7)
        assert len(result) == 7
        assert "..." in result

    def test_minimum_width(self):
        """Width less than 5 just truncates."""
        result = ellipsis("hello", 3)
        assert result == "hel"


class TestShortState:
    """Tests for short_state function."""

    def test_active_unchanged(self):
        """'active' is unchanged."""
        assert short_state("active") == "active"

    def test_idle_in_transaction_shortened(self):
        """'idle in transaction' is shortened."""
        assert short_state("idle in transaction") == "idle in trans"

    def test_idle_in_transaction_aborted_shortened(self):
        """'idle in transaction (aborted)' is shortened."""
        assert short_state("idle in transaction (aborted)") == "idle in trans (a)"

    def test_unknown_state_unchanged(self):
        """Unknown states are unchanged."""
        assert short_state("custom_state") == "custom_state"


class TestWaitStatus:
    """Tests for wait_status function."""

    def test_none_returns_empty(self):
        """None returns empty string."""
        assert wait_status(None) == ""

    def test_true_returns_y(self):
        """True returns 'Y'."""
        assert wait_status(True) == "Y"

    def test_false_returns_n(self):
        """False returns 'N'."""
        assert wait_status(False) == "N"

    def test_string_returned_as_is(self):
        """String values are returned as-is."""
        assert wait_status("ClientRead") == "ClientRead"


class TestGetDuration:
    """Tests for get_duration function."""

    def test_none_returns_zero(self):
        """None returns 0."""
        assert get_duration(None) == 0

    def test_negative_returns_zero(self):
        """Negative values return 0."""
        assert get_duration(-5) == 0

    def test_positive_returns_value(self):
        """Positive values are returned as float."""
        assert get_duration(10) == 10.0
        assert get_duration(5.5) == 5.5


class TestMessagePile:
    """Tests for MessagePile class."""

    def test_empty_pile_returns_none(self):
        """Empty pile returns None."""
        pile = MessagePile(n=2)
        assert pile.get() is None

    def test_message_returned_n_times(self):
        """Message is returned n times then None."""
        pile = MessagePile(n=2)
        pile.send("hello")
        assert pile.get() == "hello"
        assert pile.get() == "hello"
        assert pile.get() is None

    def test_new_message_replaces_old(self):
        """New message replaces old message."""
        pile = MessagePile(n=2)
        pile.send("first")
        pile.get()
        pile.send("second")
        assert pile.get() == "second"


class TestCsvWrite:
    """Tests for csv_write function."""

    def test_writes_header(self):
        """CSV header is written at beginning of file."""
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv') as f:
            csv_write(f, [])
            f.seek(0)
            content = f.read()
            assert "datetimeutc" in content
            assert "pid" in content

    def test_writes_process_data(self):
        """Process data is written correctly."""
        procs = [{
            'pid': 123,
            'database': 'testdb',
            'user': 'postgres',
            'query': 'SELECT 1',
            'state': 'active',
            'duration': 1.5,
            'wait': False,
            'cpu': 5.0,
            'mem': 2.0,
            'read': 1024,
            'write': 512,
            'io_wait': False,
            'application_name': 'app',
            'xmin': 100,
            'client': 'localhost',
        }]
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv') as f:
            csv_write(f, procs)
            f.seek(0)
            lines = f.readlines()
            assert len(lines) == 2  # header + 1 data row
            assert '"123"' in lines[1]
            assert '"testdb"' in lines[1]

    def test_handles_missing_fields(self):
        """Missing fields are handled gracefully."""
        procs = [{'pid': 123}]
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv') as f:
            csv_write(f, procs)
            f.seek(0)
            lines = f.readlines()
            assert len(lines) == 2
            assert '"N/A"' in lines[1]


class TestNaturaltimedelta:
    """Tests for naturaltimedelta function."""

    def test_simple_timedelta(self):
        """Simple timedelta formats correctly."""
        result = naturaltimedelta(timedelta(hours=5, minutes=30))
        assert "5:30" in result

    def test_days_included(self):
        """Days are included in output."""
        result = naturaltimedelta(timedelta(days=2, hours=3))
        assert "2 day" in result
