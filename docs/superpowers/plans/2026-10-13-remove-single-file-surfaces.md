# Remove the Single-File Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete `interpreter/api.py`, `mcp_server/`, `viz/` and the CLI's dump flags, keeping every test that covers something else, and record what was removed.

**Architecture:** Pure removal in red-dragon (`~/code/red-dragon`, never `vendor/red-dragon`). First free the three tests that use `api` only as a shortcut, then remove MCP, viz and `api` in separate commits, consumers before what they consume, each with its living-doc edits, then write the ADR and bead, then bump the forge.

**Tech Stack:** Python 3.13, uv, pytest (xdist), import-linter, python-fp-lint, Talisman, beads.

**Spec:** `docs/superpowers/specs/2026-10-13-remove-single-file-surfaces-design.md`

## Global Constraints

- Work in `~/code/red-dragon`; the forge's `vendor/red-dragon` changes only by submodule bump (Task 6).
- No `--no-verify`. If Talisman flags incidental wording, reword the line; do not touch `.talismanrc`.
- Specs and plans under `docs/superpowers/` and `docs/design/` are point-in-time: do not edit them.
- No test counts in living docs.
- `bd export -o issues/issues.jsonl` and stage it in any commit that changes an issue.
- `make test PYTEST_ARGS="-q"` is red-dragon's full suite (builds the ProLeap JAR first). Several minutes.

## Review Focus

- A test deleted with a removed module that actually covered a kept module — check each deleted test file's imports against the spec's list before deleting.
- `interpreter/__init__.py` re-exports: anything still importing `from interpreter import lower_source` (tests, scripts, docs) fails at import, not at collection of one file — run the full suite, not a subset.
- `run_linked_traced` must keep working with only `scripts/symbolic_trace_harness.py` and its moved test as callers.
- The forge's `uv.lock` pins `mcp` through red-dragon; the bump must re-lock or `uv sync` will disagree with the lock.
- README examples that survive must still run: every remaining snippet uses only names that exist.

---

### Task 1: Free the three tests from `api`; move the linked-traced test

**Files:**
- Move: `tests/unit/viz/test_run_linked_traced.py` → `tests/unit/test_run_linked_traced.py`
- Modify: `tests/unit/test_c_frontend.py:5,1150,1180`
- Modify: `tests/unit/test_pattern_index_registers.py:27,77,98,104-115`
- Modify: `tests/unit/test_step_budget_exhausted.py:7,41-51`

**Interfaces:**
- Produces: `tests.unit.test_run_linked_traced._build_linked_program(source: str, language: Language) -> LinkedProgram` (unchanged helper, new module path), used by Task 1's step-budget rewrite.

- [ ] **Step 1: Run the three tests and the linked-traced test as they are**

Run: `uv run --no-sync pytest -q -n0 tests/unit/test_c_frontend.py tests/unit/test_pattern_index_registers.py tests/unit/test_step_budget_exhausted.py tests/unit/viz/test_run_linked_traced.py 2>&1 | tail -2`
Expected: all pass. Record the count; Step 6 must match it.

- [ ] **Step 2: Move the linked-traced test**

```bash
git mv tests/unit/viz/test_run_linked_traced.py tests/unit/test_run_linked_traced.py
```

- [ ] **Step 3: Rewrite the C frontend's two CFG tests**

In `tests/unit/test_c_frontend.py` replace `from interpreter.api import build_cfg_from_source` with `from interpreter.cfg import build_cfg, extract_function_instructions` (drop the now-duplicate `from interpreter.cfg import build_cfg` line), add a module-level helper after the imports:

```python
def _function_cfg(source: str, function_name: str):
    instructions = get_frontend(Language.C).lower(source.encode("utf-8"))
    return build_cfg(extract_function_instructions(instructions, function_name))
```

and replace the two calls:

```python
cfg = _function_cfg(source, "test_func")
```

```python
cfg = _function_cfg(source, "test_complex")
```

- [ ] **Step 4: Rewrite the pattern-index register tests**

In `tests/unit/test_pattern_index_registers.py` replace `from interpreter.api import lower_source` with `from interpreter.frontend import get_frontend` and `from interpreter.run import run`; replace both `ir = lower_source(source, language)` with

```python
ir = get_frontend(language).lower(source.encode("utf-8"))
```

and replace the body of `test_pattern_matching_still_computes_the_right_answers` with

```python
    vm = run(PATTERN_SOURCE, language=Language.PYTHON, max_steps=5000)
    values = {str(name): tv.value for name, tv in vm.call_stack[0].local_vars.items()}
    assert values["r1"] == 7, f"[3, 4] -> a + b should be 7, got {values['r1']!r}"
    assert (
        values["r2"] == 10
    ), f"[2, 5, 9, 9] -> p * q should be 10, got {values['r2']!r}"
```

- [ ] **Step 5: Rewrite the two traced step-budget tests**

In `tests/unit/test_step_budget_exhausted.py` replace `from interpreter.api import execute_traced` with

```python
from interpreter.constants import Language
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run_linked_traced
from tests.unit.test_run_linked_traced import _build_linked_program
```

and the two `execute_traced(...)` calls with

```python
run_linked_traced(
    _build_linked_program(INFINITE_LOOP, Language.PYTHON),
    entry_point=EntryPoint.top_level(),
    max_steps=50,
)
```

```python
run_linked_traced(
    _build_linked_program(TERMINATING, Language.PYTHON),
    entry_point=EntryPoint.top_level(),
    max_steps=500,
)
```

- [ ] **Step 6: Run the rewritten tests**

Run: `uv run --no-sync pytest -q -n0 tests/unit/test_c_frontend.py tests/unit/test_pattern_index_registers.py tests/unit/test_step_budget_exhausted.py tests/unit/test_run_linked_traced.py 2>&1 | tail -2`
Expected: same count as Step 1, all pass.

- [ ] **Step 7: Mutation-check the traced budget rewrite**

In `test_traced_execution_warns_when_budget_exhausted`, change `INFINITE_LOOP` to `TERMINATING`, run the file, confirm that test fails, then revert.
Run: `uv run --no-sync pytest -q -n0 tests/unit/test_step_budget_exhausted.py 2>&1 | tail -1`
Expected: with the mutation, that one test fails and the other three succeed; after the revert, all four succeed.

- [ ] **Step 8: Confirm nothing in these files imports `interpreter.api`**

Run: `rg -n "interpreter.api" tests/unit/test_c_frontend.py tests/unit/test_pattern_index_registers.py tests/unit/test_step_budget_exhausted.py tests/unit/test_run_linked_traced.py`
Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add -A tests/unit
git commit -m "test: reach frontends and run() directly instead of through api

```

---

### Task 2: Remove `mcp_server/`

**Files:**
- Delete: `mcp_server/`, `tests/unit/test_mcp_tools.py`, `tests/unit/test_mcp_formatting.py`, `tests/unit/project/test_mcp_tool.py`, `tests/integration/test_mcp_server.py`
- Modify: `pyproject.toml` (the `mcp[cli]` dependency), `uv.lock`, `pyrightconfig.json` (`include`), `README.md` (`### MCP Server`), `docs/linker-design.md` (MCP rows), `guidelines/project-context.md:8`

- [ ] **Step 1: Confirm nothing else imports it**

Run: `rg -l "mcp_server" --type py . | grep -v "^./mcp_server/" | sort`
Expected: only the four test files above, plus any `viz/` files (those go in Task 3).

- [ ] **Step 2: Delete and de-configure**

```bash
git rm -rq mcp_server tests/unit/test_mcp_tools.py tests/unit/test_mcp_formatting.py tests/unit/project/test_mcp_tool.py tests/integration/test_mcp_server.py
```

Remove the line `"mcp[cli] (>=1.26.0,<2.0.0)",` from `pyproject.toml`; change `pyrightconfig.json` `"include": ["interpreter", "cobol_asg", "mcp_server"]` to `"include": ["interpreter", "cobol_asg"]`. Then:

Run: `uv lock 2>&1 | tail -2 && rg -c '^name = "mcp"' uv.lock`
Expected: lock updates; count `0` (rg exits 1 with no output is also correct).

- [ ] **Step 3: Docs**

- README: delete the `### MCP Server` section through the closing ```` ``` ```` of its JSON block.
- `docs/linker-design.md`: delete the `handle_load_project` entry-points row and the two `mcp_server/...` lines in the file map.
- `guidelines/project-context.md:8`: "over `interpreter`, `cobol_asg`, `mcp_server`, with" → "over `interpreter`, `cobol_asg`, with".

- [ ] **Step 4: Check and gate**

Run: `rg -n "mcp_server|MCP server|MCP Server|load_project|handle_load" --glob '!docs/superpowers/**' --glob '!docs/design/**' --glob '!docs/architectural-design-decisions.md' --glob '!issues/**' --glob '!guidelines/code-search-tools.md' --glob '!viz/**' . ; make test PYTEST_ARGS="-q" > /tmp/rd-task3.log 2>&1; tail -2 /tmp/rd-task3.log`
Expected: no `rg` output; suite green.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove the MCP server

```

---

### Task 3: Remove `viz/`

**Files:**
- Delete: `viz/`, `tests/unit/viz/`, `tests/integration/viz/`, `docs/pipeline-viz.cast`, `docs/pipeline-viz.gif`
- Modify: `pyproject.toml` (the `textual` dev dependency), `uv.lock`, `README.md` (`### Pipeline visualisation`, `### Built-in pipeline visualizer`), `guidelines/project-context.md:41`

- [ ] **Step 1: Confirm nothing else imports it**

Run: `rg -l "from viz|import viz|textual" --type py . | grep -v "^./viz/\|^./tests/\(unit\|integration\)/viz/" | sort`
Expected: no output.

- [ ] **Step 2: Delete and de-configure**

```bash
git rm -rq viz tests/unit/viz tests/integration/viz docs/pipeline-viz.cast docs/pipeline-viz.gif
```

Remove the line `"textual>=8.1.0",` from `pyproject.toml`.
Run: `uv lock 2>&1 | tail -2 && rg -c '^name = "textual"' uv.lock`
Expected: count `0` (or no output).

- [ ] **Step 3: Docs**

- README: delete `### Pipeline visualisation` and `### Built-in pipeline visualizer` through the paragraph ending "…language-specific (`✓`) or shared (`✓*`)."
- `guidelines/project-context.md:41`: "- Pydantic — boundary parsing; textual — the TUI" → "- Pydantic — boundary parsing".

- [ ] **Step 4: Check and gate**

Run: `rg -n "\bviz\b|textual|pipeline-viz" --glob '!docs/superpowers/**' --glob '!docs/design/**' --glob '!docs/architectural-design-decisions.md' --glob '!issues/**' --glob '!uv.lock' .`
Expected: no output.
Run: `uv run --no-sync lint-imports 2>&1 | tail -1; uv run --no-sync python -m python_fp_lint check --config fp.json interpreter/ cobol_asg/ 2>&1 | tail -1; make test PYTEST_ARGS="-q" > /tmp/rd-task4.log 2>&1; tail -2 /tmp/rd-task4.log`
Expected: contracts kept; fp-lint total not above `fp-baseline.json`; suite green.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove the viz TUI

```

---

### Task 4: Remove `interpreter/api.py`, `ir_stats`, the re-exports and the CLI dump flags

**Files:**
- Delete: `interpreter/api.py`, `interpreter/ir_stats.py`, `scripts/demo_type_inference_tier2.py`, `scripts/demo_type_inference_tier3.py`, `scripts/demo_multifile_project.py`, `tests/unit/test_api.py`, `tests/unit/test_ir_stats.py`, `tests/integration/project/test_api_integration.py`, `tests/unit/demos/test_type_inference_tier2.py`, `tests/unit/demos/test_type_inference_tier3.py`
- Modify: `interpreter/__init__.py`, `interpreter.py`, `README.md`, `docs/notes-on-vm-design.md:564`, `docs/linker-design.md` (the `run_project` rows)

**Interfaces:**
- Consumes: Task 1 (no kept test imports `interpreter.api`); Tasks 2–3 (MCP and viz, its other importers, are gone).
- Produces: `interpreter` package exports only `ExecutionStats`, `VMConfig`, `execute_cfg`, `run`.

- [ ] **Step 1: Confirm the deletion list is complete**

Run: `rg -l "interpreter\.api|from interpreter import (lower_source|lower_and_infer|dump_ir|build_cfg_from_source|dump_cfg|dump_mermaid|extract_function_source|ir_stats)|interpreter\.ir_stats|count_opcodes" --type py . | sort`
Expected: exactly the files in this task's Delete and Modify lists that are Python, plus `tests/unit/demos/__init__.py` only if it imports them (it should not). Anything else: stop and add it to the list with a ruling.

- [ ] **Step 2: Delete the files**

```bash
git rm -q interpreter/api.py interpreter/ir_stats.py \
  scripts/demo_type_inference_tier2.py scripts/demo_type_inference_tier3.py scripts/demo_multifile_project.py \
  tests/unit/test_api.py tests/unit/test_ir_stats.py tests/integration/project/test_api_integration.py \
  tests/unit/demos/test_type_inference_tier2.py tests/unit/demos/test_type_inference_tier3.py
```

If `tests/unit/demos/` now holds only `__init__.py`, `git rm` that too.

- [ ] **Step 3: Drop the re-exports**

`interpreter/__init__.py` becomes:

```python
"""LLM Symbolic Interpreter package."""

from interpreter.run import ExecutionStats, VMConfig, execute_cfg, run  # noqa: F401
```

- [ ] **Step 4: Drop the CLI dump flags**

In `interpreter.py`: delete the `from interpreter.api import (dump_cfg, dump_ir, dump_mermaid)` import; delete the `add_argument` calls for `--ir-only`, `--cfg-only`, `--mermaid` and `--function`; delete the three `if args.ir_only:` / `if args.mermaid:` / `if args.cfg_only:` blocks. Keep everything else.

Run: `uv run --no-sync python interpreter.py --help | rg -c "ir-only|cfg-only|mermaid|--function"; uv run --no-sync python interpreter.py 2>&1 | tail -3`
Expected: `0`, then the built-in factorial demo runs to completion.

- [ ] **Step 5: Update the README**

- Usage block: delete the `--ir-only`, `--cfg-only` and `--mermaid --function foo` lines; delete the four table rows `--ir-only`, `--cfg-only`, `--mermaid`, `--function`.
- Replace the whole `### Programmatic API` section, through the paragraph ending "…with VMState snapshots at each instruction.", with:

````markdown
### Programmatic API

```python
from interpreter import run
from interpreter.constants import Language

source = """
def factorial(n):
    if n <= 1:
        return n
    return n * factorial(n - 1)
result = factorial(6)
"""

vm = run(source, language=Language.PYTHON, verbose=True)
print(vm.call_stack[0].local_vars["result"])  # 720
```

With an LLM resolving external calls the deterministic frontend cannot:

```python
from interpreter import run
from interpreter.constants import Language
from interpreter.run_types import UnresolvedCallStrategy

vm = run(
    "import math\nx = math.sqrt(16)\ny = math.floor(7.8)\n",
    language=Language.PYTHON,
    unresolved_call_strategy=UnresolvedCallStrategy.LLM,
    backend="claude",
)
```

`execute_cfg` runs a pre-built CFG:

```python
from interpreter import execute_cfg, VMConfig
from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.registry import build_registry

instructions = get_frontend(Language.PYTHON).lower(source.encode("utf-8"))
cfg = build_cfg(instructions)
registry = build_registry(instructions, cfg)
vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))
```
````

- In `### Multi-file project support` replace the `run_project` snippet with:

````markdown
```python
from pathlib import Path

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run_linked

linked = compile_directory(Path("src"), Language.PYTHON)
vm = run_linked(linked, EntryPoint.top_level(), max_steps=500)
```
````

- Coverage list: delete the `**Composable API**` bullet; in the `**Multi-file projects**` bullet change "multi-file VM execution for every language, API and MCP integration" to "multi-file VM execution for every language".

- [ ] **Step 6: Update the other living docs**

- `docs/notes-on-vm-design.md:564`: "IR from the Python frontend (`dump_ir`), as CFG blocks:" → "IR from the Python frontend, as CFG blocks:".
- `docs/linker-design.md`: delete the entry-points row for `run_project` and the two-line `interpreter/api.py` / `run_project()` block in the file map.

- [ ] **Step 7: Check the whole removal**

Run: `rg -n "\bviz\b|textual|pipeline-viz|mcp_server|interpreter\.api|interpreter/api\.py|interpreter\.ir_stats|lower_source|lower_and_infer|dump_ir|build_cfg_from_source|dump_cfg|dump_mermaid|extract_function_source|ir_stats|execute_traced|run_project|--ir-only|--cfg-only|--mermaid" --glob '!docs/superpowers/**' --glob '!docs/design/**' --glob '!docs/architectural-design-decisions.md' --glob '!issues/**' --glob '!uv.lock' .`
Expected: no output.

- [ ] **Step 8: Gate**

Run: `uv run --no-sync lint-imports 2>&1 | tail -1; uv run --no-sync python -m python_fp_lint check --config fp.json interpreter/ cobol_asg/ 2>&1 | tail -1; make test PYTEST_ARGS="-q" > /tmp/rd-task4.log 2>&1; tail -2 /tmp/rd-task4.log`
Expected: `Contracts: 8 kept, 0 broken.`; fp-lint total not above `fp-baseline.json`; suite green.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: remove interpreter.api, ir_stats and the CLI dump flags

```

---

### Task 5: Record the removal (ADR-180) and file the rebuild bead

**Files:**
- Modify: `docs/architectural-design-decisions.md` (append ADR-180)
- Modify: `issues/issues.jsonl`

- [ ] **Step 1: File the bead**

```bash
bd create "Rebuild IR, CFG and Mermaid dumps on the fully linked program" -t feature -p 3 \
  -d "ADR-180 removed the CLI's --ir-only, --cfg-only, --mermaid and --function, which printed one file's IR or CFG from single-file lowering. Rebuild them on the LinkedProgram that the multi-file compile core produces (merged_ir, merged_cfg), after spec 2 of the single-pipeline work lands. Restore source for the old behaviour: interpreter/api.py at the parent of the removal commits." --silent
```

Record the printed id as `<BEAD>`.

- [ ] **Step 2: Append ADR-180**

Append to `docs/architectural-design-decisions.md`, with `<BASE>` = the commit before Task 2 (`git log --format=%h -1 <Task 2 commit>^`), the last commit with all six surfaces and `<BEAD>` from Step 1:

```markdown

---

### ADR-180: Remove the single-file surfaces (2026-10-13)

**Context:** Non-COBOL code compiled two ways: `run()` hand-built a one-module `LinkedProgram` from one string, and `compile_directory` compiled and linked files. The same program got different labels from each. Six surfaces sat on the single-file side or wrapped it, and rewiring each onto one compile core was not worth it for code nothing outside this repo used.

**Decision:** Delete them. To restore any of them, start from `<BASE>`.

| Surface | What it did |
|---|---|
| `interpreter/api.py` | `lower_source` (string → IR), `lower_and_infer` (IR plus type environment), `dump_ir`, `build_cfg_from_source` (CFG, optionally one function), `dump_cfg`, `dump_mermaid`, `ir_stats`, `execute_traced` (one-module traced run), `extract_function_source` (a function's source via tree-sitter), `run_project` (directory → `compile_directory` → `execute_cfg`); eight of them re-exported from `interpreter` |
| `interpreter/ir_stats.py` | `count_opcodes`, used only by `api.ir_stats` |
| `mcp_server/` | MCP tools `load_program`, `step`, `run_to_end`, `get_state`, `get_ir`, `load_project`, `list_opcodes`; resources for source, IR and CFG |
| `viz/` | Textual TUI: single-file pipeline stepping, cross-language compare, lowering trace, frontend coverage matrix, project mode over `compile_directory` |
| CLI `--ir-only`, `--cfg-only`, `--mermaid`, `--function` | Print one file's IR, CFG or Mermaid CFG and exit |
| Demo scripts | `demo_type_inference_tier2/3.py`, `demo_multifile_project.py` |

**Consequences:** The CLI only runs programs. `interpreter` exports `run`, `execute_cfg`, `VMConfig`, `ExecutionStats`. The `mcp` and `textual` dependencies are gone. IR, CFG and Mermaid dumps come back on the fully linked program only (<BEAD>).
```

- [ ] **Step 3: Export and commit**

```bash
bd export -o issues/issues.jsonl
git add docs/architectural-design-decisions.md issues/issues.jsonl
git commit -m "docs(adr): ADR-180 records the removed single-file surfaces

git push origin main
```

Expected: push succeeds; `git status -sb` shows `## main...origin/main`.

---

### Task 6: Bump the forge

**Files (in `~/code/red-dragon-forge`):**
- Modify: `vendor/red-dragon` (submodule), `uv.lock`

- [ ] **Step 1: Move the submodule**

```bash
cd ~/code/red-dragon-forge
git -C vendor/red-dragon fetch -q origin && git -C vendor/red-dragon checkout -q origin/main
uv lock 2>&1 | tail -2
rg -c '^name = "mcp"' uv.lock
```

Expected: the lock drops `mcp` (count `0` or no output). `textual` was a red-dragon dev dependency and should not have been in the forge lock.

- [ ] **Step 2: Confirm the forge never used the removed surfaces**

Run: `rg -n "interpreter\.api|mcp_server|from viz|from interpreter import (lower_source|dump_ir|lower_and_infer)" --type py -g '!vendor/**' .`
Expected: no output.

- [ ] **Step 3: Gate**

Run (background, timeout 40 min): `. ./bridge-env.sh && make test-all > /tmp/forge-test-all.log 2>&1; grep -E "[0-9]+ (passed|failed)" /tmp/forge-test-all.log`
Expected: cicada, squall, jackal, cobble and root suites all pass.

- [ ] **Step 4: Commit and push**

```bash
git add vendor/red-dragon uv.lock
git commit -m "chore(vendor): bump red-dragon; api, MCP server and viz removed upstream

git push origin main
```
