"""Tests for database connection and query module."""

from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from pgmonitor.data import (
    DatabaseManager,
    ServerInfo,
    TemporaryFileInfo,
    parse_client_addr,
    parse_lock_type,
)
from pgmonitor.types import (
    DurationMode,
    Filters,
    LockType,
    RunningProcess,
    WaitingProcess,
    BlockingProcess,
)


class TestParseClientAddr:
    """Tests for parse_client_addr function."""

    def test_ipv4_address(self):
        """Parse IPv4 address."""
        result = parse_client_addr("127.0.0.1")
        assert result == IPv4Address("127.0.0.1")

    def test_ipv6_address(self):
        """Parse IPv6 address."""
        result = parse_client_addr("::1")
        assert result == IPv6Address("::1")

    def test_none_returns_none(self):
        """None returns None."""
        assert parse_client_addr(None) is None

    def test_empty_returns_none(self):
        """Empty string returns None."""
        assert parse_client_addr("") is None

    def test_invalid_returns_none(self):
        """Invalid address returns None."""
        assert parse_client_addr("not_an_ip") is None


class TestParseLockType:
    """Tests for parse_lock_type function."""

    def test_valid_lock_type(self):
        """Parse valid lock type."""
        assert parse_lock_type("relation") == LockType.relation
        assert parse_lock_type("transactionid") == LockType.transactionid
        assert parse_lock_type("tuple") == LockType.tuple

    def test_none_returns_default(self):
        """None returns default (relation)."""
        assert parse_lock_type(None) == LockType.relation

    def test_invalid_returns_default(self):
        """Invalid type returns default (relation)."""
        assert parse_lock_type("invalid_type") == LockType.relation


class TestServerInfo:
    """Tests for ServerInfo class."""

    def test_default_values(self):
        """Default values are sensible."""
        info = ServerInfo()
        assert info.total == 0
        assert info.max_connections == 0
        assert info.active_connections == 0
        assert info.tps == 0
        assert info.cache_hit_ratio_last_snap == 0.0

    def test_custom_values(self):
        """Custom values are stored."""
        info = ServerInfo(
            total=10,
            max_connections=100,
            active_connections=5,
            uptime=timedelta(days=1),
        )
        assert info.total == 10
        assert info.max_connections == 100
        assert info.active_connections == 5
        assert info.uptime == timedelta(days=1)


class TestTemporaryFileInfo:
    """Tests for TemporaryFileInfo class."""

    def test_default_values(self):
        """Default values are zero."""
        info = TemporaryFileInfo()
        assert info.temp_files == 0
        assert info.temp_bytes == 0

    def test_custom_values(self):
        """Custom values are stored."""
        info = TemporaryFileInfo(temp_files=5, temp_bytes=1024)
        assert info.temp_files == 5
        assert info.temp_bytes == 1024


class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection."""
        conn = MagicMock()
        conn.info.server_version = 150000  # PostgreSQL 15
        conn.info.get_parameters.return_value = {"host": "localhost"}
        return conn

    @pytest.fixture
    def manager(self, mock_conn):
        """Create a DatabaseManager with mock connection."""
        return DatabaseManager(mock_conn)

    def test_connection_property(self, manager, mock_conn):
        """connection property returns the connection."""
        assert manager.connection is mock_conn

    def test_close(self, manager, mock_conn):
        """close() closes the connection."""
        manager.close()
        mock_conn.close.assert_called_once()

    def test_server_version(self, manager):
        """server_version returns version from connection info."""
        assert manager.server_version == 150000

    def test_pg_version(self, manager, mock_conn):
        """pg_version queries and caches the version string."""
        cursor = MagicMock()
        cursor.fetchone.return_value = {"pg_version": "PostgreSQL 15.0"}
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        version = manager.pg_version
        assert version == "PostgreSQL 15.0"

        # Second call should use cached value
        version2 = manager.pg_version
        assert version2 == "PostgreSQL 15.0"
        # Only one query should be made
        assert cursor.execute.call_count == 1

    def test_pg_is_local_localhost(self, manager, mock_conn):
        """pg_is_local returns True for localhost."""
        mock_conn.info.get_parameters.return_value = {"host": "localhost"}
        assert manager.pg_is_local() is True

    def test_pg_is_local_loopback(self, manager, mock_conn):
        """pg_is_local returns True for loopback."""
        mock_conn.info.get_parameters.return_value = {"host": "127.0.0.1"}
        assert manager.pg_is_local() is True

    def test_pg_is_local_socket(self, manager, mock_conn):
        """pg_is_local returns True for Unix socket."""
        mock_conn.info.get_parameters.return_value = {"host": "/var/run/postgresql"}
        assert manager.pg_is_local() is True

    def test_pg_is_local_remote(self, manager, mock_conn):
        """pg_is_local returns False for remote host."""
        mock_conn.info.get_parameters.return_value = {"host": "192.168.1.100"}
        assert manager.pg_is_local() is False


class TestDatabaseManagerQueries:
    """Tests for DatabaseManager query methods."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection."""
        conn = MagicMock()
        conn.info.server_version = 150000
        conn.info.get_parameters.return_value = {"host": "localhost"}
        return conn

    @pytest.fixture
    def manager(self, mock_conn):
        """Create a DatabaseManager with mock connection."""
        return DatabaseManager(mock_conn)

    def test_get_activities_returns_running_processes(self, manager, mock_conn):
        """get_activities returns list of RunningProcess."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "pid": 123,
                "application_name": "pgbench",
                "database": "testdb",
                "user": "postgres",
                "client": "127.0.0.1",
                "duration": 1.5,
                "state": "active",
                "query": "SELECT 1",
                "wait": None,
                "xmin": 1000,
                "query_leader_pid": 123,
                "is_parallel_worker": False,
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        processes = manager.get_activities()

        assert len(processes) == 1
        assert isinstance(processes[0], RunningProcess)
        assert processes[0].pid == 123
        assert processes[0].database == "testdb"
        assert processes[0].state == "active"

    def test_get_activities_with_filter(self, mock_conn):
        """get_activities applies database filter."""
        manager = DatabaseManager(mock_conn, filters=Filters(dbname="test.*"))
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        manager.get_activities()

        # Check that the filter was passed to execute
        call_args = cursor.execute.call_args
        params = call_args[0][1]  # Second argument is params
        assert params == {"dbname": "test.*"}

    def test_get_waiting_returns_waiting_processes(self, manager, mock_conn):
        """get_waiting returns list of WaitingProcess."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "pid": 456,
                "application_name": "app",
                "database": "testdb",
                "user": "postgres",
                "client": None,
                "duration": 2.0,
                "state": "active",
                "query": "UPDATE t SET x=1",
                "mode": "ExclusiveLock",
                "type": "relation",
                "relation": "public.t",
                "query_leader_pid": 456,
                "is_parallel_worker": False,
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        processes = manager.get_waiting()

        assert len(processes) == 1
        assert isinstance(processes[0], WaitingProcess)
        assert processes[0].pid == 456
        assert processes[0].mode == "ExclusiveLock"
        assert processes[0].type == LockType.relation

    def test_get_blocking_returns_blocking_processes(self, manager, mock_conn):
        """get_blocking returns list of BlockingProcess."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "pid": 789,
                "application_name": "app",
                "database": "testdb",
                "user": "postgres",
                "client": "::1",
                "duration": 10.0,
                "state": "active",
                "query": "UPDATE t SET x=1",
                "mode": "AccessExclusiveLock",
                "type": "relation",
                "relation": "public.t",
                "wait": "ClientRead",
                "query_leader_pid": 789,
                "is_parallel_worker": False,
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        processes = manager.get_blocking()

        assert len(processes) == 1
        assert isinstance(processes[0], BlockingProcess)
        assert processes[0].pid == 789
        assert processes[0].wait == "ClientRead"


class TestDatabaseManagerActions:
    """Tests for DatabaseManager action methods."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection."""
        conn = MagicMock()
        conn.info.server_version = 150000
        return conn

    @pytest.fixture
    def manager(self, mock_conn):
        """Create a DatabaseManager with mock connection."""
        return DatabaseManager(mock_conn)

    def test_cancel_backend_success(self, manager, mock_conn):
        """cancel_backend returns True on success."""
        cursor = MagicMock()
        cursor.fetchone.return_value = {"result": True}
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        result = manager.cancel_backend(123)
        assert result is True

    def test_cancel_backend_failure(self, manager, mock_conn):
        """cancel_backend returns False on failure."""
        cursor = MagicMock()
        cursor.fetchone.return_value = {"result": False}
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        result = manager.cancel_backend(999)
        assert result is False

    def test_terminate_backend_success(self, manager, mock_conn):
        """terminate_backend returns True on success."""
        cursor = MagicMock()
        cursor.fetchone.return_value = {"result": True}
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        result = manager.terminate_backend(123)
        assert result is True

    def test_terminate_backend_failure(self, manager, mock_conn):
        """terminate_backend returns False on failure."""
        cursor = MagicMock()
        cursor.fetchone.return_value = {"result": False}
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        result = manager.terminate_backend(999)
        assert result is False


class TestDatabaseManagerServerInfo:
    """Tests for DatabaseManager.get_server_info method."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection."""
        conn = MagicMock()
        conn.info.server_version = 150000
        return conn

    @pytest.fixture
    def manager(self, mock_conn):
        """Create a DatabaseManager with mock connection."""
        return DatabaseManager(mock_conn)

    def test_get_server_info(self, manager, mock_conn):
        """get_server_info returns populated ServerInfo."""
        cursor = MagicMock()
        # First call - basic stats
        cursor.fetchone.side_effect = [
            {
                "total": 10,
                "max_conn": 100,
                "active": 5,
                "idle": 3,
                "idle_in_trans": 1,
                "idle_in_trans_aborted": 0,
                "waiting": 2,
                "max_dbname_len": 12,
                "uptime": timedelta(hours=5),
            },
            {"total_size": 1024000},
            {
                "max_worker": 8,
                "max_autovac": 3,
                "max_wal_send": 10,
                "max_repl_slots": 10,
            },
        ]
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        info = manager.get_server_info()

        assert info.total == 10
        assert info.max_connections == 100
        assert info.active_connections == 5
        assert info.idle == 3
        assert info.max_dbname_length == 12
        assert info.uptime == timedelta(hours=5)

    def test_get_server_info_skip_db_size(self, manager, mock_conn):
        """get_server_info can skip database size query."""
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {
                "total": 5,
                "max_conn": 50,
                "active": 2,
                "idle": 2,
                "idle_in_trans": 0,
                "idle_in_trans_aborted": 0,
                "waiting": 1,
                "max_dbname_len": 10,
                "uptime": timedelta(minutes=30),
            },
            {
                "max_worker": 8,
                "max_autovac": 3,
                "max_wal_send": 10,
                "max_repl_slots": 10,
            },
        ]
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        info = manager.get_server_info(skip_db_size=True)

        assert info.total == 5
        assert info.total_size == 0  # Skipped


class TestBuildActivityQuery:
    """Tests for query building with different duration modes."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection."""
        conn = MagicMock()
        conn.info.server_version = 150000
        return conn

    @pytest.fixture
    def manager(self, mock_conn):
        """Create a DatabaseManager with mock connection."""
        return DatabaseManager(mock_conn)

    def test_query_mode(self, manager):
        """Query mode uses state_change for duration."""
        query = manager._build_activity_query(DurationMode.query)
        assert "state_change" in query

    def test_transaction_mode(self, manager):
        """Transaction mode uses xact_start for duration."""
        query = manager._build_activity_query(DurationMode.transaction)
        assert "xact_start" in query

    def test_backend_mode(self, manager):
        """Backend mode uses backend_start for duration."""
        query = manager._build_activity_query(DurationMode.backend)
        assert "backend_start" in query
