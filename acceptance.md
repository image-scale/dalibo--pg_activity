# Acceptance Criteria

## Task 1: Core data models for processes, system info, and query modes

### Acceptance Criteria
- [x] QueryMode enum has three modes: activities, waiting, blocking with human-readable values
- [x] SortKey enum supports sorting by cpu, mem, read, write, duration with a default() method
- [x] DurationMode enum has three modes: query (1), transaction (2), backend (3)
- [x] MemoryInfo holds used, buff_cached, free, total bytes and computes pct_used, pct_free, pct_bc percentages
- [x] SwapInfo holds used, free, total bytes and computes pct_used, pct_free percentages
- [x] LoadAverage holds avg1, avg5, avg15 float values
- [x] IOCounter holds count and bytes as integers
- [x] SystemInfo combines memory, swap, load, io_read, io_write, max_iops
- [x] RunningProcess has pid, database, user, client, query, state, duration, wait, application_name, is_parallel_worker
- [x] WaitingProcess extends base with mode, type, relation for lock information
- [x] BlockingProcess extends base with mode, type, relation, wait fields
- [x] LocalRunningProcess adds cpu, mem, read, write, io_wait metrics
- [x] SelectableProcesses provides focus_next, focus_prev, toggle_pin, selected list, reset functionality
- [x] Filters class parses "field:regex" format and validates known fields (dbname)
- [x] enum_next helper cycles through enum values wrapping at the end

## Task 2: Utility functions for formatting data

### Acceptance Criteria
- [ ] format_duration returns human-readable duration: sub-second shows microseconds (0.123456), 1-60000s shows mm:ss.ff, over 60000s shows hours
- [ ] format_duration returns color: green for <1s, yellow for 1-3s, red for >3s
- [ ] naturalsize formats bytes with binary units using humanize library
- [ ] yn converts boolean to "Y" or "N" string
- [ ] clean_str removes newlines, collapses whitespace, trims leading/trailing spaces
- [ ] ellipsis shortens text with "..." in middle if longer than width
- [ ] short_state abbreviates "idle in transaction" to "idle in trans"
- [ ] wait_status formats wait value: empty for None, Y/N for bool, string as-is
- [ ] MessagePile stores messages and returns them N times before clearing
- [ ] csv_write exports processes to CSV with headers and proper quoting
