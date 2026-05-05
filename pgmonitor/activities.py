"""System monitoring using psutil for local process metrics."""

from __future__ import annotations

import os
import time
from typing import Any

import psutil

from .types import (
    IOCounter,
    LoadAverage,
    LocalRunningProcess,
    MemoryInfo,
    RunningProcess,
    SwapInfo,
    SystemInfo,
    SystemProcess,
)


def mem_swap_load() -> tuple[MemoryInfo, SwapInfo, LoadAverage]:
    """Get memory, swap, and load average from psutil.

    Returns a tuple of (MemoryInfo, SwapInfo, LoadAverage).

    >>> mem, swap, load = mem_swap_load()
    >>> isinstance(mem, MemoryInfo)
    True
    >>> isinstance(swap, SwapInfo)
    True
    >>> isinstance(load, LoadAverage)
    True
    """
    vmem = psutil.virtual_memory()
    memory = MemoryInfo(
        used=vmem.total - vmem.free - getattr(vmem, 'buffers', 0) - getattr(vmem, 'cached', 0),
        buff_cached=getattr(vmem, 'buffers', 0) + getattr(vmem, 'cached', 0),
        free=vmem.free,
        total=vmem.total,
    )

    smem = psutil.swap_memory()
    swap = SwapInfo(
        used=smem.used,
        free=smem.free,
        total=smem.total,
    )

    load_tuple = os.getloadavg()
    load = LoadAverage(
        avg1=load_tuple[0],
        avg5=load_tuple[1],
        avg15=load_tuple[2],
    )

    return memory, swap, load


def sys_get_proc(pid: int) -> SystemProcess | None:
    """Get system process information for a PID.

    Returns SystemProcess or None if process doesn't exist.

    >>> result = sys_get_proc(1)  # PID 1 usually exists
    >>> result is None or isinstance(result, SystemProcess)
    True
    """
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            try:
                cpu_percent = proc.cpu_percent(interval=0)
            except psutil.NoSuchProcess:
                return None

            try:
                mem_percent = proc.memory_percent()
            except psutil.NoSuchProcess:
                return None

            try:
                meminfo = proc.memory_info()
                meminfo_tuple = (meminfo.rss, meminfo.vms)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                meminfo_tuple = (0, 0)

            try:
                cpu_times = proc.cpu_times()
                cpu_times_tuple = (cpu_times.user, cpu_times.system)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cpu_times_tuple = (0.0, 0.0)

            try:
                io_counters = proc.io_counters()
                io_read = IOCounter(io_counters.read_count, io_counters.read_bytes)
                io_write = IOCounter(io_counters.write_count, io_counters.write_bytes)
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                io_read = IOCounter.default()
                io_write = IOCounter.default()

            # Get io wait time if available
            try:
                io_time = cpu_times.iowait if hasattr(cpu_times, 'iowait') else 0.0
            except Exception:
                io_time = 0.0

            return SystemProcess(
                meminfo=meminfo_tuple,
                io_read=io_read,
                io_write=io_write,
                io_time=io_time,
                mem_percent=mem_percent,
                cpu_percent=cpu_percent,
                cpu_times=cpu_times_tuple,
                read_delta=0.0,
                write_delta=0.0,
                io_wait=False,
                psutil_proc=proc,
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def ps_complete(
    pg_processes: list[RunningProcess],
    system_procs: dict[int, SystemProcess],
    fs_blocksize: int = 512,
    refresh_interval: float = 2.0,
) -> tuple[list[LocalRunningProcess], IOCounter, IOCounter]:
    """Enrich PostgreSQL processes with system metrics.

    Takes a list of PostgreSQL processes and a dictionary of previous
    system process info, and returns enriched LocalRunningProcess
    instances with CPU, memory, and I/O metrics.

    >>> from pgmonitor.types import RunningProcess
    >>> procs = []
    >>> enriched, io_r, io_w = ps_complete(procs, {})
    >>> len(enriched)
    0
    """
    total_read = IOCounter.default()
    total_write = IOCounter.default()
    result: list[LocalRunningProcess] = []

    for pg_proc in pg_processes:
        # Get current system info for this process
        sys_proc = sys_get_proc(pg_proc.pid)
        if sys_proc is None:
            # Process no longer exists, skip it
            continue

        # Get previous system info if available
        prev_sys_proc = system_procs.get(pg_proc.pid)

        # Calculate CPU percentage
        cpu = sys_proc.cpu_percent

        # Calculate memory percentage
        mem = sys_proc.mem_percent

        # Calculate I/O deltas
        if prev_sys_proc is not None:
            read_bytes_delta = max(0, sys_proc.io_read.bytes - prev_sys_proc.io_read.bytes)
            write_bytes_delta = max(0, sys_proc.io_write.bytes - prev_sys_proc.io_write.bytes)

            # Convert to rate (bytes per second)
            read_rate = read_bytes_delta / refresh_interval if refresh_interval > 0 else 0
            write_rate = write_bytes_delta / refresh_interval if refresh_interval > 0 else 0

            # Detect I/O wait
            prev_io_time = prev_sys_proc.io_time
            io_time_delta = sys_proc.io_time - prev_io_time
            io_wait = io_time_delta > 0 and cpu < 1.0
        else:
            read_rate = 0.0
            write_rate = 0.0
            io_wait = False

        # Update system_procs dictionary with current info
        system_procs[pg_proc.pid] = sys_proc

        # Accumulate total I/O
        total_read = IOCounter(
            total_read.count + sys_proc.io_read.count,
            total_read.bytes + sys_proc.io_read.bytes,
        )
        total_write = IOCounter(
            total_write.count + sys_proc.io_write.count,
            total_write.bytes + sys_proc.io_write.bytes,
        )

        # Create enriched process
        local_proc = LocalRunningProcess.from_process(
            pg_proc,
            cpu=cpu,
            mem=mem,
            read=read_rate,
            write=write_rate,
            io_wait=io_wait,
        )
        result.append(local_proc)

    return result, total_read, total_write


def get_fs_blocksize() -> int:
    """Get the filesystem block size.

    >>> blocksize = get_fs_blocksize()
    >>> blocksize > 0
    True
    """
    try:
        statvfs = os.statvfs("/")
        return statvfs.f_bsize
    except (OSError, AttributeError):
        return 512


def get_system_info(
    prev_info: SystemInfo | None = None,
    io_read: IOCounter | None = None,
    io_write: IOCounter | None = None,
) -> SystemInfo:
    """Get current system information.

    >>> info = get_system_info()
    >>> isinstance(info.memory, MemoryInfo)
    True
    """
    memory, swap, load = mem_swap_load()

    # Calculate max IOPS if we have previous info
    max_iops = 0
    if prev_info is not None and io_read is not None and io_write is not None:
        prev_read = prev_info.io_read.bytes
        prev_write = prev_info.io_write.bytes
        read_iops = io_read.bytes - prev_read if io_read.bytes > prev_read else 0
        write_iops = io_write.bytes - prev_write if io_write.bytes > prev_write else 0
        max_iops = max(read_iops, write_iops)

    return SystemInfo(
        memory=memory,
        swap=swap,
        load=load,
        io_read=io_read or IOCounter.default(),
        io_write=io_write or IOCounter.default(),
        max_iops=max_iops,
    )


def sort_processes(
    processes: list[LocalRunningProcess],
    sort_key: str = "duration",
    reverse: bool = True,
) -> list[LocalRunningProcess]:
    """Sort processes by the specified key.

    >>> from pgmonitor.types import LocalRunningProcess
    >>> procs = []
    >>> sorted_procs = sort_processes(procs, "cpu")
    >>> isinstance(sorted_procs, list)
    True
    """
    key_funcs = {
        "cpu": lambda p: p.cpu or 0.0,
        "mem": lambda p: p.mem or 0.0,
        "read": lambda p: p.read or 0.0,
        "write": lambda p: p.write or 0.0,
        "duration": lambda p: p.duration or 0.0,
    }

    key_func = key_funcs.get(sort_key, key_funcs["duration"])
    return sorted(processes, key=key_func, reverse=reverse)
