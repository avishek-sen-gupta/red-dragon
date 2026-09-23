"""The repo's fp.json must be the rule set python-fp-lint actually runs.

Two silent failures motivated this: the locked linter once predated config
support and never read fp.json, and a stale project-local rules directory
shadowed the configured rules, so every ast-grep rule reported zero. Both
looked like a clean run.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_LONG_BODY = "\n".join(
    ["    v0 = 0"] + [f"    v{i} = v{i - 1} + 1" for i in range(1, 15)]
)

SAMPLE = f"""def grow(items: list[int]) -> list[int]:
    items.append(1)
    return items


def long_body() -> int:
{_LONG_BODY}
    return v14
"""


def _rules_reported(path: Path) -> set[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "python_fp_lint",
            "--format",
            "json",
            "check",
            "--strict",
            "--config",
            "fp.json",
            str(path),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    # ast-grep writes "W: ..." diagnostics to stdout ahead of the JSON payload.
    payload = result.stdout[result.stdout.index("{") :]
    return {v["rule"] for v in json.loads(payload)["violations"]}


def test_fp_json_rules_and_thresholds_are_what_the_linter_runs(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(SAMPLE)

    # no-list-append / no-list-dict-param-annotation: the configured ast-grep
    # rules are live. PLR0915: fp.json's ruff_select and its max_statements of
    # 10 are honoured (ruff's default ceiling is 50).
    assert _rules_reported(sample) == {
        "no-list-append",
        "no-list-dict-param-annotation",
        "PLR0915",
    }
