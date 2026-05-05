"""Database connection and query management for PostgreSQL monitoring."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .types import (
    BlockingProcess,
    DurationMode,
    Filters,
    LockType,
    RunningProcess,
    WaitingProcess,
)


@dataclass
class ServerInfo:
    """PostgreSQL server statistics."""
    total: int = 0
    max_connections: int = 0
    active_connections: int = 0
    idle: int = 0
    idle_in_transaction: int = 0
    idle_in_transaction_aborted: int = 0
    waiting: int = 0
    total_size: int = 0
    size_evolution: int = 0
    tps: int = 0
    insert_per_second: int = 0
    update_per_second: int = 0
    delete_per_second: int = 0
    cache_hit_ratio_last_snap: float = 0.0
    rollback_ratio_last_snap: float = 0.0
    uptime: timedelta = field(default_factory=lambda: timedelta(0))
    max_dbname_length: int = 8
    # Worker process info
    worker_processes: int = 0
    max_worker_processes: int = 0
    logical_replication_workers: int = 0
    max_logical_replication_workers: int = 0
    parallel_workers: int = 0
    max_parallel_workers: int = 0
    autovacuum_workers: int = 0
    autovacuum_max_workers: int = 0
    wal_senders: int = 0
    max_wal_senders: int = 0
    wal_receivers: int = 0
    replication_slots: int = 0
    max_replication_slots: int = 0
    # Temp files
    temporary_file: TemporaryFileInfo | None = None


@dataclass
class TemporaryFileInfo:
    """Temporary file statistics."""
    temp_files: int = 0
    temp_bytes: int = 0


def parse_client_addr(
    value: str | None
) -> IPv4Address | IPv6Address | None:
    """Parse client address from PostgreSQL.

    >>> parse_client_addr("127.0.0.1")
    IPv4Address('127.0.0.1')
    >>> parse_client_addr("::1")
    IPv6Address('::1')
    >>> parse_client_addr(None)
    >>> parse_client_addr("")
    """
    if not value:
        return None
    try:
        return ip_address(value)
    except ValueError:
        return None


def parse_lock_type(value: str | None) -> LockType:
    """Parse lock type from PostgreSQL.

    >>> parse_lock_type("relation")
    <LockType.relation: 1>
    >>> parse_lock_type("transactionid")
    <LockType.transactionid: 5>
    >>> parse_lock_type(None)
    <LockType.relation: 1>
    """
    if value is None:
        return LockType.relation
    try:
        return LockType[value]
    except KeyError:
        return LockType.relation


class DatabaseManager:
    """Manages PostgreSQL database connections and queries.

    >>> # Example usage (requires actual database):
    >>> # manager = DatabaseManager.connect(host='localhost', database='postgres')
    >>> # version = manager.pg_version
    >>> # processes = manager.get_activities()
    """

    def __init__(self, conn: psycopg.Connection[dict[str, Any]], filters: Filters | None = None) -> None:
        self._conn = conn
        self._filters = filters or Filters()
        self._pg_version: str | None = None
        self._server_version: int | None = None
        self._prev_server_info: ServerInfo | None = None

    @classmethod
    def connect(
        cls,
        *,
        host: str | None = None,
        port: int | str | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        dsn: str = "",
        filters: Filters | None = None,
    ) -> DatabaseManager:
        """Connect to a PostgreSQL database.

        >>> # Requires actual PostgreSQL server
        >>> # manager = DatabaseManager.connect(host='localhost', database='postgres')
        """
        kwargs: dict[str, Any] = {}
        if host is not None:
            kwargs["host"] = host
        if port is not None:
            kwargs["port"] = int(port)
        if database is not None:
            kwargs["dbname"] = database
        if user is not None:
            kwargs["user"] = user
        if password is not None:
            kwargs["password"] = password

        conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row, **kwargs)
        return cls(conn, filters)

    @property
    def connection(self) -> psycopg.Connection[dict[str, Any]]:
        """Return the underlying connection."""
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @property
    def server_version(self) -> int:
        """Return the PostgreSQL server version as an integer."""
        if self._server_version is None:
            self._server_version = self._conn.info.server_version
        return self._server_version

    @property
    def pg_version(self) -> str:
        """Return the PostgreSQL version string."""
        if self._pg_version is None:
            result = self._execute_one("SELECT version() AS pg_version")
            self._pg_version = result["pg_version"]
        return self._pg_version

    def pg_is_local(self) -> bool:
        """Check if connected to a local PostgreSQL server."""
        host = self._conn.info.get_parameters().get("host", "")
        if not host or host == "localhost" or host.startswith("/"):
            return True
        if host in ("127.0.0.1", "::1"):
            return True
        return False

    def pg_is_local_access(self) -> bool:
        """Check if we have local filesystem access to PG data directory."""
        try:
            result = self._execute_one("SELECT setting FROM pg_settings WHERE name = 'data_directory'")
            import os
            return os.path.exists(result["setting"])
        except Exception:
            return False

    def _execute(self, query: str | sql.Composed, params: dict[str, Any] | None = None) -> None:
        """Execute a query without returning results."""
        with self._conn.cursor() as cur:
            cur.execute(query, params)

    def _execute_one(self, query: str | sql.Composed, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a query and return one row."""
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()
            if result is None:
                raise ValueError("Query returned no results")
            return result

    def _execute_all(self, query: str | sql.Composed, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a query and return all rows."""
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def _build_activity_query(self, duration_mode: DurationMode = DurationMode.query) -> str:
        """Build the query for pg_stat_activity based on server version."""
        version = self.server_version

        # Base duration calculation
        if duration_mode == DurationMode.query:
            if version >= 90200:
                duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - state_change))"
            else:
                duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - query_start))"
        elif duration_mode == DurationMode.transaction:
            duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - xact_start))"
        else:  # backend
            duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - backend_start))"

        # Wait column varies by version
        if version >= 90600:
            wait_col = "wait_event"
        else:
            wait_col = "waiting"

        # Query column
        if version >= 90200:
            query_col = "query"
        else:
            query_col = "current_query AS query"

        # Leader PID (pg 13+)
        if version >= 130000:
            leader_col = "leader_pid"
        else:
            leader_col = "NULL AS leader_pid"

        # Backend xmin (pg 9.4+)
        if version >= 90400:
            xmin_col = "backend_xmin"
        else:
            xmin_col = "NULL AS backend_xmin"

        # State column
        if version >= 90200:
            state_col = "state"
        else:
            state_col = "CASE WHEN current_query = '<IDLE>' THEN 'idle' ELSE 'active' END AS state"

        return f"""
            SELECT
                a.pid,
                {xmin_col} AS xmin,
                a.application_name,
                a.datname AS database,
                pg_encoding_to_char(d.encoding) AS encoding,
                a.usename AS user,
                a.client_addr::text AS client,
                {duration_col} AS duration,
                {state_col},
                {wait_col} AS wait,
                {query_col},
                {leader_col},
                COALESCE({leader_col}, a.pid) AS query_leader_pid,
                {leader_col} IS NOT NULL AS is_parallel_worker
            FROM pg_stat_activity a
            LEFT JOIN pg_database d ON a.datid = d.oid
            WHERE a.pid != pg_backend_pid()
              AND a.datname IS NOT NULL
              AND a.state != 'idle'
        """

    def get_activities(self, duration_mode: DurationMode = DurationMode.query) -> list[RunningProcess]:
        """Get running queries from pg_stat_activity."""
        query = self._build_activity_query(duration_mode)

        # Apply filters
        if self._filters.dbname:
            query += f" AND a.datname ~ %(dbname)s"

        rows = self._execute_all(query, {"dbname": self._filters.dbname} if self._filters.dbname else None)

        processes = []
        for row in rows:
            processes.append(RunningProcess(
                pid=row["pid"],
                application_name=row.get("application_name") or "",
                database=row.get("database"),
                user=row.get("user") or "",
                client=parse_client_addr(row.get("client")),
                duration=row.get("duration"),
                state=row.get("state") or "unknown",
                query=row.get("query"),
                wait=row.get("wait"),
                xmin=row.get("xmin") or 0,
                query_leader_pid=row.get("query_leader_pid"),
                is_parallel_worker=row.get("is_parallel_worker", False),
            ))

        return processes

    def _build_waiting_query(self, duration_mode: DurationMode = DurationMode.query) -> str:
        """Build query for waiting processes."""
        version = self.server_version

        # Duration calculation
        if duration_mode == DurationMode.query:
            if version >= 90200:
                duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - state_change))"
            else:
                duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - query_start))"
        elif duration_mode == DurationMode.transaction:
            duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - xact_start))"
        else:
            duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - backend_start))"

        if version >= 90600:
            return f"""
                SELECT
                    a.pid,
                    a.application_name,
                    a.datname AS database,
                    a.usename AS user,
                    a.client_addr::text AS client,
                    {duration_col} AS duration,
                    a.state,
                    a.query,
                    l.mode,
                    l.locktype AS type,
                    COALESCE(c.relname, '') AS relation,
                    COALESCE(a.leader_pid, a.pid) AS query_leader_pid,
                    a.leader_pid IS NOT NULL AS is_parallel_worker
                FROM pg_stat_activity a
                JOIN pg_locks l ON a.pid = l.pid AND NOT l.granted
                LEFT JOIN pg_class c ON l.relation = c.oid
                WHERE a.pid != pg_backend_pid()
                  AND a.datname IS NOT NULL
            """
        else:
            return f"""
                SELECT
                    a.pid,
                    a.application_name,
                    a.datname AS database,
                    a.usename AS user,
                    a.client_addr::text AS client,
                    {duration_col} AS duration,
                    a.state,
                    a.query,
                    l.mode,
                    l.locktype AS type,
                    COALESCE(c.relname, '') AS relation,
                    a.pid AS query_leader_pid,
                    FALSE AS is_parallel_worker
                FROM pg_stat_activity a
                JOIN pg_locks l ON a.pid = l.pid AND NOT l.granted
                LEFT JOIN pg_class c ON l.relation = c.oid
                WHERE a.pid != pg_backend_pid()
                  AND a.datname IS NOT NULL
            """

    def get_waiting(self, duration_mode: DurationMode = DurationMode.query) -> list[WaitingProcess]:
        """Get queries waiting for locks."""
        query = self._build_waiting_query(duration_mode)

        if self._filters.dbname:
            query += f" AND a.datname ~ %(dbname)s"

        rows = self._execute_all(query, {"dbname": self._filters.dbname} if self._filters.dbname else None)

        processes = []
        for row in rows:
            processes.append(WaitingProcess(
                pid=row["pid"],
                application_name=row.get("application_name") or "",
                database=row.get("database"),
                user=row.get("user") or "",
                client=parse_client_addr(row.get("client")),
                duration=row.get("duration"),
                state=row.get("state") or "unknown",
                query=row.get("query"),
                mode=row.get("mode") or "",
                type=parse_lock_type(row.get("type")),
                relation=row.get("relation") or "",
                query_leader_pid=row.get("query_leader_pid"),
                is_parallel_worker=row.get("is_parallel_worker", False),
            ))

        return processes

    def _build_blocking_query(self, duration_mode: DurationMode = DurationMode.query) -> str:
        """Build query for blocking processes."""
        version = self.server_version

        # Duration calculation
        if duration_mode == DurationMode.query:
            if version >= 90200:
                duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - state_change))"
            else:
                duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - query_start))"
        elif duration_mode == DurationMode.transaction:
            duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - xact_start))"
        else:
            duration_col = "EXTRACT(EPOCH FROM (clock_timestamp() - backend_start))"

        if version >= 90600:
            wait_col = "wait_event"
        else:
            wait_col = "waiting"

        if version >= 130000:
            leader_col = "COALESCE(a.leader_pid, a.pid)"
            is_parallel = "a.leader_pid IS NOT NULL"
        else:
            leader_col = "a.pid"
            is_parallel = "FALSE"

        return f"""
            SELECT DISTINCT
                a.pid,
                a.application_name,
                a.datname AS database,
                a.usename AS user,
                a.client_addr::text AS client,
                {duration_col} AS duration,
                a.state,
                a.query,
                l.mode,
                l.locktype AS type,
                COALESCE(c.relname, '') AS relation,
                {wait_col} AS wait,
                {leader_col} AS query_leader_pid,
                {is_parallel} AS is_parallel_worker
            FROM pg_stat_activity a
            JOIN pg_locks l ON a.pid = l.pid AND l.granted
            WHERE a.pid != pg_backend_pid()
              AND a.datname IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM pg_locks bl
                WHERE bl.pid != l.pid
                  AND NOT bl.granted
                  AND bl.locktype = l.locktype
                  AND (
                    (bl.locktype = 'transactionid' AND bl.transactionid = l.transactionid)
                    OR (bl.locktype = 'virtualxid' AND bl.virtualxid = l.virtualxid)
                    OR (bl.locktype = 'relation' AND bl.relation = l.relation)
                    OR (bl.locktype = 'tuple' AND bl.relation = l.relation AND bl.page = l.page AND bl.tuple = l.tuple)
                  )
              )
        """

    def get_blocking(self, duration_mode: DurationMode = DurationMode.query) -> list[BlockingProcess]:
        """Get queries blocking other queries."""
        query = self._build_blocking_query(duration_mode)

        if self._filters.dbname:
            query += f" AND a.datname ~ %(dbname)s"

        rows = self._execute_all(query, {"dbname": self._filters.dbname} if self._filters.dbname else None)

        processes = []
        for row in rows:
            processes.append(BlockingProcess(
                pid=row["pid"],
                application_name=row.get("application_name") or "",
                database=row.get("database"),
                user=row.get("user") or "",
                client=parse_client_addr(row.get("client")),
                duration=row.get("duration"),
                state=row.get("state") or "unknown",
                query=row.get("query"),
                mode=row.get("mode") or "",
                type=parse_lock_type(row.get("type")),
                relation=row.get("relation") or "",
                wait=row.get("wait"),
                query_leader_pid=row.get("query_leader_pid"),
                is_parallel_worker=row.get("is_parallel_worker", False),
            ))

        return processes

    def cancel_backend(self, pid: int) -> bool:
        """Cancel a backend query."""
        result = self._execute_one("SELECT pg_cancel_backend(%(pid)s) AS result", {"pid": pid})
        return result["result"]

    def terminate_backend(self, pid: int) -> bool:
        """Terminate a backend session."""
        result = self._execute_one("SELECT pg_terminate_backend(%(pid)s) AS result", {"pid": pid})
        return result["result"]

    def get_server_info(
        self,
        prev_server_info: ServerInfo | None = None,
        skip_db_size: bool = False,
    ) -> ServerInfo:
        """Get server statistics."""
        info = ServerInfo()

        # Basic connection stats
        stats = self._execute_one("""
            SELECT
                (SELECT count(*) FROM pg_stat_activity WHERE datname IS NOT NULL) AS total,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conn,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND pid != pg_backend_pid()) AS active,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction') AS idle_in_trans,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction (aborted)') AS idle_in_trans_aborted,
                (SELECT count(*) FROM pg_stat_activity WHERE wait_event IS NOT NULL AND state != 'idle') AS waiting,
                (SELECT max(length(datname)) FROM pg_database) AS max_dbname_len,
                (SELECT now() - pg_postmaster_start_time()) AS uptime
        """)

        info.total = stats.get("total") or 0
        info.max_connections = stats.get("max_conn") or 0
        info.active_connections = stats.get("active") or 0
        info.idle = stats.get("idle") or 0
        info.idle_in_transaction = stats.get("idle_in_trans") or 0
        info.idle_in_transaction_aborted = stats.get("idle_in_trans_aborted") or 0
        info.waiting = stats.get("waiting") or 0
        info.max_dbname_length = stats.get("max_dbname_len") or 8
        info.uptime = stats.get("uptime") or timedelta(0)

        # Database size
        if not skip_db_size:
            try:
                size_result = self._execute_one(
                    "SELECT sum(pg_database_size(datname)) AS total_size FROM pg_database"
                )
                info.total_size = size_result.get("total_size") or 0
                if prev_server_info and prev_server_info.total_size:
                    info.size_evolution = info.total_size - prev_server_info.total_size
            except Exception:
                info.total_size = 0

        # Worker processes
        try:
            worker_stats = self._execute_one("""
                SELECT
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_worker_processes') AS max_worker,
                    (SELECT setting::int FROM pg_settings WHERE name = 'autovacuum_max_workers') AS max_autovac,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_wal_senders') AS max_wal_send,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_replication_slots') AS max_repl_slots
            """)
            info.max_worker_processes = worker_stats.get("max_worker") or 0
            info.autovacuum_max_workers = worker_stats.get("max_autovac") or 0
            info.max_wal_senders = worker_stats.get("max_wal_send") or 0
            info.max_replication_slots = worker_stats.get("max_repl_slots") or 0
        except Exception:
            pass

        return info


# Type alias for backward compatibility
Data = DatabaseManager
