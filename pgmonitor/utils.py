"""Utility functions for formatting and display."""

from __future__ import annotations

import base64
import functools
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import IO, Any

import humanize


# Natural size formatting using humanize
naturalsize = functools.partial(humanize.naturalsize, gnu=True, format="%.2f")


def format_duration(duration: float | None) -> tuple[str, str]:
    """Format duration for display with appropriate color.

    Returns a tuple of (formatted_string, color_name).

    >>> format_duration(None)
    ('N/A     ', 'green')
    >>> format_duration(-0.001)
    ('0.000000', 'green')
    >>> format_duration(0.123456)
    ('0.123456', 'green')
    >>> format_duration(1.5)
    ('00:01.50', 'yellow')
    >>> format_duration(5.0)
    ('00:05.00', 'red')
    >>> format_duration(125.5)
    ('02:05.50', 'red')
    >>> format_duration(65000)
    ('18 h', 'red')
    """
    if duration is None:
        return "N/A".ljust(8), "green"

    if duration < 1:
        if duration < 0:
            duration = 0
        return f"{duration:.6f}", "green"
    elif duration < 60000:
        if duration < 3:
            color = "yellow"
        else:
            color = "red"
        td = timedelta(seconds=float(duration))
        minutes = td.seconds // 60
        seconds = td.seconds % 60
        microseconds = td.microseconds
        # Format as mm:ss.ff (hundredths)
        return f"{minutes:02d}:{seconds:02d}.{microseconds // 10000:02d}", color
    else:
        hours = int(duration / 3600)
        return f"{hours} h", "red"


def yn(value: bool) -> str:
    """Convert boolean to Y or N string.

    >>> yn(True)
    'Y'
    >>> yn(False)
    'N'
    """
    return "Y" if value else "N"


def clean_str(text: str) -> str:
    """Clean a string by removing newlines, collapsing whitespace, and trimming.

    >>> clean_str("\\n")
    ''
    >>> clean_str("  hello   world  ")
    'hello world'
    >>> clean_str("line1\\nline2\\tline3")
    'line1 line2 line3'
    >>> clean_str("a  b   c    d")
    'a b c d'
    """
    # Replace newlines with spaces
    text = text.replace("\n", " ")
    # Collapse multiple whitespace to single space
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text


def ellipsis(text: str, width: int) -> str:
    """Shorten text to width with ellipsis in the middle if needed.

    >>> ellipsis("short", 10)
    'short'
    >>> ellipsis("longerthanwidth", 7)
    'lo...th'
    >>> ellipsis("verylongtext", 8)
    've...xt'
    """
    if len(text) <= width:
        return text
    if width < 5:
        return text[:width]
    # Calculate how many chars on each side
    # left_len + 3 + right_len = width
    remaining = width - 3
    left_len = remaining // 2
    right_len = remaining - left_len
    return text[:left_len] + "..." + text[-right_len:]


def short_state(state: str) -> str:
    """Return abbreviated state string.

    >>> short_state("active")
    'active'
    >>> short_state("idle in transaction")
    'idle in trans'
    >>> short_state("idle in transaction (aborted)")
    'idle in trans (a)'
    """
    abbreviations = {
        "idle in transaction": "idle in trans",
        "idle in transaction (aborted)": "idle in trans (a)",
    }
    return abbreviations.get(state, state)


def wait_status(value: None | bool | str) -> str:
    """Format wait status for display.

    >>> wait_status(None)
    ''
    >>> wait_status(True)
    'Y'
    >>> wait_status(False)
    'N'
    >>> wait_status("ClientRead")
    'ClientRead'
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return yn(value)
    return str(value)


def get_duration(duration: float | None) -> float:
    """Return 0 if duration is None or negative, else return the duration.

    >>> get_duration(None)
    0
    >>> get_duration(-5)
    0
    >>> get_duration(10.5)
    10.5
    """
    if duration is None or duration < 0:
        return 0
    return float(duration)


@dataclass
class MessagePile:
    """A pile of messages that returns the same message N times.

    >>> pile = MessagePile(n=2)
    >>> pile.send("hello")
    >>> pile.get()
    'hello'
    >>> pile.get()
    'hello'
    >>> pile.get()
    >>> pile.send("world")
    >>> pile.get()
    'world'
    """
    n: int
    _messages: list[str] = field(default_factory=list, init=False)

    def send(self, message: str) -> None:
        """Send a message to be returned n times."""
        self._messages[:] = [message] * self.n

    def get(self) -> str | None:
        """Get the next message or None if exhausted."""
        if self._messages:
            return self._messages.pop()
        return None


def osc52_copy(text: str) -> None:
    """Copy text to clipboard using OSC 52 escape sequence."""
    if sys.__stderr__ is not None:
        buffer = sys.__stderr__.buffer
        encoded = base64.b64encode(text.encode())
        buffer.write(b"\033]52;c;" + encoded + b"\a")
        buffer.flush()


def csv_write(
    fobj: IO[str],
    procs: Iterable[Mapping[str, Any]],
    *,
    delimiter: str = ";",
) -> None:
    """Write processes to CSV file.

    >>> import tempfile
    >>> procs = [
    ...     {'pid': 123, 'database': 'testdb', 'user': 'postgres', 'query': 'SELECT 1',
    ...      'state': 'active', 'duration': 1.5, 'wait': False, 'cpu': 5.0, 'mem': 2.0,
    ...      'read': 1024, 'write': 512, 'io_wait': False, 'application_name': 'app',
    ...      'xmin': 100, 'client': 'local'},
    ... ]
    >>> with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv') as f:
    ...     csv_write(f, procs)
    ...     _ = f.seek(0)
    ...     lines = f.readlines()
    >>> 'datetimeutc' in lines[0]
    True
    >>> '123' in lines[1]
    True
    """
    def clean_csv(s: str) -> str:
        return clean_str(s).replace('"', '\\"')

    # Write header if at beginning of file
    if fobj.tell() == 0:
        headers = [
            "datetimeutc", "pid", "xmin", "database", "appname", "user",
            "client", "cpu", "memory", "read", "write", "duration",
            "wait", "io_wait", "state", "query"
        ]
        fobj.write(delimiter.join(headers) + "\n")

    def yn_or_na(value: bool | None) -> str:
        if value is None:
            return "N/A"
        return yn(value)

    for p in procs:
        dt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        pid = p.get("pid", "N/A")
        xmin = p.get("xmin", "N/A")
        database = p.get("database", "N/A") or ""
        appname = p.get("application_name", "N/A")
        user = p.get("user", "N/A")
        client = p.get("client", "N/A")
        cpu = p.get("cpu", "N/A")
        mem = p.get("mem", "N/A")
        read_val = p.get("read", "N/A")
        write_val = p.get("write", "N/A")
        duration = p.get("duration", "N/A")
        wait = yn_or_na(p.get("wait"))
        io_wait = yn_or_na(p.get("io_wait"))
        state = p.get("state", "N/A")
        query = clean_csv(str(p.get("query", "N/A") or ""))

        values = [
            f'"{dt}"', f'"{pid}"', f'"{xmin}"', f'"{database}"',
            f'"{appname}"', f'"{user}"', f'"{client}"', f'"{cpu}"',
            f'"{mem}"', f'"{read_val}"', f'"{write_val}"', f'"{duration}"',
            f'"{wait}"', f'"{io_wait}"', f'"{state}"', f'"{query}"'
        ]
        fobj.write(delimiter.join(values) + "\n")


def naturaltimedelta(d: timedelta) -> str:
    """Format timedelta in human-readable form.

    >>> naturaltimedelta(timedelta(days=1, hours=2, minutes=30))
    '1 day, 2:30:00'
    >>> naturaltimedelta(timedelta(hours=5, minutes=15, seconds=30))
    '5:15:30'
    """
    return str(d)
