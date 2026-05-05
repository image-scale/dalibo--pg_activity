"""Tests for main entry point and CLI."""

import pytest
from unittest.mock import MagicMock, patch

from pgmonitor.main import (
    get_parser,
    UIState,
)
from pgmonitor.types import DurationMode, QueryMode, SortKey


class TestGetParser:
    """Tests for get_parser function."""

    def test_parser_created(self):
        """Parser is created."""
        parser = get_parser()
        assert parser is not None

    def test_parser_prog(self):
        """Parser has custom prog name."""
        parser = get_parser("my_pg_monitor")
        assert parser.prog == "my_pg_monitor"

    def test_host_argument(self):
        """Parser accepts --host."""
        parser = get_parser()
        args = parser.parse_args(["--host", "localhost"])
        assert args.host == "localhost"

    def test_port_argument(self):
        """Parser accepts --port."""
        parser = get_parser()
        args = parser.parse_args(["--port", "5433"])
        assert args.port == 5433

    def test_port_default(self):
        """Parser has default port."""
        parser = get_parser()
        args = parser.parse_args([])
        assert args.port == 5432

    def test_username_argument(self):
        """Parser accepts --username."""
        parser = get_parser()
        args = parser.parse_args(["--username", "postgres"])
        assert args.user == "postgres"

    def test_dbname_argument(self):
        """Parser accepts --dbname."""
        parser = get_parser()
        args = parser.parse_args(["--dbname", "testdb"])
        assert args.dbname == "testdb"

    def test_profile_argument(self):
        """Parser accepts --profile."""
        parser = get_parser()
        args = parser.parse_args(["--profile", "minimal"])
        assert args.profile == "minimal"

    def test_refresh_argument(self):
        """Parser accepts --refresh."""
        parser = get_parser()
        args = parser.parse_args(["--refresh", "1"])
        assert args.refresh == 1.0

    def test_refresh_default(self):
        """Parser has default refresh."""
        parser = get_parser()
        args = parser.parse_args([])
        assert args.refresh == 2

    def test_duration_mode_argument(self):
        """Parser accepts --duration-mode."""
        parser = get_parser()
        args = parser.parse_args(["--duration-mode", "2"])
        assert args.duration_mode == "2"

    def test_wrap_query_argument(self):
        """Parser accepts --wrap-query."""
        parser = get_parser()
        args = parser.parse_args(["--wrap-query"])
        assert args.wrap_query is True

    def test_wrap_query_default(self):
        """Parser has default wrap_query."""
        parser = get_parser()
        args = parser.parse_args([])
        assert args.wrap_query is False

    def test_filter_argument(self):
        """Parser accepts --filter."""
        parser = get_parser()
        args = parser.parse_args(["--filter", "dbname:test"])
        assert args.filters == ["dbname:test"]

    def test_multiple_filters(self):
        """Parser accepts multiple --filter."""
        parser = get_parser()
        args = parser.parse_args(["--filter", "dbname:test", "--filter", "dbname:prod"])
        assert args.filters == ["dbname:test", "dbname:prod"]

    def test_help_argument(self):
        """Parser accepts --help."""
        parser = get_parser()
        args = parser.parse_args(["--help"])
        assert args.help is True


class TestUIState:
    """Tests for UIState class."""

    def test_default_state(self):
        """UIState has sensible defaults."""
        state = UIState()
        assert state.refresh_time == 2.0
        assert state.duration_mode == DurationMode.query
        assert state.query_mode == QueryMode.activities
        assert state.sort_key == SortKey.duration
        assert state.wrap_query is False
        assert state.in_pause is False

    def test_custom_state(self):
        """UIState accepts custom values."""
        state = UIState(
            refresh_time=1.0,
            duration_mode=DurationMode.transaction,
            query_mode=QueryMode.waiting,
            sort_key=SortKey.cpu,
            wrap_query=True,
            in_pause=True,
        )
        assert state.refresh_time == 1.0
        assert state.duration_mode == DurationMode.transaction
        assert state.query_mode == QueryMode.waiting
        assert state.sort_key == SortKey.cpu
        assert state.wrap_query is True
        assert state.in_pause is True

    def test_interactive_default(self):
        """UIState starts not interactive."""
        state = UIState()
        assert state.interactive() is False

    def test_start_interactive(self):
        """start_interactive enables interactive mode."""
        state = UIState()
        state.start_interactive()
        assert state.interactive() is True

    def test_end_interactive(self):
        """end_interactive disables interactive mode."""
        state = UIState()
        state.start_interactive()
        state.end_interactive()
        assert state.interactive() is False

    def test_tick_interactive(self):
        """tick_interactive decrements timeout."""
        state = UIState()
        state.start_interactive()
        for _ in range(10):
            state.tick_interactive()
        # Should auto-exit after timeout
        assert state.interactive() is False

    def test_toggle_pause(self):
        """toggle_pause toggles pause state."""
        state = UIState()
        assert state.in_pause is False
        state.toggle_pause()
        assert state.in_pause is True
        state.toggle_pause()
        assert state.in_pause is False

    def test_toggle_header_system(self):
        """toggle_header_system toggles system header."""
        state = UIState()
        assert state.show_header_system is True
        state.toggle_header_system()
        assert state.show_header_system is False

    def test_toggle_header_instance(self):
        """toggle_header_instance toggles instance header."""
        state = UIState()
        assert state.show_header_instance is True
        state.toggle_header_instance()
        assert state.show_header_instance is False

    def test_toggle_header_workers(self):
        """toggle_header_workers toggles workers header."""
        state = UIState()
        assert state.show_header_workers is True
        state.toggle_header_workers()
        assert state.show_header_workers is False


class TestMainFunction:
    """Tests for main function behavior."""

    def test_main_exists(self):
        """main function exists."""
        from pgmonitor.main import main
        assert callable(main)

    def test_run_ui_exists(self):
        """run_ui function exists."""
        from pgmonitor.main import run_ui
        assert callable(run_ui)
