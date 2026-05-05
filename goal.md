# Goal

## Project
pg_activity — a python project.

## Description
A command line tool for PostgreSQL server activity monitoring, similar to htop but for PostgreSQL databases. It provides a real-time terminal-based interface to:
- View running, waiting, and blocking queries
- Monitor database server statistics (TPS, connections, cache hit ratio)
- Display system information (memory, swap, CPU, IO) when running locally
- Sort and filter processes by various criteria
- Cancel or terminate PostgreSQL backends interactively
- Support configuration profiles for customizing display

## Scope
- 12-15 production source files to implement
- 6-8 test files to write
- Core functionality: data models, database queries, system monitoring, terminal UI, configuration
