"""Main UI module."""
from __future__ import annotations

import time
from argparse import Namespace
from typing import TYPE_CHECKING

from blessed import Terminal
from blessed.keyboard import Keystroke

from . import activities, handlers, keys, views, widgets
from .config import Configuration, Flag
from .data import Data
from .types import (
    ActivityStats,
    DurationMode,
    Host,
    IOCounter,
    QueryMode,
    SelectableProcesses,
    SystemInfo,
    UI,
)
from .utils import MessagePile, csv_write, osc52_copy

if TYPE_CHECKING:
    pass


def main(
    term: Terminal,
    config: Configuration,
    dataobj: Data,
    host: Host,
    options: Namespace,
    *,
    render_header: bool = True,
    render_footer: bool = True,
    width: int | None = None,
    wait_on_actions: float = 3,
) -> None:
    """Main UI loop."""
    # Determine if local access
    is_local = dataobj.pg_is_local_access()

    # Initialize UI state
    flag = Flag.from_options(options)
    config = config.merged_with_flag(flag)

    ui = UI.make(
        flag=flag,
        min_duration=options.minduration,
        duration_mode=DurationMode(int(options.durationmode)),
        wrap_query=options.wrap_query,
        refresh_time=options.refresh,
        header_show_instance=options.header_show_instance
        if options.header_show_instance is not None
        else True,
        header_show_workers=options.header_show_workers
        if options.header_show_workers is not None
        else True,
        header_show_system=options.header_show_system
        if options.header_show_system is not None
        else True,
        config=config,
        filters=dataobj.filters,
    )

    # Initialize system processes
    system_processes: dict[int, activities.SystemProcess] = {}
    max_iops = 0
    io_read = IOCounter(0, 0)
    io_write = IOCounter(0, 0)
    message_pile = MessagePile(int(wait_on_actions))

    # Server information
    server_info = dataobj.pg_get_server_information(
        prev_server_info=None,
        using_rds=options.rds,
        skip_db_size=not options.dbsize,
        skip_tempfile=options.tempfiles is False or options.rds,
        skip_walreceiver=options.walreceiver is False,
    )

    # CSV output file
    csv_file = None
    if options.output:
        csv_file = open(options.output, "w")

    try:
        while True:
            # Fetch activities
            if ui.query_mode == QueryMode.activities:
                raw_processes = dataobj.pg_get_activities(
                    duration_mode=ui.duration_mode.value
                )
            elif ui.query_mode == QueryMode.waiting:
                raw_processes = dataobj.pg_get_waiting(
                    duration_mode=ui.duration_mode.value
                )
            elif ui.query_mode == QueryMode.blocking:
                raw_processes = dataobj.pg_get_blocking(
                    duration_mode=ui.duration_mode.value
                )
            else:
                raw_processes = []

            # Get system info if local
            system_info: SystemInfo | None = None
            if is_local and ui.query_mode == QueryMode.activities:
                local_procs, io_read, io_write = activities.ps_complete(
                    raw_processes,
                    system_processes,
                    options.blocksize,
                )
                max_iops = activities.update_max_iops(
                    max_iops, io_read.count, io_write.count
                )
                memory, swap, load = activities.mem_swap_load()
                system_info = SystemInfo(
                    memory=memory,
                    swap=swap,
                    load=load,
                    io_read=io_read,
                    io_write=io_write,
                    max_iops=max_iops,
                )
                procs = SelectableProcesses(local_procs)
            else:
                procs = SelectableProcesses(list(raw_processes))

            activity_stats: ActivityStats
            if system_info is not None:
                activity_stats = (procs, system_info)
            else:
                activity_stats = procs

            # Write to CSV if enabled
            if csv_file is not None:
                csv_write(
                    csv_file,
                    [dict(p) for p in procs],
                )

            # Render screen
            views.screen(
                term,
                ui,
                host=host,
                pg_version=dataobj.pg_version,
                server_information=server_info,
                activity_stats=activity_stats,
                message=message_pile.get(),
                render_header=render_header,
                render_footer=render_footer,
                width=width,
            )

            # Wait for key input
            key = term.inkey(timeout=ui.refresh_time)

            # Handle key input
            if not key:
                # Timeout - refresh
                if not ui.in_pause:
                    server_info = dataobj.pg_get_server_information(
                        prev_server_info=server_info,
                        using_rds=options.rds,
                        skip_db_size=not options.dbsize,
                        skip_tempfile=options.tempfiles is False or options.rds,
                        skip_walreceiver=options.walreceiver is False,
                    )
                continue

            # Exit
            if key == keys.EXIT:
                break

            # Help
            if key == keys.HELP:
                # Display help
                print(term.home + term.clear, end="")
                views.help(term, dataobj.pg_version, is_local)
                term.inkey()  # Wait for any key
                continue

            # Pause
            if key == keys.SPACE:
                if ui.interactive():
                    # Interactive mode - pin/unpin process
                    procs.toggle_pin()
                else:
                    ui = ui.toggle_pause()
                continue

            # Refresh time
            if key in (keys.REFRESH_TIME_INCREASE, keys.REFRESH_TIME_DECREASE):
                new_refresh = handlers.refresh_time(key, ui.refresh_time)
                ui = ui.evolve(refresh_time=new_refresh)
                continue

            # Duration mode
            if key == keys.CHANGE_DURATION_MODE:
                new_mode = handlers.duration_mode(key, ui.duration_mode)
                ui = ui.evolve(duration_mode=new_mode)
                continue

            # Wrap query
            if key == keys.WRAP_QUERY:
                ui = ui.evolve(wrap_query=handlers.wrap_query(key, ui.wrap_query))
                continue

            # Query mode
            new_qm = handlers.query_mode(key)
            if new_qm is not None:
                ui = ui.evolve(query_mode=new_qm)
                continue

            # Sort key
            sort_key = handlers.sort_key_for(key, ui.query_mode, flag)
            if sort_key is not None:
                ui = ui.evolve(sort_key=sort_key)
                continue

            # Header toggles
            if keys.is_toggle_header_system(key):
                ui = ui.evolve(
                    header=ui.header.evolve(show_system=not ui.header.show_system)
                )
                continue
            if keys.is_toggle_header_instance(key):
                ui = ui.evolve(
                    header=ui.header.evolve(show_instance=not ui.header.show_instance)
                )
                continue
            if keys.is_toggle_header_workers(key):
                ui = ui.evolve(
                    header=ui.header.evolve(show_workers=not ui.header.show_workers)
                )
                continue

            # Process navigation
            if keys.is_process_next(key) or keys.is_process_next_vi(key):
                procs.focus_next()
                continue
            if keys.is_process_prev(key) or keys.is_process_prev_vi(key):
                procs.focus_prev()
                continue
            if keys.is_process_nextpage(key):
                procs.focus_next_page()
                continue
            if keys.is_process_prevpage(key):
                procs.focus_prev_page()
                continue
            if keys.is_process_first(key):
                procs.focus_first()
                continue
            if keys.is_process_last(key):
                procs.focus_last()
                continue

            # DB size refresh
            if key == keys.REFRESH_DB_SIZE:
                server_info = dataobj.pg_get_server_information(
                    prev_server_info=server_info,
                    using_rds=options.rds,
                    skip_db_size=False,
                    skip_tempfile=options.tempfiles is False or options.rds,
                    skip_walreceiver=options.walreceiver is False,
                )
                continue

            # Force refresh
            if key == "R":
                server_info = dataobj.pg_get_server_information(
                    prev_server_info=server_info,
                    using_rds=options.rds,
                    skip_db_size=not options.dbsize,
                    skip_tempfile=options.tempfiles is False or options.rds,
                    skip_walreceiver=options.walreceiver is False,
                )
                continue

            # Copy to clipboard
            if key == keys.COPY_TO_CLIPBOARD:
                focused = procs.focused
                if focused is not None:
                    for p in procs:
                        if p.pid == focused:
                            if p.query:
                                osc52_copy(p.query)
                                message_pile.send(
                                    f"query of process {focused} copied to clipboard"
                                )
                            break
                continue

            # Cancel backend
            if key == keys.PROCESS_CANCEL:
                pids = procs.selected_pids()
                if pids:
                    pid_str = ", ".join(str(p) for p in pids)
                    confirm_msg = f"Confirm cancel action on process{'es' if len(pids) > 1 else ''}  {pid_str}? (y/n)"
                    print(widgets.boxed(term, confirm_msg, center=True), end="")
                    confirm_key = term.inkey()
                    if confirm_key == "y":
                        for pid in pids:
                            if dataobj.pg_cancel_backend(pid):
                                pass
                        if len(pids) == 1:
                            message_pile.send(f"Process {pids[0]} canceled")
                        else:
                            message_pile.send(f"Processes {pid_str} canceled")
                        procs.reset_selection()
                continue

            # Kill backend
            if key == keys.PROCESS_KILL:
                pids = procs.selected_pids()
                if pids:
                    pid_str = ", ".join(str(p) for p in pids)
                    confirm_msg = f"Confirm terminate action on process{'es' if len(pids) > 1 else ''}  {pid_str}? (y/n)"
                    print(widgets.boxed(term, confirm_msg, center=True), end="")
                    confirm_key = term.inkey()
                    if confirm_key == "y":
                        for pid in pids:
                            if dataobj.pg_terminate_backend(pid):
                                pass
                        if len(pids) == 1:
                            message_pile.send(f"Process {pids[0]} terminated")
                        else:
                            message_pile.send(f"Processes {pid_str} terminated")
                        procs.reset_selection()
                continue

    finally:
        if csv_file is not None:
            csv_file.close()


def keys_is_process_next_vi(key: Keystroke) -> bool:
    """Check if key is process next VI key."""
    return key == keys.PROCESS_NEXT_VI


def keys_is_process_prev_vi(key: Keystroke) -> bool:
    """Check if key is process prev VI key."""
    return key == keys.PROCESS_PREV_VI
