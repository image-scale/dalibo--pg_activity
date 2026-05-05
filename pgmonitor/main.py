"""Main entry point and CLI for pg_monitor."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from blessed import Terminal

from . import __version__
from .activities import get_system_info, mem_swap_load, ps_complete
from .config import Configuration, ConfigError
from .data import DatabaseManager
from .keys import (
    EXIT,
    HELP,
    SPACE,
    PROCESS_CANCEL,
    PROCESS_KILL,
    is_process_first,
    is_process_last,
    is_process_next,
    is_process_nextpage,
    is_process_prev,
    is_process_prevpage,
    is_toggle_header_instance,
    is_toggle_header_system,
    is_toggle_header_workers,
    handle_duration_mode,
    handle_query_mode,
    handle_refresh_time,
    handle_sort_key,
    handle_wrap_query,
    REFRESH_TIME_INCREASE,
    REFRESH_TIME_DECREASE,
)
from .types import (
    DurationMode,
    Filters,
    QueryMode,
    RunningProcess,
    SelectableProcesses,
    SortKey,
    SystemProcess,
)
from .utils import MessagePile
from .views import (
    boxed,
    get_default_columns,
    render_footer_help,
    render_footer_interactive,
    render_footer_message,
    render_header,
    render_help,
    render_query_mode,
    render_columns_header,
    render_processes,
    LineCounter,
    screen,
)


def get_parser(prog: str | None = None) -> argparse.ArgumentParser:
    """Create argument parser for CLI.

    >>> parser = get_parser("pg_monitor")
    >>> parser.prog
    'pg_monitor'
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description="htop-like PostgreSQL server activity monitoring tool.",
        add_help=False,
    )

    # Connection options
    conn_group = parser.add_argument_group("Connection Options")
    conn_group.add_argument(
        "-h", "--host",
        dest="host",
        metavar="HOSTNAME",
        help="Database server host or socket directory.",
    )
    conn_group.add_argument(
        "-p", "--port",
        dest="port",
        metavar="PORT",
        type=int,
        default=5432,
        help="Database server port (default: %(default)s).",
    )
    conn_group.add_argument(
        "-U", "--username",
        dest="user",
        metavar="USERNAME",
        help="Database user name.",
    )
    conn_group.add_argument(
        "-d", "--dbname",
        dest="dbname",
        metavar="DBNAME",
        help="Database name to connect to.",
    )

    # Configuration options
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "-P", "--profile",
        dest="profile",
        metavar="PROFILE",
        help="Configuration profile name.",
    )

    # Display options
    display_group = parser.add_argument_group("Display Options")
    display_group.add_argument(
        "--refresh",
        dest="refresh",
        metavar="SECONDS",
        type=float,
        choices=[0.5, 1, 2, 3, 4, 5],
        default=2,
        help="Refresh rate in seconds (default: %(default)s).",
    )
    display_group.add_argument(
        "--duration-mode",
        dest="duration_mode",
        metavar="MODE",
        choices=["1", "2", "3"],
        default="1",
        help="Duration mode: 1=query, 2=transaction, 3=backend (default: %(default)s).",
    )
    display_group.add_argument(
        "-w", "--wrap-query",
        dest="wrap_query",
        action="store_true",
        help="Wrap query column instead of truncating.",
    )
    display_group.add_argument(
        "--filter",
        dest="filters",
        metavar="FIELD:REGEX",
        action="append",
        default=[],
        help="Filter activities by field regex.",
    )

    # Other options
    other_group = parser.add_argument_group("Other Options")
    other_group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    other_group.add_argument(
        "--help",
        dest="help",
        action="store_true",
        help="Show this help message and exit.",
    )

    return parser


class UIState:
    """State of the user interface.

    >>> state = UIState()
    >>> state.query_mode
    <QueryMode.activities: 'running queries'>
    >>> state.refresh_time
    2.0
    """

    def __init__(
        self,
        *,
        refresh_time: float = 2.0,
        duration_mode: DurationMode = DurationMode.query,
        query_mode: QueryMode = QueryMode.activities,
        sort_key: SortKey = SortKey.duration,
        wrap_query: bool = False,
        in_pause: bool = False,
        show_header_system: bool = True,
        show_header_instance: bool = True,
        show_header_workers: bool = True,
    ):
        self.refresh_time = refresh_time
        self.duration_mode = duration_mode
        self.query_mode = query_mode
        self.sort_key = sort_key
        self.wrap_query = wrap_query
        self.in_pause = in_pause
        self.show_header_system = show_header_system
        self.show_header_instance = show_header_instance
        self.show_header_workers = show_header_workers
        self._interactive = False
        self._interactive_timeout = 0

    def interactive(self) -> bool:
        """Check if in interactive mode (process selected)."""
        return self._interactive

    def start_interactive(self) -> None:
        """Enter interactive mode."""
        self._interactive = True
        self._interactive_timeout = 10  # seconds

    def end_interactive(self) -> None:
        """Exit interactive mode."""
        self._interactive = False
        self._interactive_timeout = 0

    def tick_interactive(self) -> None:
        """Decrement interactive timeout, exit if expired."""
        if self._interactive:
            self._interactive_timeout -= 1
            if self._interactive_timeout <= 0:
                self.end_interactive()

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        self.in_pause = not self.in_pause

    def toggle_header_system(self) -> None:
        """Toggle system header visibility."""
        self.show_header_system = not self.show_header_system

    def toggle_header_instance(self) -> None:
        """Toggle instance header visibility."""
        self.show_header_instance = not self.show_header_instance

    def toggle_header_workers(self) -> None:
        """Toggle workers header visibility."""
        self.show_header_workers = not self.show_header_workers


def run_ui(
    term: Terminal,
    db: DatabaseManager,
    state: UIState,
    *,
    is_local: bool = True,
    flag: Any = None,
) -> None:
    """Run the main UI loop.

    This is the core interactive loop that handles:
    - Fetching process data from database
    - Rendering the screen
    - Processing keyboard input
    - Managing process selection and actions
    """
    key = None
    in_help = False
    sys_procs: dict[int, SystemProcess] = {}
    pg_procs = SelectableProcesses([])
    msg_pile = MessagePile(2)
    system_info = None

    host_str = f"{db.host or 'localhost'}:{db.port}/{db.database}"

    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        while True:
            # Handle help screen
            if key == HELP:
                in_help = True
            elif in_help and key is not None:
                in_help = False
                key = None
                print(term.clear + term.home, end="")

            # Handle exit
            elif key == EXIT:
                break

            # Handle pause toggle (when not in interactive mode)
            elif not state.interactive() and key == SPACE:
                state.toggle_pause()

            # Handle key presses
            elif key is not None:
                if is_process_next(key):
                    if pg_procs.focus_next():
                        state.start_interactive()
                elif is_process_prev(key):
                    if pg_procs.focus_prev():
                        state.start_interactive()
                elif is_process_nextpage(key):
                    if pg_procs.focus_next(term.height // 3):
                        state.start_interactive()
                elif is_process_prevpage(key):
                    if pg_procs.focus_prev(term.height // 3):
                        state.start_interactive()
                elif is_process_first(key):
                    if pg_procs.focus_first():
                        state.start_interactive()
                elif is_process_last(key):
                    if pg_procs.focus_last():
                        state.start_interactive()
                elif key == SPACE:
                    pg_procs.toggle_pin_focused()
                elif hasattr(key, 'name') and key.name == "KEY_ESCAPE":
                    pg_procs.reset()
                    state.end_interactive()
                elif is_toggle_header_system(key):
                    state.toggle_header_system()
                elif is_toggle_header_instance(key):
                    state.toggle_header_instance()
                elif is_toggle_header_workers(key):
                    state.toggle_header_workers()

                # Handle cancel/terminate
                elif pg_procs.selected and key in (PROCESS_CANCEL, PROCESS_KILL):
                    action = "cancel" if key == PROCESS_CANCEL else "terminate"
                    color = "yellow" if key == PROCESS_CANCEL else "red"
                    pids = pg_procs.selected

                    if len(pids) > 1:
                        ptitle = f"processes {', '.join(str(p) for p in pids)}"
                    else:
                        ptitle = f"process {pids[0]}"

                    # Show confirmation dialog
                    with term.location(x=0, y=term.height // 3):
                        color_func = getattr(term, color)
                        msg = f"Confirm {color_func(action)} action on {ptitle}? (y/n)"
                        print(boxed(term, msg, border_color=color, center=True, width=term.width), end="")
                        confirm = term.inkey(timeout=None)

                    if confirm.lower() == "y":
                        for pid in pids:
                            if action == "cancel":
                                db.cancel_backend(pid)
                            else:
                                db.terminate_backend(pid)
                        action_color = getattr(term, color)
                        msg_pile.send(action_color(f"{ptitle.capitalize()} {action}led"))
                        pg_procs.reset()
                        state.end_interactive()

                else:
                    # Handle other keys (mode changes, sorting, etc.)
                    pg_procs.reset()
                    state.end_interactive()

                    # Duration mode
                    state.duration_mode = handle_duration_mode(key, state.duration_mode)

                    # Wrap query
                    state.wrap_query = handle_wrap_query(key, state.wrap_query)

                    # Refresh time
                    if key in (REFRESH_TIME_INCREASE, REFRESH_TIME_DECREASE):
                        state.refresh_time = handle_refresh_time(key, state.refresh_time)

                    # Query mode
                    new_query_mode = handle_query_mode(key)
                    if new_query_mode is not None:
                        state.query_mode = new_query_mode

                    # Sort key
                    if flag is not None:
                        new_sort = handle_sort_key(key, state.query_mode, flag)
                        if new_sort is not None:
                            state.sort_key = new_sort

            # Render screen
            if in_help:
                if key is not None:
                    print(term.clear + term.home, end="")
                    render_help(term, __version__, is_local, lines_counter=LineCounter(term.height))
            else:
                # Fetch data if not paused and not in interactive mode
                if not state.in_pause and not state.interactive():
                    if is_local:
                        system_info = get_system_info()

                    # Get processes based on query mode
                    if state.query_mode == QueryMode.activities:
                        procs = db.get_activities(state.duration_mode)
                        if is_local and procs:
                            local_procs, io_read, io_write = ps_complete(
                                procs, sys_procs, refresh_interval=state.refresh_time
                            )
                            pg_procs.set_items(local_procs)
                        else:
                            pg_procs.set_items(procs)
                    elif state.query_mode == QueryMode.waiting:
                        pg_procs.set_items(db.get_waiting(state.duration_mode))
                    elif state.query_mode == QueryMode.blocking:
                        pg_procs.set_items(db.get_blocking(state.duration_mode))

                # Render the screen
                screen(
                    term,
                    pg_version=db.pg_version,
                    host=host_str,
                    refresh_time=state.refresh_time,
                    duration_mode=state.duration_mode,
                    query_mode=state.query_mode,
                    sort_key=state.sort_key,
                    processes=pg_procs,
                    system_info=system_info if is_local else None,
                    message=msg_pile.get(),
                    in_pause=state.in_pause,
                    interactive=state.interactive(),
                    wrap_query=state.wrap_query,
                    is_local=is_local,
                )

                # Tick interactive timeout
                if state.interactive():
                    if not pg_procs.pinned:
                        state.tick_interactive()
                elif pg_procs.selected:
                    pg_procs.reset()

            # Wait for input
            key = term.inkey(timeout=state.refresh_time) or None


def main() -> None:
    """Main entry point for pg_monitor CLI.

    Parses command-line arguments, connects to the database,
    and runs the interactive monitoring UI.
    """
    parser = get_parser()
    args = parser.parse_args()

    if args.help:
        parser.print_help()
        sys.exit(0)

    # Parse filters
    try:
        filters = Filters.from_options(args.filters) if args.filters else None
    except ValueError as e:
        parser.error(str(e))

    # Load configuration profile
    config = None
    if args.profile:
        try:
            config = Configuration.lookup(args.profile)
        except (ConfigError, FileNotFoundError) as e:
            parser.error(str(e))

    # Create database manager
    db = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        database=args.dbname,
        filters=filters,
    )

    # Connect to database
    try:
        db.connect()
    except Exception as e:
        parser.exit(status=1, message=f"could not connect to PostgreSQL: {e}\n")

    # Determine if local connection
    is_local = db.pg_is_local()

    # Get column flags from config
    flag = None
    if config:
        flag = config.column_flag(is_local=is_local)

    # Create UI state
    state = UIState(
        refresh_time=args.refresh,
        duration_mode=DurationMode(int(args.duration_mode)),
        wrap_query=args.wrap_query,
    )

    # Create terminal and run UI
    term = Terminal()

    while True:
        try:
            run_ui(term, db, state, is_local=is_local, flag=flag)
            break
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            # Try to reconnect
            print(term.clear + term.home, end="")
            print(f"Error: {e}")
            print("Attempting to reconnect in 5 seconds...")
            try:
                time.sleep(5)
                db.connect()
            except KeyboardInterrupt:
                sys.exit(1)
            except Exception:
                continue


if __name__ == "__main__":
    main()
