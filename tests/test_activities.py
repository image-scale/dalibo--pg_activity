"""Tests for system monitoring activities module."""

from collections import namedtuple
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from pgmonitor.activities import (
    mem_swap_load,
    sys_get_proc,
    ps_complete,
    get_fs_blocksize,
    get_system_info,
    sort_processes,
)
from pgmonitor.types import (
    IOCounter,
    LoadAverage,
    LocalRunningProcess,
    MemoryInfo,
    RunningProcess,
    SwapInfo,
    SystemInfo,
    SystemProcess,
)


class TestMemSwapLoad:
    """Tests for mem_swap_load function."""

    def test_returns_correct_types(self):
        """mem_swap_load returns correct types."""
        with patch("psutil.virtual_memory") as mock_vmem, \
             patch("psutil.swap_memory") as mock_swap, \
             patch("os.getloadavg") as mock_load:

            # Mock virtual memory
            vmem = MagicMock()
            vmem.total = 8000000000
            vmem.free = 2000000000
            vmem.buffers = 500000000
            vmem.cached = 1500000000
            mock_vmem.return_value = vmem

            # Mock swap memory
            smem = MagicMock()
            smem.total = 4000000000
            smem.used = 1000000000
            smem.free = 3000000000
            mock_swap.return_value = smem

            # Mock load average
            mock_load.return_value = (0.5, 1.0, 1.5)

            memory, swap, load = mem_swap_load()

            assert isinstance(memory, MemoryInfo)
            assert isinstance(swap, SwapInfo)
            assert isinstance(load, LoadAverage)

    def test_memory_values(self):
        """mem_swap_load returns correct memory values."""
        with patch("psutil.virtual_memory") as mock_vmem, \
             patch("psutil.swap_memory") as mock_swap, \
             patch("os.getloadavg") as mock_load:

            vmem = MagicMock()
            vmem.total = 8000
            vmem.free = 2000
            vmem.buffers = 500
            vmem.cached = 1500
            mock_vmem.return_value = vmem

            smem = MagicMock()
            smem.total = 4000
            smem.used = 1000
            smem.free = 3000
            mock_swap.return_value = smem

            mock_load.return_value = (0.5, 1.0, 1.5)

            memory, swap, load = mem_swap_load()

            # used = total - free - buffers - cached = 8000 - 2000 - 500 - 1500 = 4000
            assert memory.used == 4000
            assert memory.buff_cached == 2000  # buffers + cached
            assert memory.free == 2000
            assert memory.total == 8000

    def test_swap_values(self):
        """mem_swap_load returns correct swap values."""
        with patch("psutil.virtual_memory") as mock_vmem, \
             patch("psutil.swap_memory") as mock_swap, \
             patch("os.getloadavg") as mock_load:

            vmem = MagicMock()
            vmem.total = 8000
            vmem.free = 2000
            vmem.buffers = 0
            vmem.cached = 0
            mock_vmem.return_value = vmem

            smem = MagicMock()
            smem.total = 4000
            smem.used = 1000
            smem.free = 3000
            mock_swap.return_value = smem

            mock_load.return_value = (0.5, 1.0, 1.5)

            memory, swap, load = mem_swap_load()

            assert swap.used == 1000
            assert swap.free == 3000
            assert swap.total == 4000

    def test_load_values(self):
        """mem_swap_load returns correct load values."""
        with patch("psutil.virtual_memory") as mock_vmem, \
             patch("psutil.swap_memory") as mock_swap, \
             patch("os.getloadavg") as mock_load:

            vmem = MagicMock()
            vmem.total = 8000
            vmem.free = 2000
            vmem.buffers = 0
            vmem.cached = 0
            mock_vmem.return_value = vmem

            smem = MagicMock()
            smem.total = 4000
            smem.used = 1000
            smem.free = 3000
            mock_swap.return_value = smem

            mock_load.return_value = (1.5, 2.5, 3.5)

            memory, swap, load = mem_swap_load()

            assert load.avg1 == 1.5
            assert load.avg5 == 2.5
            assert load.avg15 == 3.5


class TestSysGetProc:
    """Tests for sys_get_proc function."""

    def test_returns_system_process(self):
        """sys_get_proc returns SystemProcess for valid PID."""
        with patch("psutil.Process") as mock_proc_class:
            mock_proc = MagicMock()
            mock_proc_class.return_value = mock_proc

            mock_proc.cpu_percent.return_value = 5.0
            mock_proc.memory_percent.return_value = 2.5

            meminfo = MagicMock()
            meminfo.rss = 1000000
            meminfo.vms = 2000000
            mock_proc.memory_info.return_value = meminfo

            cpu_times = MagicMock()
            cpu_times.user = 1.0
            cpu_times.system = 0.5
            cpu_times.iowait = 0.1
            mock_proc.cpu_times.return_value = cpu_times

            io_counters = MagicMock()
            io_counters.read_count = 100
            io_counters.read_bytes = 1024
            io_counters.write_count = 50
            io_counters.write_bytes = 512
            mock_proc.io_counters.return_value = io_counters

            mock_proc.oneshot.return_value.__enter__ = MagicMock()
            mock_proc.oneshot.return_value.__exit__ = MagicMock()

            result = sys_get_proc(123)

            assert result is not None
            assert isinstance(result, SystemProcess)
            assert result.cpu_percent == 5.0
            assert result.mem_percent == 2.5

    def test_returns_none_for_missing_process(self):
        """sys_get_proc returns None for non-existent PID."""
        import psutil as real_psutil

        with patch("psutil.Process") as mock_proc_class:
            mock_proc_class.side_effect = real_psutil.NoSuchProcess(99999)

            result = sys_get_proc(99999)
            assert result is None

    def test_handles_access_denied(self):
        """sys_get_proc returns None for access denied."""
        import psutil as real_psutil

        with patch("psutil.Process") as mock_proc_class:
            mock_proc_class.side_effect = real_psutil.AccessDenied(1)

            result = sys_get_proc(1)
            assert result is None


class TestPsComplete:
    """Tests for ps_complete function."""

    @pytest.fixture
    def sample_process(self):
        """Create a sample RunningProcess."""
        return RunningProcess(
            pid=1234,
            application_name="pgbench",
            database="testdb",
            user="postgres",
            client=None,
            duration=1.5,
            state="active",
            query="SELECT 1",
            wait=False,
        )

    def test_empty_list(self):
        """ps_complete with empty list returns empty list."""
        procs, io_r, io_w = ps_complete([], {})
        assert procs == []
        assert io_r == IOCounter.default()
        assert io_w == IOCounter.default()

    def test_enriches_process(self, sample_process):
        """ps_complete enriches process with metrics."""
        with patch("pgmonitor.activities.sys_get_proc") as mock_get:
            mock_get.return_value = SystemProcess(
                meminfo=(1000, 2000),
                io_read=IOCounter(10, 1024),
                io_write=IOCounter(5, 512),
                io_time=0.1,
                mem_percent=2.5,
                cpu_percent=5.0,
                cpu_times=(1.0, 0.5),
                read_delta=0.0,
                write_delta=0.0,
                io_wait=False,
            )

            procs, io_r, io_w = ps_complete([sample_process], {})

            assert len(procs) == 1
            assert isinstance(procs[0], LocalRunningProcess)
            assert procs[0].cpu == 5.0
            assert procs[0].mem == 2.5

    def test_skips_missing_process(self, sample_process):
        """ps_complete skips processes that no longer exist."""
        with patch("pgmonitor.activities.sys_get_proc") as mock_get:
            mock_get.return_value = None

            procs, io_r, io_w = ps_complete([sample_process], {})

            assert len(procs) == 0

    def test_computes_io_deltas(self, sample_process):
        """ps_complete computes I/O deltas from previous values."""
        prev_sys_proc = SystemProcess(
            meminfo=(1000, 2000),
            io_read=IOCounter(8, 512),
            io_write=IOCounter(4, 256),
            io_time=0.05,
            mem_percent=2.0,
            cpu_percent=4.0,
            cpu_times=(0.9, 0.4),
            read_delta=0.0,
            write_delta=0.0,
            io_wait=False,
        )

        with patch("pgmonitor.activities.sys_get_proc") as mock_get:
            mock_get.return_value = SystemProcess(
                meminfo=(1000, 2000),
                io_read=IOCounter(10, 1024),
                io_write=IOCounter(5, 512),
                io_time=0.1,
                mem_percent=2.5,
                cpu_percent=5.0,
                cpu_times=(1.0, 0.5),
                read_delta=0.0,
                write_delta=0.0,
                io_wait=False,
            )

            system_procs = {sample_process.pid: prev_sys_proc}
            procs, io_r, io_w = ps_complete([sample_process], system_procs, refresh_interval=2.0)

            assert len(procs) == 1
            # Read delta: (1024 - 512) / 2.0 = 256 bytes/sec
            assert procs[0].read == 256.0
            # Write delta: (512 - 256) / 2.0 = 128 bytes/sec
            assert procs[0].write == 128.0


class TestGetFsBlocksize:
    """Tests for get_fs_blocksize function."""

    def test_returns_positive_value(self):
        """get_fs_blocksize returns a positive value."""
        blocksize = get_fs_blocksize()
        assert blocksize > 0

    def test_handles_error(self):
        """get_fs_blocksize returns default on error."""
        with patch("os.statvfs") as mock_statvfs:
            mock_statvfs.side_effect = OSError("Not supported")
            blocksize = get_fs_blocksize()
            assert blocksize == 512


class TestGetSystemInfo:
    """Tests for get_system_info function."""

    def test_returns_system_info(self):
        """get_system_info returns SystemInfo."""
        with patch("pgmonitor.activities.mem_swap_load") as mock_msl:
            mock_msl.return_value = (
                MemoryInfo(1000, 500, 500, 2000),
                SwapInfo(200, 800, 1000),
                LoadAverage(0.5, 1.0, 1.5),
            )

            info = get_system_info()

            assert isinstance(info, SystemInfo)
            assert info.memory.total == 2000
            assert info.swap.total == 1000
            assert info.load.avg1 == 0.5


class TestSortProcesses:
    """Tests for sort_processes function."""

    @pytest.fixture
    def sample_processes(self):
        """Create sample processes for sorting."""
        base = dict(
            application_name="app",
            database="db",
            user="user",
            client=None,
            state="active",
            query="SELECT 1",
            wait=False,
        )
        return [
            LocalRunningProcess(pid=1, duration=1.0, cpu=10.0, mem=5.0, read=100.0, write=50.0, **base),
            LocalRunningProcess(pid=2, duration=3.0, cpu=5.0, mem=10.0, read=50.0, write=100.0, **base),
            LocalRunningProcess(pid=3, duration=2.0, cpu=15.0, mem=2.0, read=200.0, write=25.0, **base),
        ]

    def test_sort_by_cpu(self, sample_processes):
        """sort_processes sorts by CPU correctly."""
        sorted_procs = sort_processes(sample_processes, "cpu")
        cpus = [p.cpu for p in sorted_procs]
        assert cpus == [15.0, 10.0, 5.0]  # Descending

    def test_sort_by_mem(self, sample_processes):
        """sort_processes sorts by memory correctly."""
        sorted_procs = sort_processes(sample_processes, "mem")
        mems = [p.mem for p in sorted_procs]
        assert mems == [10.0, 5.0, 2.0]  # Descending

    def test_sort_by_duration(self, sample_processes):
        """sort_processes sorts by duration correctly."""
        sorted_procs = sort_processes(sample_processes, "duration")
        durations = [p.duration for p in sorted_procs]
        assert durations == [3.0, 2.0, 1.0]  # Descending

    def test_sort_by_read(self, sample_processes):
        """sort_processes sorts by read correctly."""
        sorted_procs = sort_processes(sample_processes, "read")
        reads = [p.read for p in sorted_procs]
        assert reads == [200.0, 100.0, 50.0]  # Descending

    def test_sort_by_write(self, sample_processes):
        """sort_processes sorts by write correctly."""
        sorted_procs = sort_processes(sample_processes, "write")
        writes = [p.write for p in sorted_procs]
        assert writes == [100.0, 50.0, 25.0]  # Descending

    def test_empty_list(self):
        """sort_processes handles empty list."""
        sorted_procs = sort_processes([], "cpu")
        assert sorted_procs == []
