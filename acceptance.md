# Acceptance Criteria

## Task 1: Core data models for processes, system info, and query modes

### Acceptance Criteria
- [ ] QueryMode enum has three modes: activities, waiting, blocking with human-readable values
- [ ] SortKey enum supports sorting by cpu, mem, read, write, duration with a default() method
- [ ] DurationMode enum has three modes: query (1), transaction (2), backend (3)
- [ ] MemoryInfo holds used, buff_cached, free, total bytes and computes pct_used, pct_free, pct_bc percentages
- [ ] SwapInfo holds used, free, total bytes and computes pct_used, pct_free percentages
- [ ] LoadAverage holds avg1, avg5, avg15 float values
- [ ] IOCounter holds count and bytes as integers
- [ ] SystemInfo combines memory, swap, load, io_read, io_write, max_iops
- [ ] RunningProcess has pid, database, user, client, query, state, duration, wait, application_name, is_parallel_worker
- [ ] WaitingProcess extends base with mode, type, relation for lock information
- [ ] BlockingProcess extends base with mode, type, relation, wait fields
- [ ] LocalRunningProcess adds cpu, mem, read, write, io_wait metrics
- [ ] SelectableProcesses provides focus_next, focus_prev, toggle_pin, selected list, reset functionality
- [ ] Filters class parses "field:regex" format and validates known fields (dbname)
- [ ] enum_next helper cycles through enum values wrapping at the end
