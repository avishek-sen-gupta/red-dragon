# Mutation Testing Infrastructure — Design Spec

**Date:** 2026-06-03
**Status:** Approved for implementation

---

## Overview

Add mutation testing infrastructure to RedDragon so the quality of the existing ~13k-test suite can be measured and improved over time. The target is mutation testing **of RedDragon itself** (its Python source), not of programs it analyses.

Tool: **mutmut**. Results stored in a local SQLite cache (`.mutmut-cache`), persistent between sessions. Run manually on demand; no CI integration yet.

---

## Scope

Initial scope is the high-value core IR/VM layer — the modules where an undetected mutant has the widest blast radius:

| Target name | Paths |
|-------------|-------|
| `core` | `interpreter/ir.py`, `interpreter/instructions.py`, `interpreter/register.py` |
| `vm` | `interpreter/vm/` |
| `handlers` | `interpreter/handlers/` |
| `all-core` | all of the above combined |

Additional targets (e.g. `cobol`, `types`, `frontends`) can be added later by extending the dict in the helper script.

---

## New Files

- `scripts/mutation_test.py` — helper script (the primary interface)

## Modified Files

- `pyproject.toml` — add mutmut dev dependency + `[tool.mutmut]` config
- `.gitignore` — add `.mutmut-cache`

---

## Configuration (`pyproject.toml`)

```toml
[tool.mutmut]
runner = "poetry run python -m pytest tests/ -x -q --tb=no"
tests_dir = "tests/"
```

`paths_to_mutate` is deliberately absent — always supplied per-run by the script to prevent accidental whole-codebase mutations. `-x` stops on first test failure (fast kill). `--tb=no` keeps mutmut's output readable.

mutmut is installed as a poetry dev dependency:

```toml
[tool.poetry.dev-dependencies]
mutmut = ">=2.4"
```

---

## Cache (`gitignore`)

`.mutmut-cache` (SQLite) is local state — not committed. Add to `.gitignore`:

```
.mutmut-cache
```

Runs can be interrupted and resumed; the cache persists across sessions.

---

## Helper Script (`scripts/mutation_test.py`)

### Interface

```
python scripts/mutation_test.py --list                       # print all targets and their paths
python scripts/mutation_test.py --target vm                  # run mutmut on interpreter/vm/
python scripts/mutation_test.py --target core                # run mutmut on core IR files
python scripts/mutation_test.py --target all-core            # run all four target paths
python scripts/mutation_test.py --results                    # print summary from last run
python scripts/mutation_test.py --target vm --use-coverage   # coverage-guided run (faster)
```

### `--target <name>` (primary mode)

Shells out to:
```
poetry run mutmut run --paths-to-mutate=<paths>
```

Where `<paths>` is the comma-joined list for the named target.

### `--results`

Shells out to:
```
poetry run mutmut results
```

Prints the surviving/killed/timeout/suspicious mutant summary from the last run. Works across targets (mutmut cache is shared).

### `--list`

Prints each target name and its paths. Self-documenting; no args to remember.

### `--use-coverage` (optional, off by default)

When passed alongside `--target`:
1. Runs `poetry run python -m pytest --cov=<target-paths> tests/ -q --tb=no` to generate `.coverage`
2. Adds `--use-coverage` to the mutmut invocation

mutmut then only runs tests that cover each mutant — significantly faster for large targets. Requires `pytest-cov` (already a dev dependency if present; add it if not).

### Exit code

The script exits with mutmut's return code so a future `--target core` CI step requires no rewiring.

---

## Workflow

**First run on a target:**
```bash
python scripts/mutation_test.py --target core
# runs for a while; results in .mutmut-cache
python scripts/mutation_test.py --results
```

**Resuming an interrupted run:**
```bash
# mutmut automatically resumes from where it left off
python scripts/mutation_test.py --target core
```

**Generating an HTML report (manual, any time):**
```bash
poetry run mutmut html
# opens html/ directory in browser
```

**Adding a new target later:**
Edit `TARGETS` dict in `scripts/mutation_test.py`:
```python
TARGETS["cobol"] = ["interpreter/cobol/"]
```

---

## Out of Scope

- CI integration (deferred)
- Mutation score thresholds / quality gates (deferred)
- Automatic test generation for surviving mutants (deferred)
- Mutating `scripts/`, `tests/`, or `mcp_server/` (not in initial scope)
