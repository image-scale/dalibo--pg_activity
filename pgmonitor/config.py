"""Configuration system for pg_monitor with profile support."""

from __future__ import annotations

import configparser
import enum
import os
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import IO, Any


class ConfigError(Exception):
    """Configuration error with filename context."""

    def __init__(self, filename: str, message: str) -> None:
        super().__init__(message)
        self.filename = filename
        self._message = message

    def __str__(self) -> str:
        return f"invalid configuration '{self.filename}': {self._message}"


class InvalidSectionError(ConfigError):
    """Invalid section in configuration file."""

    def __init__(self, section: str, filename: str) -> None:
        super().__init__(filename, f"invalid section '{section}'")
        self.section = section


class InvalidOptionError(ConfigError):
    """Invalid option in configuration file."""

    def __init__(self, section: str, message: str, filename: str) -> None:
        super().__init__(filename, f"invalid option(s) in '{section}': {message}")
        self.section = section


class ColumnFlag(enum.Flag):
    """Column display flags.

    >>> ColumnFlag.names()[:3]
    ['database', 'appname', 'client']
    >>> flag = ColumnFlag.DATABASE | ColumnFlag.USER
    >>> bool(flag & ColumnFlag.DATABASE)
    True
    >>> bool(flag & ColumnFlag.CPU)
    False
    """

    DATABASE = enum.auto()
    APPNAME = enum.auto()
    CLIENT = enum.auto()
    USER = enum.auto()
    CPU = enum.auto()
    MEM = enum.auto()
    READ = enum.auto()
    WRITE = enum.auto()
    TIME = enum.auto()
    WAIT = enum.auto()
    RELATION = enum.auto()
    TYPE = enum.auto()
    MODE = enum.auto()
    IOWAIT = enum.auto()
    PID = enum.auto()
    XMIN = enum.auto()

    @classmethod
    def names(cls) -> list[str]:
        """Return list of flag names in lowercase."""
        result = []
        for f in cls:
            if f.name is not None:
                result.append(f.name.lower())
        return result

    @classmethod
    def all(cls) -> ColumnFlag:
        """Return a flag with all columns enabled."""
        value = cls(0)
        for f in cls:
            value |= f
        return value

    @classmethod
    def from_config(cls, config: Configuration) -> ColumnFlag:
        """Build a flag from configuration, disabling hidden columns."""
        value = cls(0)
        for f in cls:
            if f.name is None:
                continue
            col_name = f.name.lower()
            try:
                col_opts = config[col_name]
            except KeyError:
                pass
            else:
                if isinstance(col_opts, ColumnOptions) and col_opts.hidden:
                    continue
            value |= f
        return value

    @classmethod
    def load(
        cls,
        config: Configuration | None,
        *,
        is_local: bool,
        appname: bool | None = None,
        client: bool | None = None,
        cpu: bool | None = None,
        database: bool | None = None,
        mem: bool | None = None,
        pid: bool | None = None,
        read: bool | None = None,
        time: bool | None = None,
        user: bool | None = None,
        wait: bool | None = None,
        write: bool | None = None,
        xmin: bool | None = None,
        **kwargs: Any,
    ) -> ColumnFlag:
        """Build a flag from config and command line options.

        >>> ColumnFlag.load(None, is_local=True, database=True, cpu=False)  # doctest: +ELLIPSIS
        <ColumnFlag...>
        """
        if config is not None:
            flag = cls.from_config(config)
        else:
            flag = cls.all()

        # Apply command line overrides
        for opt, value in (
            (appname, cls.APPNAME),
            (client, cls.CLIENT),
            (cpu, cls.CPU),
            (database, cls.DATABASE),
            (mem, cls.MEM),
            (pid, cls.PID),
            (read, cls.READ),
            (time, cls.TIME),
            (user, cls.USER),
            (wait, cls.WAIT),
            (write, cls.WRITE),
            (xmin, cls.XMIN),
        ):
            if opt is True:
                flag |= value
            elif opt is False:
                flag &= ~value

        # Remove local-only columns when not local
        if not is_local:
            local_only = cls.CPU | cls.MEM | cls.READ | cls.WRITE | cls.IOWAIT
            flag &= ~local_only

        return flag


@dataclass(frozen=True)
class HeaderOptions:
    """Header display options."""
    show_instance: bool = True
    show_system: bool = True
    show_workers: bool = True

    @classmethod
    def from_config_section(
        cls, section: configparser.SectionProxy
    ) -> HeaderOptions:
        """Create from config section."""
        values: dict[str, bool] = {}
        known = {'show_instance', 'show_system', 'show_workers'}

        # Check for unknown options
        unknown = set(section.keys()) - known
        if unknown:
            raise ValueError(f"invalid option(s): {', '.join(sorted(unknown))}")

        for name in known:
            val = section.getboolean(name)
            if val is not None:
                values[name] = val

        return cls(**values)


@dataclass(frozen=True)
class ColumnOptions:
    """Column display options."""
    hidden: bool = False
    width: int | None = None
    color: str | None = None

    def __post_init__(self) -> None:
        if self.width is not None and self.width <= 0:
            raise ValueError(f"'width' must be > 0: {self.width}")

    @classmethod
    def from_config_section(
        cls, section: configparser.SectionProxy
    ) -> ColumnOptions:
        """Create from config section."""
        known = {'hidden', 'width', 'color'}

        # Check for unknown options
        unknown = set(section.keys()) - known
        if unknown:
            raise ValueError(f"invalid option(s): {', '.join(sorted(unknown))}")

        values: dict[str, Any] = {}
        hidden = section.getboolean('hidden')
        if hidden is not None:
            values['hidden'] = hidden
        width_str = section.get('width')
        if width_str is not None:
            values['width'] = int(width_str)
        color = section.get('color')
        if color is not None:
            values['color'] = color

        return cls(**values)


# Type for config values
ConfigValue = HeaderOptions | ColumnOptions


@dataclass(frozen=True)
class Configuration:
    """Configuration container.

    >>> from io import StringIO
    >>> cfg_text = '''
    ... [header]
    ... show_workers=no
    ...
    ... [database]
    ... hidden=yes
    ... width=10
    ... '''
    >>> config = Configuration.parse(StringIO(cfg_text), "test.conf")
    >>> config.name
    'test.conf'
    >>> config['header'].show_workers
    False
    >>> config['database'].hidden
    True
    """
    name: str
    values: dict[str, ConfigValue]

    def __getitem__(self, key: str) -> ConfigValue:
        return self.values[key]

    def get(self, key: str, default: ConfigValue | None = None) -> ConfigValue | None:
        return self.values.get(key, default)

    def header(self) -> HeaderOptions | None:
        val = self.get('header')
        if isinstance(val, HeaderOptions):
            return val
        return None

    def error(self, message: str) -> ConfigError:
        """Create a ConfigError for this configuration."""
        return ConfigError(self.name, message)

    @classmethod
    def parse(cls, f: IO[str], name: str) -> Configuration:
        """Parse configuration from file object.

        >>> from io import StringIO
        >>> bad = StringIO("[invalid_section]\\n")
        >>> Configuration.parse(bad, "bad.ini")
        Traceback (most recent call last):
            ...
        pgmonitor.config.InvalidSectionError: invalid configuration 'bad.ini': invalid section 'invalid_section'
        >>> bad = StringIO("[cpu]\\nunknown=1")
        >>> Configuration.parse(bad, "bad.ini")
        Traceback (most recent call last):
            ...
        pgmonitor.config.InvalidOptionError: invalid configuration 'bad.ini': invalid option(s) in 'cpu': invalid option(s): unknown
        """
        parser = configparser.ConfigParser(default_section='global', strict=True)
        try:
            parser.read_file(f)
        except configparser.Error as e:
            raise ConfigError(name, f"failed to parse INI: {e}") from None

        known_columns = set(ColumnFlag.names())
        config: dict[str, HeaderOptions | ColumnOptions] = {}

        for section_name, section in parser.items():
            if section_name == parser.default_section:
                if section:
                    raise InvalidSectionError(parser.default_section, name)
                continue

            if section_name == 'header':
                try:
                    config[section_name] = HeaderOptions.from_config_section(section)
                except ValueError as e:
                    raise InvalidOptionError(section_name, str(e), name) from None
                continue

            if section_name not in known_columns:
                raise InvalidSectionError(section_name, name)

            try:
                config[section_name] = ColumnOptions.from_config_section(section)
            except ValueError as e:
                raise InvalidOptionError(section_name, str(e), name) from None

        return cls(name=name, values=config)

    @classmethod
    def lookup(
        cls,
        profile: str | None,
        *,
        user_config_home: Path | None = None,
        etc: Path = Path("/etc"),
    ) -> Configuration | None:
        """Look up configuration file.

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     cfg = Configuration.lookup(None, user_config_home=Path(tmpdir))
        ...     print(cfg)
        None
        >>> cfg = Configuration.lookup("minimal", user_config_home=Path("/nonexistent"))
        >>> cfg.header().show_instance
        False
        """
        if user_config_home is None:
            user_config_home = Path(
                os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
            )

        if profile is None:
            # Look for default config file
            for base in (user_config_home, etc):
                fpath = base / "pg_activity.conf"
                if fpath.exists():
                    with fpath.open() as f:
                        return cls.parse(f, str(fpath))
            return None

        # Look for profile file
        fname = f"{profile}.conf"
        bases = (user_config_home / "pg_activity", etc / "pg_activity")

        for base in bases:
            fpath = base / fname
            if fpath.exists():
                with fpath.open() as f:
                    return cls.parse(f, str(fpath))

        # Try built-in profiles
        builtin = get_builtin_profile(profile)
        if builtin is not None:
            return cls.parse(StringIO(builtin), f"<builtin:{profile}>")

        raise FileNotFoundError(f"profile {profile!r} not found")


# Built-in profile definitions
BUILTIN_PROFILES: dict[str, str] = {
    "minimal": """\
[header]
show_instance = no
show_system = no
show_workers = no

[database]
hidden = yes

[user]
hidden = yes

[client]
hidden = yes

[cpu]
hidden = yes

[mem]
hidden = yes

[read]
hidden = yes

[write]
hidden = yes

[appname]
hidden = yes

[xmin]
hidden = yes
""",
    "narrow": """\
[database]
hidden = yes

[user]
hidden = yes

[client]
hidden = yes

[cpu]
hidden = yes

[mem]
hidden = yes

[read]
hidden = yes

[write]
hidden = yes

[appname]
hidden = yes

[xmin]
hidden = yes
""",
    "wide": """\
[database]
hidden = no

[user]
hidden = no

[client]
hidden = no

[cpu]
hidden = no

[mem]
hidden = no

[read]
hidden = no

[write]
hidden = no

[appname]
hidden = no

[xmin]
hidden = no
""",
}


def get_builtin_profile(name: str) -> str | None:
    """Get a built-in profile by name.

    >>> get_builtin_profile("minimal") is not None
    True
    >>> get_builtin_profile("nonexistent") is None
    True
    """
    return BUILTIN_PROFILES.get(name)
