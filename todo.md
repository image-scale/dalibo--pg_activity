# Todo

## Plan
Implement the project in a layered approach: start with core data models and utility functions, then database connection and queries, followed by system monitoring, and finally the terminal UI components. Each task will deliver user-facing functionality with tests.

## Tasks
- [x] Task 1: Core data models for processes, system info, and query modes - types for running/waiting/blocking processes with attributes like pid, database, query, duration; system info types for memory, swap, load average; enumerated query modes and sort keys
- [x] Task 2: Utility functions for formatting data - human-readable duration formatting, byte sizes, query text cleaning, boolean Y/N display, CSV export
- [x] Task 3: Configuration system with profiles - INI file parsing, column flags for showing/hiding fields, header display options, built-in profiles (narrow/wide/minimal), profile lookup from user config directories
- [x] Task 4: Database connection and SQL queries - PostgreSQL connection wrapper supporting psycopg, execute queries for running/waiting/blocking processes, server statistics, cancel/terminate backends
- [x] Task 5: System monitoring with psutil - collect memory, swap, load average, per-process CPU/memory/IO metrics, integrate system data with process information
- [x] Task 6: Keyboard handling and action handlers - key bindings for navigation, sorting, mode switching, refresh rate control, process selection, map keystrokes to UI state changes
- [x] Task 7: Terminal rendering with blessed - header display with server stats, process table with columns, footer with help keys, color-coded output, query wrapping
- [x] Task 8: Main UI loop and CLI - integrate all components into interactive loop, command line argument parsing, process list navigation, cancel/terminate confirmations
