import re


def parse_log(log: str) -> dict[str, str]:
    """Parse test runner output into per-test results.

    Args:
        log: Full stdout+stderr output of `bash run_test.sh 2>&1`.

    Returns:
        Dict mapping test_id to status.
        - test_id: pytest native format
          (e.g. "tests/foo.py::TestClass::test_func[param]")
        - status: one of "PASSED", "FAILED", "SKIPPED", "ERROR"
        - Must include ALL tests that appear in the output, not just failures.
    """
    results = {}
    # Strip ANSI escape codes
    log = re.sub(r'\x1b\[[0-9;]*m', '', log)
    log = re.sub(r'\x1b\(B', '', log)

    for line in log.splitlines():
        line = line.strip()

        # Match verbose pytest output lines:
        # <test_id> PASSED/FAILED/ERROR  [ XX%]
        # <test_id> SKIPPED (reason...)  [ XX%]
        # Test IDs may contain spaces (parametrized tests), so we anchor
        # on the percentage marker at the end.
        m = re.match(
            r'^(\S+::\S+.*?)\s+(PASSED|FAILED|ERROR|SKIPPED)(?:\s.*?)?\s+\[\s*\d+%\]',
            line
        )
        if m:
            test_id = m.group(1).rstrip()
            status = m.group(2)
            results[test_id] = status
            continue

        # Handle collection errors: "ERROR tests/foo.py" (no ::)
        m = re.match(r'^ERROR\s+(tests/\S+\.py)$', line)
        if m:
            results[m.group(1)] = "ERROR"
            continue

    # Also parse the short test summary info section for any missed tests
    in_summary = False
    for line in log.splitlines():
        line = line.strip()
        if line == "short test summary info":
            in_summary = True
            continue
        if in_summary:
            if line.startswith("="):
                break
            m = re.match(r'^(FAILED|ERROR)\s+(\S+::\S+)', line)
            if m:
                status = m.group(1)
                test_id = m.group(2)
                # Don't overwrite inline results
                results.setdefault(test_id, status)

    return results

