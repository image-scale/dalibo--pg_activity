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
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("No rows returned")
        if text_as_bytes and mkrow is not None:
            # Convert text fields to bytes if needed
            row = {k: v.encode() if isinstance(v, str) else v for k, v in row.items()}
        elif not text_as_bytes:
            # Ensure text fields are strings, not bytes
            row = {
                k: v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v
                for k, v in row.items()
            }
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
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        if text_as_bytes and mkrow is not None:
            # Convert text fields to bytes if needed
            rows = [
                {k: v.encode() if isinstance(v, str) else v for k, v in row.items()}
                for row in rows
            ]
        elif not text_as_bytes:
            # Ensure text fields are strings, not bytes
            rows = [
                {
                    k: v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v
                    for k, v in row.items()
                }
                for row in rows
            ]
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


def decode(value: bytes, encoding: bytes | str, errors: str = "strict") -> str:
    """Decode bytes to string using the specified encoding.

    >>> decode(b'hello', b'utf-8')
    'hello'
    >>> decode(b'hello', 'utf-8')
    'hello'
    >>> decode(b'hello', 'SQL_ASCII')
    'hello'
    """
    if isinstance(encoding, bytes):
        encoding = encoding.decode("ascii")

    # Map PostgreSQL encoding names to Python encoding names
    pg_to_python = {
        "SQL_ASCII": "ascii",
        "UTF8": "utf-8",
        "LATIN1": "iso-8859-1",
        "LATIN2": "iso-8859-2",
        "LATIN3": "iso-8859-3",
        "LATIN4": "iso-8859-4",
        "LATIN5": "iso-8859-9",
        "LATIN6": "iso-8859-10",
        "LATIN7": "iso-8859-13",
        "LATIN8": "iso-8859-14",
        "LATIN9": "iso-8859-15",
        "LATIN10": "iso-8859-16",
        "EUC_JP": "euc-jp",
        "EUC_CN": "euc-cn",
        "EUC_KR": "euc-kr",
        "EUC_TW": "big5",  # EUC_TW is similar to Big5
        "SJIS": "shift-jis",
        "BIG5": "big5",
        "GBK": "gbk",
        "GB18030": "gb18030",
        "UHC": "cp949",
        "JOHAB": "johab",
        "WIN1250": "cp1250",
        "WIN1251": "cp1251",
        "WIN1252": "cp1252",
        "WIN1253": "cp1253",
        "WIN1254": "cp1254",
        "WIN1255": "cp1255",
        "WIN1256": "cp1256",
        "WIN1257": "cp1257",
        "WIN1258": "cp1258",
        "WIN866": "cp866",
        "WIN874": "cp874",
        "KOI8R": "koi8-r",
        "KOI8U": "koi8-u",
        "ISO_8859_5": "iso-8859-5",
        "ISO_8859_6": "iso-8859-6",
        "ISO_8859_7": "iso-8859-7",
        "ISO_8859_8": "iso-8859-8",
    }

    encoding_upper = encoding.upper()
    python_encoding = pg_to_python.get(encoding_upper, encoding)

    try:
        return value.decode(python_encoding, errors=errors)
    except LookupError:
        # If still unknown, try with ascii as fallback
        return value.decode("ascii", errors=errors)
