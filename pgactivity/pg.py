"""PostgreSQL connection wrapper module using psycopg."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

import psycopg
import psycopg.errors
import psycopg.rows
from psycopg import sql as sql

# Export version for conftest
__version__ = psycopg.__version__

# Type aliases
Connection = psycopg.Connection[Any]
T = TypeVar("T")

# Exception types
InterfaceError = psycopg.InterfaceError
OperationalError = psycopg.OperationalError
ProgrammingError = psycopg.ProgrammingError
InsufficientPrivilege = psycopg.errors.InsufficientPrivilege
QueryCanceled = psycopg.errors.QueryCanceled
FeatureNotSupported = psycopg.errors.FeatureNotSupported


def connect(
    dsn: str = "",
    *,
    host: str | None = None,
    port: int = 5432,
    user: str = "postgres",
    dbname: str = "postgres",
    password: str | None = None,
    application_name: str = "pg_activity",
    **kwargs: Any,
) -> Connection:
    """Connect to PostgreSQL database.

    >>> conn = connect(host="localhost", dbname="postgres")  # doctest: +SKIP
    """
    conninfo_parts = []
    if dsn:
        conninfo_parts.append(dsn)
    if host:
        conninfo_parts.append(f"host={host}")
    if port:
        conninfo_parts.append(f"port={port}")
    if user:
        conninfo_parts.append(f"user={user}")
    if dbname:
        conninfo_parts.append(f"dbname={dbname}")
    if password:
        conninfo_parts.append(f"password={password}")
    if application_name:
        conninfo_parts.append(f"application_name={application_name}")

    conninfo = " ".join(conninfo_parts)
    return psycopg.connect(conninfo, autocommit=True, **kwargs)


def execute(conn: Connection, query: str | sql.Composed) -> None:
    """Execute a query without returning results."""
    with conn.cursor() as cur:
        cur.execute(query)


def fetchone(
    conn: Connection,
    query: str | sql.Composed,
    params: dict[str, Any] | None = None,
    *,
    mkrow: Callable[..., T] | None = None,
    text_as_bytes: bool = False,
) -> T | dict[str, Any]:
    """Fetch one row from a query result.

    If mkrow is provided, it's called with the row data as keyword arguments.
    """
    with conn.cursor(binary=text_as_bytes, row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("No rows returned")
        if mkrow is not None:
            return mkrow(**row)
        return row


def fetchall(
    conn: Connection,
    query: str | sql.Composed,
    params: dict[str, Any] | None = None,
    *,
    mkrow: Callable[..., T] | None = None,
    text_as_bytes: bool = False,
) -> list[T] | list[dict[str, Any]]:
    """Fetch all rows from a query result.

    If mkrow is provided, it's called with each row's data as keyword arguments.
    """
    with conn.cursor(binary=text_as_bytes, row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        if mkrow is not None:
            return [mkrow(**row) for row in rows]
        return list(rows)


def server_version(conn: Connection) -> int:
    """Return the server version as an integer (e.g., 130000 for 13.0)."""
    return conn.info.server_version


def connection_parameters(conn: Connection) -> dict[str, str]:
    """Return connection parameters as a dictionary."""
    params = conn.info.get_parameters()
    result = {}
    if params.get("host"):
        result["host"] = params["host"]
    if params.get("port"):
        result["port"] = int(params["port"])
    if params.get("user"):
        result["user"] = params["user"]
    if params.get("dbname"):
        result["dbname"] = params["dbname"]
    if params.get("password"):
        result["password"] = params["password"]
    if params.get("application_name"):
        result["application_name"] = params["application_name"]
    return result


def needs_password(err: OperationalError) -> bool:
    """Check if an OperationalError indicates that a password is required."""
    err_str = str(err).lower()
    return "password" in err_str or "authentication" in err_str
