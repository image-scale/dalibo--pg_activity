# Progress

(Updated after each feature commit.)

## Round 1
**Task**: Task 1 — Core data models for processes, system info, and query modes
**Files created**: pgmonitor/__init__.py, pgmonitor/types.py, tests/test_types.py, pytest.ini, pyproject.toml
**Commit**: Add data models for PostgreSQL activity monitoring including query modes, process types, and system metrics.
**Acceptance**: 15/15 criteria met
**Verification**: tests FAIL on previous state (ImportError), PASS on current state (55 tests)
