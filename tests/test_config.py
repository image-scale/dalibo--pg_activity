"""Tests for configuration system."""

import tempfile
from io import StringIO
from pathlib import Path

import pytest

from pgmonitor.config import (
    ColumnFlag,
    HeaderOptions,
    ColumnOptions,
    Configuration,
    ConfigError,
    InvalidSectionError,
    InvalidOptionError,
    get_builtin_profile,
    BUILTIN_PROFILES,
)


class TestColumnFlag:
    """Tests for ColumnFlag enum."""

    def test_names_returns_lowercase(self):
        """names() returns lowercase flag names."""
        names = ColumnFlag.names()
        assert "database" in names
        assert "appname" in names
        assert "cpu" in names
        assert all(n == n.lower() for n in names)

    def test_all_returns_all_flags(self):
        """all() returns a flag with all values set."""
        flag = ColumnFlag.all()
        assert flag & ColumnFlag.DATABASE
        assert flag & ColumnFlag.CPU
        assert flag & ColumnFlag.MEM

    def test_flag_operations(self):
        """Flag operations work correctly."""
        flag = ColumnFlag.DATABASE | ColumnFlag.USER
        assert flag & ColumnFlag.DATABASE
        assert flag & ColumnFlag.USER
        assert not (flag & ColumnFlag.CPU)

    def test_load_with_no_config(self):
        """load() with no config enables all flags."""
        flag = ColumnFlag.load(None, is_local=True)
        assert flag & ColumnFlag.DATABASE
        assert flag & ColumnFlag.CPU

    def test_load_disables_local_when_not_local(self):
        """load() disables local-only flags when not local."""
        flag = ColumnFlag.load(None, is_local=False)
        assert flag & ColumnFlag.DATABASE
        assert not (flag & ColumnFlag.CPU)
        assert not (flag & ColumnFlag.MEM)
        assert not (flag & ColumnFlag.READ)
        assert not (flag & ColumnFlag.WRITE)

    def test_load_applies_overrides(self):
        """load() applies command line overrides."""
        flag = ColumnFlag.load(None, is_local=True, database=False, cpu=True)
        assert not (flag & ColumnFlag.DATABASE)
        assert flag & ColumnFlag.CPU

    def test_from_config_hides_columns(self):
        """from_config() hides columns marked as hidden."""
        config = Configuration(
            name="test",
            values={"database": ColumnOptions(hidden=True)},
        )
        flag = ColumnFlag.from_config(config)
        assert not (flag & ColumnFlag.DATABASE)
        assert flag & ColumnFlag.USER


class TestHeaderOptions:
    """Tests for HeaderOptions class."""

    def test_default_values(self):
        """Default values are all True."""
        opts = HeaderOptions()
        assert opts.show_instance is True
        assert opts.show_system is True
        assert opts.show_workers is True

    def test_from_config_section(self):
        """from_config_section parses values correctly."""
        config = configparser.ConfigParser()
        config.read_string("[header]\nshow_workers=no\nshow_instance=yes")
        opts = HeaderOptions.from_config_section(config["header"])
        assert opts.show_workers is False
        assert opts.show_instance is True
        assert opts.show_system is True  # default

    def test_from_config_section_unknown_option(self):
        """from_config_section raises on unknown options."""
        config = configparser.ConfigParser()
        config.read_string("[header]\nunknown_option=yes")
        with pytest.raises(ValueError, match="invalid option"):
            HeaderOptions.from_config_section(config["header"])


class TestColumnOptions:
    """Tests for ColumnOptions class."""

    def test_default_values(self):
        """Default values are sensible."""
        opts = ColumnOptions()
        assert opts.hidden is False
        assert opts.width is None
        assert opts.color is None

    def test_with_values(self):
        """Custom values are stored."""
        opts = ColumnOptions(hidden=True, width=10, color="green")
        assert opts.hidden is True
        assert opts.width == 10
        assert opts.color == "green"

    def test_width_validation(self):
        """Width must be positive."""
        with pytest.raises(ValueError, match="width"):
            ColumnOptions(width=0)
        with pytest.raises(ValueError, match="width"):
            ColumnOptions(width=-5)

    def test_from_config_section(self):
        """from_config_section parses values correctly."""
        config = configparser.ConfigParser()
        config.read_string("[cpu]\nhidden=yes\nwidth=15\ncolor=red")
        opts = ColumnOptions.from_config_section(config["cpu"])
        assert opts.hidden is True
        assert opts.width == 15
        assert opts.color == "red"


class TestConfiguration:
    """Tests for Configuration class."""

    def test_parse_header_section(self):
        """parse() handles header section."""
        cfg_text = "[header]\nshow_workers=no"
        config = Configuration.parse(StringIO(cfg_text), "test.conf")
        assert config.name == "test.conf"
        header = config.header()
        assert header is not None
        assert header.show_workers is False

    def test_parse_column_section(self):
        """parse() handles column sections."""
        cfg_text = "[database]\nhidden=yes\nwidth=10"
        config = Configuration.parse(StringIO(cfg_text), "test.conf")
        col_opts = config["database"]
        assert isinstance(col_opts, ColumnOptions)
        assert col_opts.hidden is True
        assert col_opts.width == 10

    def test_parse_invalid_section(self):
        """parse() raises on invalid section."""
        cfg_text = "[invalid_section]\n"
        with pytest.raises(InvalidSectionError, match="invalid section"):
            Configuration.parse(StringIO(cfg_text), "test.conf")

    def test_parse_invalid_option(self):
        """parse() raises on invalid option."""
        cfg_text = "[cpu]\nunknown=yes"
        with pytest.raises(InvalidOptionError, match="invalid option"):
            Configuration.parse(StringIO(cfg_text), "test.conf")

    def test_parse_global_section_error(self):
        """parse() raises on malformed INI."""
        cfg_text = "key=value\n"  # No section
        with pytest.raises(ConfigError, match="failed to parse INI"):
            Configuration.parse(StringIO(cfg_text), "test.conf")

    def test_get_returns_default(self):
        """get() returns default for missing keys."""
        config = Configuration(name="test", values={})
        assert config.get("missing") is None
        default = ColumnOptions()
        assert config.get("missing", default) is default

    def test_error_method(self):
        """error() creates ConfigError with filename."""
        config = Configuration(name="test.conf", values={})
        err = config.error("test message")
        assert isinstance(err, ConfigError)
        assert err.filename == "test.conf"


class TestConfigurationLookup:
    """Tests for Configuration.lookup method."""

    def test_lookup_no_config(self):
        """lookup() returns None when no config found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Configuration.lookup(None, user_config_home=Path(tmpdir))
            assert config is None

    def test_lookup_default_config(self):
        """lookup() finds default config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "pg_activity.conf"
            config_path.write_text("[header]\nshow_workers=no")
            config = Configuration.lookup(None, user_config_home=Path(tmpdir))
            assert config is not None
            assert config.header().show_workers is False

    def test_lookup_profile(self):
        """lookup() finds profile by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "pg_activity"
            profile_dir.mkdir()
            (profile_dir / "custom.conf").write_text("[header]\nshow_system=no")
            config = Configuration.lookup("custom", user_config_home=Path(tmpdir))
            assert config is not None
            assert config.header().show_system is False

    def test_lookup_builtin_profile(self):
        """lookup() finds built-in profiles."""
        config = Configuration.lookup(
            "minimal", user_config_home=Path("/nonexistent")
        )
        assert config is not None
        header = config.header()
        assert header is not None
        assert header.show_instance is False

    def test_lookup_missing_profile(self):
        """lookup() raises FileNotFoundError for missing profile."""
        with pytest.raises(FileNotFoundError, match="not found"):
            Configuration.lookup("nonexistent", user_config_home=Path("/nonexistent"))


class TestBuiltinProfiles:
    """Tests for built-in profiles."""

    def test_minimal_profile(self):
        """minimal profile hides header and columns."""
        config = Configuration.lookup(
            "minimal", user_config_home=Path("/nonexistent")
        )
        header = config.header()
        assert header.show_instance is False
        assert header.show_system is False
        assert header.show_workers is False
        db_opts = config["database"]
        assert isinstance(db_opts, ColumnOptions)
        assert db_opts.hidden is True

    def test_narrow_profile(self):
        """narrow profile hides columns but not header."""
        config = Configuration.lookup(
            "narrow", user_config_home=Path("/nonexistent")
        )
        # narrow doesn't have a header section
        assert config.header() is None
        db_opts = config["database"]
        assert isinstance(db_opts, ColumnOptions)
        assert db_opts.hidden is True

    def test_wide_profile(self):
        """wide profile shows all columns."""
        config = Configuration.lookup(
            "wide", user_config_home=Path("/nonexistent")
        )
        db_opts = config["database"]
        assert isinstance(db_opts, ColumnOptions)
        assert db_opts.hidden is False

    def test_get_builtin_profile(self):
        """get_builtin_profile returns profile content."""
        content = get_builtin_profile("minimal")
        assert content is not None
        assert "show_instance" in content

        missing = get_builtin_profile("nonexistent")
        assert missing is None


# Need to import configparser at module level for the tests
import configparser
