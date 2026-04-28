"""Command-line interface module."""
from __future__ import annotations

import argparse
from textwrap import dedent
from typing import TYPE_CHECKING

from . import __version__

if TYPE_CHECKING:
    from argparse import ArgumentParser


EPILOG = dedent(
    """\
    The connection string can be in the form of a list of Key/Value parameters or
    an URI as described in the PostgreSQL documentation. The parsing is delegated
    to the libpq: different versions of the client library may support different
    formats or parameters (for example, connection URIs are only supported from
    libpq 9.2).
    """
)


class BooleanOptionalAction(argparse.Action):
    """Action to handle --flag/--no-flag boolean arguments."""

    def __init__(
        self,
        option_strings: list[str],
        dest: str,
        default: bool | None = None,
        required: bool = False,
        help: str | None = None,
    ):
        _option_strings = []
        for option_string in option_strings:
            _option_strings.append(option_string)
            if option_string.startswith("--"):
                _option_strings.append(f"--no-{option_string[2:]}")

        super().__init__(
            option_strings=_option_strings,
            dest=dest,
            nargs=0,
            default=default,
            required=required,
            help=help,
        )

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: argparse.Namespace,
        values: str | list[str] | None,
        option_string: str | None = None,
    ) -> None:
        if option_string is not None:
            setattr(namespace, self.dest, not option_string.startswith("--no-"))

    def format_usage(self) -> str:
        return " | ".join(self.option_strings)


def get_parser(prog: str = "pg_activity") -> ArgumentParser:
    """Create and return the argument parser for pg_activity."""
    parser = argparse.ArgumentParser(
        prog=prog,
        usage="%(prog)s [options] [connection string]",
        description="htop like application for PostgreSQL server activity monitoring.",
        epilog=EPILOG,
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Configuration group
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "-P",
        "--profile",
        dest="profile",
        default=None,
        metavar="PROFILE",
        help="Configuration profile matching a PROFILE.conf file in "
        "${XDG_CONFIG_HOME:~/.config}/pg_activity/ or /etc/pg_activity/, "
        "or a built-in profile.",
    )

    # Options group
    options_group = parser.add_argument_group("Options")
    options_group.add_argument(
        "--blocksize",
        dest="blocksize",
        default=4096,
        type=int,
        metavar="BLOCKSIZE",
        help="Filesystem blocksize (default: 4096).",
    )
    options_group.add_argument(
        "--rds",
        dest="rds",
        default=False,
        action="store_true",
        help="Enable support for AWS RDS (implies --no-tempfiles and filters out "
        "the rdsadmin database from space calculation).",
    )
    options_group.add_argument(
        "--output",
        dest="output",
        default=None,
        metavar="FILEPATH",
        help="Store running queries as CSV.",
    )
    options_group.add_argument(
        "--db-size",
        dest="dbsize",
        action=BooleanOptionalAction,
        default=True,
        help="Enable/disable total size of DB.",
    )
    options_group.add_argument(
        "--tempfiles",
        dest="tempfiles",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable tempfile count and size.",
    )
    options_group.add_argument(
        "--walreceiver",
        dest="walreceiver",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable walreceiver checks.",
    )
    options_group.add_argument(
        "-w",
        "--wrap-query",
        dest="wrap_query",
        action="store_true",
        default=False,
        help="Wrap query column instead of truncating.",
    )
    options_group.add_argument(
        "--duration-mode",
        dest="durationmode",
        default="1",
        metavar="DURATION_MODE",
        help="Duration mode. Values: 1-QUERY(default), 2-TRANSACTION, 3-BACKEND.",
    )
    options_group.add_argument(
        "--min-duration",
        dest="minduration",
        default=0,
        type=float,
        metavar="SECONDS",
        help="Don't display queries with smaller than specified duration (in seconds).",
    )
    options_group.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        metavar="FIELD:REGEX",
        help="Filter activities with a (case insensitive) regular expression "
        "applied on selected fields. Known fields are: dbname.",
    )
    options_group.add_argument(
        "--debug-file",
        dest="debug_file",
        default=None,
        metavar="DEBUG_FILE",
        help="Enable debug and write it to DEBUG_FILE.",
    )
    options_group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show program's version number and exit.",
    )
    options_group.add_argument(
        "--help",
        dest="help",
        action="store_true",
        default=False,
        help="Show this help message and exit.",
    )

    # Connection options group
    conn_group = parser.add_argument_group("Connection Options")
    conn_group.add_argument(
        "connection_string",
        nargs="?",
        default="",
        metavar="connection string",
        help="A valid connection string to the database, e.g.: "
        "'host=HOSTNAME port=PORT user=USER dbname=DBNAME'.",
    )
    conn_group.add_argument(
        "-h",
        "--host",
        dest="host",
        default=None,
        metavar="HOSTNAME",
        help="Database server host or socket directory.",
    )
    conn_group.add_argument(
        "-p",
        "--port",
        dest="port",
        default="5432",
        metavar="PORT",
        help="Database server port.",
    )
    conn_group.add_argument(
        "-U",
        "--username",
        dest="username",
        default=None,
        metavar="USERNAME",
        help="Database user name.",
    )
    conn_group.add_argument(
        "-d",
        "--dbname",
        dest="dbname",
        default=None,
        metavar="DBNAME",
        help="Database name to connect to.",
    )

    # Process table display options group
    display_group = parser.add_argument_group(
        "Process table display options",
        description="These options may be used hide some columns from the processes table.",
    )
    display_group.add_argument(
        "--pid",
        dest="pid",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable PID.",
    )
    display_group.add_argument(
        "--xmin",
        dest="xmin",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable XMIN.",
    )
    display_group.add_argument(
        "--database",
        dest="database",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable DATABASE.",
    )
    display_group.add_argument(
        "--user",
        dest="user",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable USER.",
    )
    display_group.add_argument(
        "--client",
        dest="client",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable CLIENT.",
    )
    display_group.add_argument(
        "--cpu",
        dest="cpu",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable CPU%%.",
    )
    display_group.add_argument(
        "--mem",
        dest="mem",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable MEM%%.",
    )
    display_group.add_argument(
        "--read",
        dest="read",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable READ/s.",
    )
    display_group.add_argument(
        "--write",
        dest="write",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable WRITE/s.",
    )
    display_group.add_argument(
        "--time",
        dest="time",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable TIME+.",
    )
    display_group.add_argument(
        "--wait",
        dest="wait",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable W.",
    )
    display_group.add_argument(
        "--app-name",
        dest="appname",
        action=BooleanOptionalAction,
        default=None,
        help="Enable/disable APP.",
    )

    # Header display options group
    header_group = parser.add_argument_group("Header display options")
    header_group.add_argument(
        "--no-inst-info",
        dest="header_show_instance",
        action="store_false",
        default=None,
        help="Hide instance information.",
    )
    header_group.add_argument(
        "--no-sys-info",
        dest="header_show_system",
        action="store_false",
        default=None,
        help="Hide system information.",
    )
    header_group.add_argument(
        "--no-proc-info",
        dest="header_show_workers",
        action="store_false",
        default=None,
        help="Hide workers process information.",
    )

    # Other display options group
    other_group = parser.add_argument_group("Other display options")
    other_group.add_argument(
        "--hide-queries-in-logs",
        dest="hide_queries_in_logs",
        action="store_true",
        default=False,
        help="Disable log_min_duration_statements and log_min_duration_sample "
        "for pg_activity.",
    )
    other_group.add_argument(
        "--refresh",
        dest="refresh",
        type=float,
        default=2,
        choices=[0.5, 1, 2, 3, 4, 5],
        metavar="REFRESH",
        help="Refresh rate. Values: 0.5, 1, 2, 3, 4, 5 (default: 2).",
    )

    return parser
