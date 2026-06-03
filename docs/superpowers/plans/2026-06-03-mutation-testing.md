# Mutation Testing Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `mutmut`-backed mutation testing infrastructure to RedDragon so the quality of the existing test suite can be measured and improved over time against the core IR/VM modules.

**Architecture:** Two changes to existing files (add `mutmut` dev dependency + `[tool.mutmut]` config to `pyproject.toml`; add `.mutmut-cache` to `.gitignore`) and one new file (`scripts/mutation_test.py`) that wraps `mutmut` with named targets. The script is the entire interface — no CI wiring, no automation.

**Tech Stack:** Python 3.12, `mutmut >=2.4`, `pytest-cov` (already present), `subprocess` for shelling out to mutmut.

---

## File Structure

**New files:**
- `scripts/mutation_test.py` — the mutation testing runner and CLI

**Modified files:**
- `pyproject.toml` — add `mutmut` to `[tool.poetry.group.dev.dependencies]` and add `[tool.mutmut]` config section
- `.gitignore` — add `.mutmut-cache`

---

## Task 1: Add `mutmut` Dependency and Configuration

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

There is nothing to TDD here — these are config file changes. Verify them by running the install and checking the config is picked up.

- [ ] **Step 1: Add `mutmut` to dev dependencies in `pyproject.toml`**

In the `[tool.poetry.group.dev.dependencies]` section (currently ending around line 49), add:

```toml
mutmut = ">=2.4"
```

The section should look like:

```toml
[tool.poetry.group.dev.dependencies]
black = "^26.1.0"
pytest = "^8.0.0"
pytest-xdist = "^3.8.0"
radon = "^6.0"
pylint = "^3.0"
import-linter = "^2.0"
grimp = "^3.0"
pydeps = "^1.12"
textual = "^8.1.0"
pyright = "^1.1.408"
tdd-guard-pytest = "^0.1.2"
pytest-cov = "^7.1.0"
pytest-timeout = "^2.4.0"
mutmut = ">=2.4"
```

- [ ] **Step 2: Add `[tool.mutmut]` config section to `pyproject.toml`**

Append after the existing `[tool.coverage.report]` section (the end of the file):

```toml
[tool.mutmut]
runner = "poetry run python -m pytest tests/ -x -q --tb=no"
tests_dir = "tests/"
```

`paths_to_mutate` is deliberately absent — the script always supplies it per-run.

- [ ] **Step 3: Add `.mutmut-cache` to `.gitignore`**

Append to `.gitignore`:

```
# mutmut results cache
.mutmut-cache
```

- [ ] **Step 4: Install the new dependency**

```bash
poetry install
```

Expected: resolves and installs `mutmut` without errors.

- [ ] **Step 5: Verify mutmut is available**

```bash
poetry run mutmut --version
```

Expected output: `mutmut 2.x.x` (any version ≥ 2.4).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml poetry.lock .gitignore
git commit -m "chore: add mutmut dev dependency and [tool.mutmut] config"
```

---

## Task 2: Create `scripts/mutation_test.py`

**Files:**
- Create: `scripts/mutation_test.py`
- Create: `tests/unit/test_mutation_test_script.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_mutation_test_script.py
"""Tests for scripts/mutation_test.py — verify correct subprocess commands are built."""

from __future__ import annotations

import sys
import os
import subprocess
from io import StringIO
from unittest.mock import call, patch, MagicMock

import pytest

# Make scripts/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import mutation_test  # noqa: E402


def test_targets_dict_has_expected_keys():
    assert set(mutation_test.TARGETS.keys()) == {"core", "vm", "handlers", "all-core"}


def test_target_core_paths():
    assert "interpreter/ir.py" in mutation_test.TARGETS["core"]
    assert "interpreter/instructions.py" in mutation_test.TARGETS["core"]
    assert "interpreter/register.py" in mutation_test.TARGETS["core"]


def test_target_vm_paths():
    assert mutation_test.TARGETS["vm"] == ["interpreter/vm/"]


def test_target_handlers_paths():
    assert mutation_test.TARGETS["handlers"] == ["interpreter/handlers/"]


def test_target_all_core_is_union():
    all_core = mutation_test.TARGETS["all-core"]
    for path in mutation_test.TARGETS["core"]:
        assert path in all_core
    assert "interpreter/vm/" in all_core
    assert "interpreter/handlers/" in all_core


def test_run_target_calls_mutmut_with_correct_paths():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.run_target("vm")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "mutmut" in cmd
        assert "run" in cmd
        assert any("interpreter/vm/" in arg for arg in cmd)


def test_run_target_core_joins_multiple_paths():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.run_target("core")
        cmd = mock_run.call_args[0][0]
        paths_arg = next(arg for arg in cmd if "paths" in arg.lower())
        assert "interpreter/ir.py" in paths_arg
        assert "interpreter/instructions.py" in paths_arg
        assert "interpreter/register.py" in paths_arg


def test_run_target_use_coverage_runs_pytest_first():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.run_target("vm", use_coverage=True)
        assert mock_run.call_count == 2
        first_call_cmd = mock_run.call_args_list[0][0][0]
        assert "pytest" in first_call_cmd
        assert "--cov" in " ".join(first_call_cmd)
        second_call_cmd = mock_run.call_args_list[1][0][0]
        assert "mutmut" in second_call_cmd
        assert "--use-coverage" in second_call_cmd


def test_show_results_calls_mutmut_results():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mutation_test.show_results()
        cmd = mock_run.call_args[0][0]
        assert "mutmut" in cmd
        assert "results" in cmd


def test_list_targets_prints_all_targets(capsys):
    mutation_test.list_targets()
    captured = capsys.readouterr()
    for target in ("core", "vm", "handlers", "all-core"):
        assert target in captured.out


def test_main_list_flag(capsys):
    with patch("sys.argv", ["mutation_test.py", "--list"]):
        mutation_test.main()
    captured = capsys.readouterr()
    assert "vm" in captured.out
    assert "handlers" in captured.out


def test_main_results_flag():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("sys.argv", ["mutation_test.py", "--results"]):
            mutation_test.main()
        cmd = mock_run.call_args[0][0]
        assert "results" in cmd


def test_main_target_flag():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("sys.argv", ["mutation_test.py", "--target", "handlers"]):
            mutation_test.main()
        cmd = mock_run.call_args[0][0]
        assert "interpreter/handlers/" in " ".join(cmd)


def test_main_exits_with_mutmut_return_code():
    with patch("mutation_test.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=3)
        with patch("sys.argv", ["mutation_test.py", "--target", "vm"]):
            with pytest.raises(SystemExit) as exc_info:
                mutation_test.main()
            assert exc_info.value.code == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_mutation_test_script.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'mutation_test'` (file doesn't exist yet).

- [ ] **Step 3: Create `scripts/mutation_test.py`**

```python
#!/usr/bin/env python3
"""mutation_test.py — run mutmut against named RedDragon target modules.

Usage:
    python scripts/mutation_test.py --list
    python scripts/mutation_test.py --target vm
    python scripts/mutation_test.py --target core
    python scripts/mutation_test.py --target all-core
    python scripts/mutation_test.py --results
    python scripts/mutation_test.py --target vm --use-coverage
"""

from __future__ import annotations

import argparse
import subprocess
import sys

TARGETS: dict[str, list[str]] = {
    "core": [
        "interpreter/ir.py",
        "interpreter/instructions.py",
        "interpreter/register.py",
    ],
    "vm": ["interpreter/vm/"],
    "handlers": ["interpreter/handlers/"],
    "all-core": [
        "interpreter/ir.py",
        "interpreter/instructions.py",
        "interpreter/register.py",
        "interpreter/vm/",
        "interpreter/handlers/",
    ],
}


def run_target(target: str, use_coverage: bool = False) -> int:
    """Run mutmut against the named target. Returns mutmut's exit code."""
    paths = TARGETS[target]
    paths_str = ",".join(paths)

    if use_coverage:
        cov_paths = ",".join(f"--cov={p}" for p in paths)
        cov_cmd = [
            "poetry", "run", "python", "-m", "pytest",
            *cov_paths.split(),
            "tests/", "-q", "--tb=no",
        ]
        result = subprocess.run(cov_cmd)
        if result.returncode != 0:
            return result.returncode

    cmd = [
        "poetry", "run", "mutmut", "run",
        f"--paths-to-mutate={paths_str}",
    ]
    if use_coverage:
        cmd.append("--use-coverage")

    result = subprocess.run(cmd)
    return result.returncode


def show_results() -> int:
    """Print mutmut results summary from the last run. Returns exit code."""
    result = subprocess.run(["poetry", "run", "mutmut", "results"])
    return result.returncode


def list_targets() -> None:
    """Print all available targets and their paths."""
    for name, paths in TARGETS.items():
        print(f"  {name}: {', '.join(paths)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run mutmut on RedDragon core modules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--target",
        choices=list(TARGETS.keys()),
        help="Named module target to mutate.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available targets and their paths.",
    )
    parser.add_argument(
        "--results",
        action="store_true",
        help="Print mutmut results summary from the last run.",
    )
    parser.add_argument(
        "--use-coverage",
        action="store_true",
        help=(
            "Run pytest --cov first, then pass --use-coverage to mutmut. "
            "Faster for large targets; requires pytest-cov (already installed)."
        ),
    )
    args = parser.parse_args()

    if args.list:
        list_targets()
        return

    if args.results:
        sys.exit(show_results())

    if args.target:
        sys.exit(run_target(args.target, use_coverage=args.use_coverage))

    parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_mutation_test_script.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Verify the script is executable end-to-end (dry check)**

```bash
python scripts/mutation_test.py --list
```

Expected output:
```
  core: interpreter/ir.py, interpreter/instructions.py, interpreter/register.py
  vm: interpreter/vm/
  handlers: interpreter/handlers/
  all-core: interpreter/ir.py, interpreter/instructions.py, interpreter/register.py, interpreter/vm/, interpreter/handlers/
```

```bash
python scripts/mutation_test.py --help
```

Expected: help text with all flags described.

- [ ] **Step 6: Run full unit suite to check nothing regressed**

```bash
poetry run python -m pytest tests/unit/ -x -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/mutation_test.py tests/unit/test_mutation_test_script.py
git commit -m "feat: add mutation_test.py helper script with --list, --target, --results, --use-coverage"
```

---

## Self-Review

**Spec coverage:**
- ✅ `mutmut` added as dev dependency (Task 1)
- ✅ `[tool.mutmut]` config with `runner` and `tests_dir`, no `paths_to_mutate` (Task 1)
- ✅ `.mutmut-cache` added to `.gitignore` (Task 1)
- ✅ `--list` flag (Task 2)
- ✅ `--target` flag with four named targets: `core`, `vm`, `handlers`, `all-core` (Task 2)
- ✅ `--results` flag (Task 2)
- ✅ `--use-coverage` optional flag (Task 2)
- ✅ Exit code propagated from mutmut (Task 2 — `sys.exit(run_target(...))`)
- ✅ No CI wiring

**Placeholder scan:** None found.

**Type consistency:** `TARGETS` is `dict[str, list[str]]` throughout. `run_target` returns `int` (exit code), used in `sys.exit()`. `show_results` returns `int`. Consistent everywhere.
