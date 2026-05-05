# Progress

(Updated after each feature commit.)

## Round 1
**Task**: Task 1 — Core data models for processes, system info, and query modes
**Files created**: pgmonitor/__init__.py, pgmonitor/types.py, tests/test_types.py, pytest.ini, pyproject.toml
**Commit**: Add data models for PostgreSQL activity monitoring including query modes, process types, and system metrics.
**Acceptance**: 15/15 criteria met
**Verification**: tests FAIL on previous state (ImportError), PASS on current state (55 tests)

## Round 2
**Task**: Task 2 — Utility functions for formatting data
**Files created**: pgmonitor/utils.py, tests/test_utils.py
**Commit**: Add utility functions for formatting duration, sizes, and text.
**Acceptance**: 10/10 criteria met
**Verification**: tests FAIL on previous state (ImportError), PASS on current state (106 tests)

## Round 3
**Task**: Task 3 — Configuration system with profiles
**Files created**: pgmonitor/config.py, tests/test_config.py
**Commit**: Add configuration system with INI file parsing and built-in profiles.
**Acceptance**: 11/11 criteria met
**Verification**: tests FAIL on previous state (ImportError), PASS on current state (142 tests)
