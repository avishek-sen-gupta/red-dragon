#!/usr/bin/env python3
"""Format ast-grep JSON stream output as a grouped programming patterns lint report."""

import json
import sys
from collections import defaultdict

violations: dict[str, list[tuple[str, int, int, str]]] = defaultdict(list)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        match = json.loads(line)
    except json.JSONDecodeError:
        continue
    rule_id = match.get("ruleId", "unknown")
    file_path = match.get("file", "")
    start = match.get("range", {}).get("start", {})
    line_no = start.get("line", 0) + 1  # ast-grep uses 0-based lines
    col = start.get("column", 0)
    source_line = match.get("lines", "").strip()
    violations[rule_id].append((file_path, line_no, col, source_line))

if not violations:
    print("No lint violations found.")
    sys.exit(0)

total = sum(len(v) for v in violations.values())
print(f"\n{'─' * 72}")
print(
    f"  Programming Patterns Lint Report  ({total} violations across {len(violations)} rules)"
)
print(f"{'─' * 72}")

for rule_id in sorted(violations):
    entries = violations[rule_id]
    print(f"\n  [{rule_id}]  {len(entries)} violation(s)")
    for file_path, line_no, col, source_line in sorted(entries):
        print(f"    {file_path}:{line_no}:{col}")
        if source_line:
            truncated = source_line[:80] + ("…" if len(source_line) > 80 else "")
            print(f"      {truncated}")

print(f"\n{'─' * 72}\n")
