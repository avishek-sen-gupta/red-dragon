# Type Annotation Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all untyped `Any` across `interpreter/` and `mcp_server/`, establish `pyright standard` as a hard CI gate, and file a `pre_triage` backlog of domain-type migration candidates for async review.

**Architecture:** Per-file opt-in migration — `pyrightconfig.json` stays at `basic`; each file gets `# pyright: standard` added once its `Any` usages are replaced and all annotations are complete. Phase 3 upgrades the global config after all files are promoted. `HandlerContext` stays in `executor.py`; handlers import it via `TYPE_CHECKING` guard to avoid circular imports.

**Tech Stack:** Python 3.13, pyright ^1.1.408, Beads (`bd`) issue tracker, poetry

---

## Pre-Task Reference

### Filing a pre_triage issue

```bash
bd create "TITLE" \
  --description="File: interpreter/path/to/file.py\nSymbol: some_param: str\nContext: [explain what it is and why it might need a domain type]\nEpic: <epic-id>" \
  -t task -p 3
bd update <new-id> --status pre_triage
bd update <new-id> --parent <epic-id>
```

### The annotation commit pattern (every annotation task)

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add <files>
git commit -m "types: annotate interpreter/<module> — Any eliminated"
```

### The `TYPE_CHECKING` guard pattern (for circular-import-safe annotations)

Use this in `interpreter/handlers/*.py` to import `HandlerContext` without creating a runtime circular import (`executor.py` imports from `handlers/`):

```python
from __future__ import annotations  # must be first non-docstring line
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interpreter.vm.executor import HandlerContext
```

With `from __future__ import annotations` active, `ctx: HandlerContext` is stored as the string `"HandlerContext"` at runtime — Python never evaluates it, so the import under `TYPE_CHECKING` is never needed at runtime.

---

## Task 1: Phase 1 — Gate setup

**Files:**
- Modify: `pyrightconfig.json`
- Modify: `.claude/core/workflow.md`
- Modify: `.beads/` (via `bd` CLI)

- [ ] **Step 1: Configure the `pre_triage` Beads status**

```bash
bd config set status.custom "pre_triage:frozen"
```

Verify: `bd statuses` shows `pre_triage` in the list.

- [ ] **Step 2: File the triage epic**

```bash
bd create "Type annotation triage — domain type and union candidates" \
  --description="Epic tracking all pre_triage issues filed during the type annotation pass. Each child issue represents a primitive type or union type discovered during annotation that may warrant a domain type migration or unification. Issues are promoted to 'open' only after explicit discussion; closed with 'no action needed' otherwise." \
  -t task -p 2
```

Record the epic ID (e.g., `red-dragon-XYZ`). All subsequent pre_triage issues use this as `--parent`.

- [ ] **Step 3: Add `mcp_server/` to pyrightconfig.json**

Current `pyrightconfig.json`:
```json
{
    "include": ["interpreter"],
    "exclude": ["**/grammars/**", "**/__pycache__/**"],
    "typeCheckingMode": "basic",
    "pythonVersion": "3.13",
    "reportMissingImports": true,
    "reportMissingTypeStubs": false,
    "reportUnusedImport": false,
    "reportUnusedVariable": false
}
```

Updated:
```json
{
    "include": ["interpreter", "mcp_server"],
    "exclude": ["**/grammars/**", "**/__pycache__/**"],
    "typeCheckingMode": "basic",
    "pythonVersion": "3.13",
    "reportMissingImports": true,
    "reportMissingTypeStubs": false,
    "reportUnusedImport": false,
    "reportUnusedVariable": false
}
```

- [ ] **Step 4: Add pyright to the verification gate**

In `.claude/core/workflow.md`, add `poetry run pyright interpreter/ mcp_server/` to the verification gate block:

```markdown
### Verification gate

Run all four before every commit, in this order:

```bash
poetry run python -m black .         # formatting
poetry run lint-imports               # architectural contracts
poetry run pyright interpreter/ mcp_server/  # type checking (basic mode initially)
poetry run python -m pytest tests/    # ALL tests (unit + integration), not just tests/unit/
```
```

- [ ] **Step 5: Verify pyright runs cleanly (basic mode baseline)**

```bash
poetry run pyright interpreter/ mcp_server/
```

Expected: 1,042 errors (baseline). The gate is live but not yet blocking — it will block once all files carry `# pyright: standard`.

- [ ] **Step 6: Commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add pyrightconfig.json .claude/core/workflow.md
git commit -m "chore: add pyright gate and pre_triage Beads status; include mcp_server/ in type check"
```

---

## Task 2: `interpreter/types/coercion/` annotation

**Files:**
- Modify: `interpreter/types/coercion/binop_coercion.py`
- Modify: `interpreter/types/coercion/conversion_result.py`
- Modify: `interpreter/types/coercion/conversion_rules.py`
- Modify: `interpreter/types/coercion/default_conversion_rules.py`
- Modify: `interpreter/types/coercion/identity_conversion_rules.py`
- Modify: `interpreter/types/coercion/type_compatibility.py`
- Modify: `interpreter/types/coercion/unop_coercion.py`

**Key pattern — coercer `Callable[[Any], Any]`:**

`_identity` and all coercer fields in `ConversionResult` take and return raw runtime values. These are heterogeneous at this stage. Keep `Any` but document it explicitly and file a pre_triage issue:

```python
# Before
def _identity(x: Any) -> Any:
    return x

left_coercer: Callable[[Any], Any] = _identity

# After
def _identity(x: Any) -> Any:  # Any: display boundary — coerces heterogeneous runtime values
    return x

left_coercer: Callable[[Any], Any] = _identity  # Any: display boundary — see pre_triage issue
```

File one pre_triage issue: "What is the type of a coercer argument? Define RuntimeValue TypeAlias?"

- [ ] **Step 1: Annotate all functions in each file**

For each file: add missing return types, add missing parameter types, replace bare `Any` with concrete types where possible. Document `Callable[[Any], Any]` uses as display boundaries. Apply `# pyright: standard` to each file header.

Run after each file:
```bash
poetry run pyright interpreter/types/coercion/<filename>.py
```
Expected: 0 errors for that file.

- [ ] **Step 2: File pre_triage issues for all flagged Any uses**

Use the pattern from the Pre-Task Reference. Link each to the epic.

- [ ] **Step 3: Verify the module**

```bash
poetry run pyright interpreter/types/coercion/
```
Expected: 0 errors.

- [ ] **Step 4: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/types/coercion/
git commit -m "types: annotate interpreter/types/coercion/ — Any eliminated"
```

---

## Task 3: `interpreter/types/` annotation

**Files:**
- Modify: `interpreter/types/function_kind.py`
- Modify: `interpreter/types/function_signature.py`
- Modify: `interpreter/types/null_type_resolver.py`
- Modify: `interpreter/types/type_environment.py`
- Modify: `interpreter/types/type_environment_builder.py`
- Modify: `interpreter/types/type_expr.py`
- Modify: `interpreter/types/type_graph.py`
- Modify: `interpreter/types/type_inference.py`
- Modify: `interpreter/types/type_node.py`
- Modify: `interpreter/types/type_resolver.py`
- Modify: `interpreter/types/typed_value.py`
- Modify: `interpreter/types/var_scope_info.py`

**Key pattern — `Callable[[Any], Any]` in type resolvers:**

`type_resolver.py` and `null_type_resolver.py` return `Callable[[Any], Any]`. These are type resolution functions that transform values — file as pre_triage, document as display boundary for now.

- [ ] **Step 1: Annotate all functions in each file, add `# pyright: standard` to each header**

Run after each file:
```bash
poetry run pyright interpreter/types/<filename>.py
```

- [ ] **Step 2: File pre_triage issues for flagged Any uses**

- [ ] **Step 3: Verify the module**

```bash
poetry run pyright interpreter/types/
```
Expected: 0 errors.

- [ ] **Step 4: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/types/
git commit -m "types: annotate interpreter/types/ — Any eliminated"
```

---

## Task 4: `interpreter/refs/` annotation

**Files:**
- Modify: `interpreter/refs/func_ref.py`
- Modify: `interpreter/refs/class_ref.py`

These files define `FuncRef`, `BoundFuncRef`, `ClassRef`. They are likely already well-typed. Add missing return types, add `# pyright: standard`, fix any issues pyright surfaces.

- [ ] **Step 1: Annotate both files, add `# pyright: standard`**

```bash
poetry run pyright interpreter/refs/
```
Expected: 0 errors.

- [ ] **Step 2: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/refs/
git commit -m "types: annotate interpreter/refs/ — Any eliminated"
```

---

## Task 5: Root-level domain type files

**Files (small, group into one commit):**
- Modify: `interpreter/address.py`
- Modify: `interpreter/class_name.py`
- Modify: `interpreter/closure_id.py`
- Modify: `interpreter/constants.py`
- Modify: `interpreter/continuation_name.py`
- Modify: `interpreter/field_name.py`
- Modify: `interpreter/func_name.py`
- Modify: `interpreter/frontend_observer.py`
- Modify: `interpreter/ir_stats.py`
- Modify: `interpreter/operator_kind.py`
- Modify: `interpreter/register.py`
- Modify: `interpreter/storage_identifier.py`
- Modify: `interpreter/var_name.py`

These are small domain-type files. Most are likely already well-typed. Add any missing return types, add `# pyright: standard` to each.

- [ ] **Step 1: Annotate all files, add `# pyright: standard` to each**

```bash
poetry run pyright interpreter/address.py interpreter/class_name.py interpreter/closure_id.py \
  interpreter/constants.py interpreter/continuation_name.py interpreter/field_name.py \
  interpreter/func_name.py interpreter/frontend_observer.py interpreter/ir_stats.py \
  interpreter/operator_kind.py interpreter/register.py interpreter/storage_identifier.py \
  interpreter/var_name.py
```
Expected: 0 errors across all files.

- [ ] **Step 2: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/address.py interpreter/class_name.py interpreter/closure_id.py \
  interpreter/constants.py interpreter/continuation_name.py interpreter/field_name.py \
  interpreter/func_name.py interpreter/frontend_observer.py interpreter/ir_stats.py \
  interpreter/operator_kind.py interpreter/register.py interpreter/storage_identifier.py \
  interpreter/var_name.py
git commit -m "types: annotate root-level domain type files — Any eliminated"
```

---

## Task 6: Root-level core files

**Files:**
- Modify: `interpreter/cfg_types.py`
- Modify: `interpreter/cfg.py`
- Modify: `interpreter/instructions.py`
- Modify: `interpreter/ir.py`

These are the core IR and CFG types. `instructions.py` already uses typed `Callable[[Register], Register]` and `Callable[[CodeLabel], CodeLabel]` — these are correct. Add missing annotations, add `# pyright: standard`.

- [ ] **Step 1: Annotate `interpreter/cfg_types.py` and `interpreter/cfg.py`, add `# pyright: standard`**

```bash
poetry run pyright interpreter/cfg_types.py interpreter/cfg.py
```

- [ ] **Step 2: Annotate `interpreter/instructions.py`, add `# pyright: standard`**

```bash
poetry run pyright interpreter/instructions.py
```

- [ ] **Step 3: Annotate `interpreter/ir.py`, add `# pyright: standard`**

`ir.py` defines `Opcode`, `CodeLabel`, `SpreadArguments` etc. Add missing return types throughout.

```bash
poetry run pyright interpreter/ir.py
```

- [ ] **Step 4: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/cfg_types.py interpreter/cfg.py interpreter/instructions.py interpreter/ir.py
git commit -m "types: annotate root-level core files (cfg, ir, instructions) — Any eliminated"
```

---

## Task 7: Root-level data types (`run_types.py`, `trace_types.py`)

**Files:**
- Modify: `interpreter/run_types.py`
- Modify: `interpreter/trace_types.py`

**Key pattern — `io_provider: Any` in `run_types.py`:**

`io_provider: Any = None` is intentionally `Any` to avoid importing the COBOL module from the core VM. This is a legitimate design isolation choice. Document it and file pre_triage:

```python
# After
io_provider: Any = None  # Any: COBOL isolation boundary — CobolIOProvider avoided in core VM
```

File pre_triage: "io_provider: Any in VMConfig — should this be a Protocol to avoid COBOL coupling?"

**Key pattern — `instruction: Any`, `update: Any`, `vm_state: Any` in `trace_types.py`:**

These use `Any` to avoid circular imports (`trace_types` would import from `vm`, which imports from `trace_types`). Fix with `TYPE_CHECKING`:

```python
# Before
from typing import Any

instruction: Any  # InstructionBase
update: Any  # StateUpdate
vm_state: Any  # deep-copied VMState after applying update
initial_state: Any = None  # VMState before any instruction

# After
from __future__ import annotations  # already present
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interpreter.instructions import InstructionBase
    from interpreter.vm.vm import VMState, StateUpdate

instruction: InstructionBase
update: StateUpdate
vm_state: VMState
initial_state: VMState | None = None
```

First verify that `interpreter.trace_types` is not imported by `interpreter.vm.vm` or `interpreter.instructions` (that would make `TYPE_CHECKING` circular). If it is, keep `Any` with documentation and file a pre_triage issue instead.

```bash
grep -rn "from interpreter.trace_types\|import trace_types" interpreter/vm/ interpreter/instructions.py
```

- [ ] **Step 1: Annotate `interpreter/run_types.py`, add `# pyright: standard`**

```bash
poetry run pyright interpreter/run_types.py
```

- [ ] **Step 2: Check for circular imports before annotating `trace_types.py`**

```bash
grep -rn "from interpreter.trace_types\|import trace_types" interpreter/vm/ interpreter/instructions.py
```

If no results: proceed with `TYPE_CHECKING` pattern. If circular: keep `Any` with documentation, file pre_triage.

- [ ] **Step 3: Annotate `interpreter/trace_types.py`, add `# pyright: standard`**

```bash
poetry run pyright interpreter/trace_types.py
```

- [ ] **Step 4: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/run_types.py interpreter/trace_types.py
git commit -m "types: annotate run_types and trace_types — Any eliminated where possible"
```

---

## Task 8: `interpreter/handlers/` annotation (highest leverage)

**Files:**
- Modify: `interpreter/handlers/_common.py`
- Modify: `interpreter/handlers/arithmetic.py`
- Modify: `interpreter/handlers/calls.py`
- Modify: `interpreter/handlers/control_flow.py`
- Modify: `interpreter/handlers/memory.py`
- Modify: `interpreter/handlers/objects.py`
- Modify: `interpreter/handlers/regions.py`
- Modify: `interpreter/handlers/variables.py`

This is the highest-leverage task. `ctx: Any` → `ctx: HandlerContext` across 33 occurrences. Expected to resolve ~742 `reportArgumentType` errors once pyright can see the concrete type.

**Key pattern — `ctx: Any` → `ctx: HandlerContext`:**

`executor.py` imports from `handlers/` (late import, line 125+). Handlers must NOT import from `executor.py` at runtime. Use `TYPE_CHECKING`:

```python
# Add to the top of EVERY handler file:
from __future__ import annotations  # if not already present — must be first line after docstring
from typing import TYPE_CHECKING

# Add in the TYPE_CHECKING block:
if TYPE_CHECKING:
    from interpreter.vm.executor import HandlerContext

# Then replace every:
def _handle_binop(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
# With:
def _handle_binop(inst: InstructionBase, vm: VMState, ctx: HandlerContext) -> ExecutionResult:
```

**Other Any patterns in `calls.py`:**

```python
# dict[VarName, Any] — values are TypedValue or raw runtime values
new_vars: dict[VarName, Any] = {}
captured: dict[VarName, Any] = {}
# File pre_triage: "dict[VarName, Any] in calls.py — should value be TypedValue?"

# func_val: Any — union of FuncRef | BoundFuncRef | ClassRef | Callable
func_val: Any
# File pre_triage: "func_val: Any in calls.py — union of callable reference types"
```

**Other Any patterns in `memory.py`:**

```python
# idx_val: Any in _infer_index_kind — could be str | int
def _infer_index_kind(idx_val: Any) -> FieldKind:
# File pre_triage: "idx_val: Any in _infer_index_kind — str | int union"
```

- [ ] **Step 1: Annotate `interpreter/handlers/_common.py`**

Add `from __future__ import annotations` if missing, add `TYPE_CHECKING` block for `HandlerContext`, replace `ctx: Any`, add `# pyright: standard`.

```bash
poetry run pyright interpreter/handlers/_common.py
```
Expected: 0 errors.

- [ ] **Step 2: Annotate `interpreter/handlers/arithmetic.py`**

```bash
poetry run pyright interpreter/handlers/arithmetic.py
```

- [ ] **Step 3: Annotate `interpreter/handlers/control_flow.py`**

```bash
poetry run pyright interpreter/handlers/control_flow.py
```

- [ ] **Step 4: Annotate `interpreter/handlers/objects.py` and `interpreter/handlers/regions.py`**

```bash
poetry run pyright interpreter/handlers/objects.py interpreter/handlers/regions.py
```

- [ ] **Step 5: Annotate `interpreter/handlers/variables.py`**

```bash
poetry run pyright interpreter/handlers/variables.py
```

- [ ] **Step 6: Annotate `interpreter/handlers/memory.py`**

File pre_triage for `idx_val: Any`. Replace `ctx: Any` with `ctx: HandlerContext`.

```bash
poetry run pyright interpreter/handlers/memory.py
```

- [ ] **Step 7: Annotate `interpreter/handlers/calls.py`**

File pre_triage issues for `func_val: Any`, `dict[VarName, Any]`. Replace `ctx: Any` with `ctx: HandlerContext`.

```bash
poetry run pyright interpreter/handlers/calls.py
```

- [ ] **Step 8: Verify the full handlers module**

```bash
poetry run pyright interpreter/handlers/
```
Expected: 0 errors. This is where the 742 `reportArgumentType` errors should collapse.

- [ ] **Step 9: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/handlers/
git commit -m "types: annotate interpreter/handlers/ — ctx: Any → HandlerContext (33 occurrences)"
```

If this commit exposes a latent bug (pyright flags a real type mismatch): leave a `# type: ignore[rule]  # see <issue-id>`, file a separate Beads issue with full reproduction detail, fix in a follow-up commit under TDD.

---

## Task 9: `interpreter/vm/` annotation

**Files (one commit each for large files):**
- Modify: `interpreter/vm/vm_types.py`
- Modify: `interpreter/vm/field_fallback.py`
- Modify: `interpreter/vm/function_scoping.py`
- Modify: `interpreter/vm/unresolved_call.py`
- Modify: `interpreter/vm/vm.py`
- Modify: `interpreter/vm/builtins.py`
- Modify: `interpreter/vm/executor.py`

**Key pattern — `vm_types.py` has `Any` for Pydantic model fields:**

Check all `Any` fields in `vm_types.py`. Most should have concrete types. Any that are genuinely heterogeneous (e.g., heap object values) are pre_triage candidates.

- [ ] **Step 1: Annotate `interpreter/vm/vm_types.py`, `field_fallback.py`, `function_scoping.py`, `unresolved_call.py`**

These are smaller files. Group into one commit.

```bash
poetry run pyright interpreter/vm/vm_types.py interpreter/vm/field_fallback.py \
  interpreter/vm/function_scoping.py interpreter/vm/unresolved_call.py
```
Expected: 0 errors. Add `# pyright: standard` to each.

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/vm/vm_types.py interpreter/vm/field_fallback.py \
  interpreter/vm/function_scoping.py interpreter/vm/unresolved_call.py
git commit -m "types: annotate interpreter/vm/ support files — Any eliminated"
```

- [ ] **Step 2: Annotate `interpreter/vm/vm.py`**

`vm.py` defines `VMState`, `StateUpdate`, `HeapObject`, and many helpers. `HeapObject` fields are likely the primary source of `Any` in this file — they hold heterogeneous runtime values. File pre_triage for each.

```bash
poetry run pyright interpreter/vm/vm.py
```
Add `# pyright: standard`. Commit:

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/vm/vm.py
git commit -m "types: annotate interpreter/vm/vm.py — Any eliminated or filed"
```

- [ ] **Step 3: Annotate `interpreter/vm/builtins.py`**

```bash
poetry run pyright interpreter/vm/builtins.py
```
Add `# pyright: standard`. Commit:

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/vm/builtins.py
git commit -m "types: annotate interpreter/vm/builtins.py — Any eliminated or filed"
```

- [ ] **Step 4: Annotate `interpreter/vm/executor.py`**

`executor.py` is the largest VM file. Key `Any` uses:
- `instruction: Any` at line 250 — should be `InstructionBase`
- `instruction: Any` at line 224 — should be `InstructionBase`
- Any in `llm_client: Any = None` — pre_triage (Optional LLM client)

```bash
poetry run pyright interpreter/vm/executor.py
```
Add `# pyright: standard`. Commit:

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/vm/executor.py
git commit -m "types: annotate interpreter/vm/executor.py — Any eliminated or filed"
```

---

## Task 10: `interpreter/frontends/common/` and shared frontend files

**Files:**
- Modify: `interpreter/frontends/_base.py`
- Modify: `interpreter/frontends/base_node_types.py`
- Modify: `interpreter/frontends/context.py`
- Modify: `interpreter/frontends/operator_sets.py`
- Modify: `interpreter/frontends/symbol_table.py`
- Modify: `interpreter/frontends/type_extraction.py`
- Modify: `interpreter/frontends/typescript_node_types.py`
- Modify: `interpreter/frontends/common/assignments.py`
- Modify: `interpreter/frontends/common/control_flow.py`
- Modify: `interpreter/frontends/common/declarations.py`
- Modify: `interpreter/frontends/common/default_params.py`
- Modify: `interpreter/frontends/common/exceptions.py`
- Modify: `interpreter/frontends/common/expressions.py`
- Modify: `interpreter/frontends/common/match_expr.py`
- Modify: `interpreter/frontends/common/node_types.py`
- Modify: `interpreter/frontends/common/pattern_utils.py`
- Modify: `interpreter/frontends/common/patterns.py`
- Modify: `interpreter/frontends/common/property_accessors.py`

**Key pattern — `dict[str, Callable]` dispatch tables:**

The `stmt_dispatch` and `expr_dispatch` dicts in `context.py` and `_base.py` use bare `Callable` without type params. Determine the actual handler signature by reading `_base.py`'s dispatch usage. Likely `Callable[[object], list[str]]` or similar — inspect and type concretely. File pre_triage if the signature is genuinely variable.

**Key pattern — `params_lowerer: Callable` in `common/declarations.py`:**

```python
# Find the actual signature of lower_params and annotate:
params_lowerer: Callable = lower_params
# After (example — verify the real signature):
params_lowerer: Callable[[object, EmitContext], list[str]] = lower_params
```

- [ ] **Step 1: Determine the dispatch handler signature**

```bash
grep -n "def.*stmt_dispatch\|def.*expr_dispatch\|\._STMT_DISPATCH\[" interpreter/frontends/_base.py | head -20
```

Read enough of `_base.py` to understand the exact function signature stored in the dispatch dict. Type the dict accordingly.

- [ ] **Step 2: Annotate all files in this task, add `# pyright: standard` to each**

```bash
poetry run pyright interpreter/frontends/_base.py interpreter/frontends/context.py \
  interpreter/frontends/common/
```
Expected: 0 errors.

- [ ] **Step 3: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/frontends/_base.py interpreter/frontends/base_node_types.py \
  interpreter/frontends/context.py interpreter/frontends/operator_sets.py \
  interpreter/frontends/symbol_table.py interpreter/frontends/type_extraction.py \
  interpreter/frontends/typescript_node_types.py interpreter/frontends/common/
git commit -m "types: annotate interpreter/frontends/common/ and shared frontend files"
```

---

## Task 11: Language frontends (parallelizable)

**Files — 15 language frontend packages (one commit per language):**

```
interpreter/frontends/c/
interpreter/frontends/cpp/
interpreter/frontends/csharp/
interpreter/frontends/go/
interpreter/frontends/java/
interpreter/frontends/javascript/
interpreter/frontends/kotlin/
interpreter/frontends/lua/
interpreter/frontends/pascal/
interpreter/frontends/php/
interpreter/frontends/python/
interpreter/frontends/ruby/
interpreter/frontends/rust/
interpreter/frontends/scala/
interpreter/frontends/typescript.py
```

Each frontend follows the same pattern. Apply in parallel if using subagent-driven development.

**Per-language steps (repeat for each):**

- [ ] **Step 1: Annotate all files in `interpreter/frontends/<lang>/`**

For each frontend, the main `Any` sources are:
- Bare `Callable` in `_build_stmt_dispatch()` and `_build_expr_dispatch()` return types — type these using the signature determined in Task 10
- Any `Any` in individual lowering helpers

Add `# pyright: standard` to each file.

```bash
poetry run pyright interpreter/frontends/<lang>/
```
Expected: 0 errors.

- [ ] **Step 2: Run full verification gate and commit per language**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/frontends/<lang>/
git commit -m "types: annotate interpreter/frontends/<lang>/ frontend"
```

---

## Task 12: `interpreter/cobol/` annotation

**Files:** All 35 files in `interpreter/cobol/`

The COBOL module has 34 `Any` usages. Many come from the ANTLR parse tree — these are a legitimate third-party stub gap.

**Key pattern — ANTLR parse tree nodes:**

```python
# ANTLR tree nodes have no Python stubs. Use:
node: Any  # type: ignore[misc]  # ANTLR parse tree — no stubs available
```

For ANTLR boundary annotations:
```python
# Before
def lower_some_statement(self, ctx: Any, ...) -> list[str]:

# After (if ctx is an ANTLR parse tree node)
def lower_some_statement(self, ctx: Any, ...) -> list[str]:  # type: ignore[misc]  # ANTLR node — no stubs
```

**`DispatchFn` TypeAlias in `emit_context.py`:**
```python
# Already a TypeAlias — just needs the Any parameterised or documented
DispatchFn = Callable[["EmitContext", Any, DataLayout, str], None]
# The Any here is an ANTLR node — document and keep
DispatchFn = Callable[["EmitContext", Any, DataLayout, str], None]  # Any: ANTLR node, no stubs
```

- [ ] **Step 1: Identify all ANTLR boundary Any uses**

```bash
grep -n ": Any\|-> Any" interpreter/cobol/*.py | head -50
```

Classify each as: ANTLR boundary (keep with comment), concrete type not written (fix), or pre_triage.

- [ ] **Step 2: Annotate all files, add `# pyright: standard` to each**

For large files (`cobol_frontend.py`, `cobol_statements.py`): one commit each.
For small files: group into one commit.

```bash
poetry run pyright interpreter/cobol/
```
Expected: 0 errors (ANTLR boundary `# type: ignore` suppresses tree-sitter/ANTLR stub gaps).

- [ ] **Step 3: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/cobol/
git commit -m "types: annotate interpreter/cobol/ — ANTLR boundary documented, Any eliminated elsewhere"
```

---

## Task 13: `interpreter/llm/` annotation

**Files:**
- Modify: `interpreter/llm/backend.py`
- Modify: `interpreter/llm/chunked_llm_frontend.py`
- Modify: `interpreter/llm/llm_client.py`
- Modify: `interpreter/llm/llm_frontend.py`

**Key pattern — `completion_fn: Callable[..., Any]` in `llm_client.py`:**

This passes through the `litellm.completion()` signature for DI/testing. `litellm` has no complete stubs. Document as third-party boundary:

```python
completion_fn: Callable[..., Any] = _LAZY_IMPORT  # Any: litellm.completion() boundary — no stubs
```

**Key fix — `raise last_error  # type: ignore[misc]` in `llm_frontend.py:432`:**

This suppresses a pyright control-flow error where `last_error` might be unset. The fix is to eliminate the possibility at the type level:

```python
# Before (pyright can't prove last_error is set):
last_error = None
for attempt in range(n):
    try:
        return result
    except SomeError as e:
        last_error = e
raise last_error  # type: ignore[misc]

# After (initialise with a typed sentinel):
last_error: SomeError = SomeError("No attempts were made")
for attempt in range(n):
    try:
        return result
    except SomeError as e:
        last_error = e
raise last_error  # no type: ignore needed
```

Read `llm_frontend.py:420-440` to determine the actual exception type before fixing.

- [ ] **Step 1: Read `interpreter/llm/llm_frontend.py:420-440` to understand the loop**

```bash
sed -n '420,445p' interpreter/llm/llm_frontend.py
```

- [ ] **Step 2: Fix the `# type: ignore[misc]` at root cause**

Apply the sentinel initialisation pattern above with the correct exception type.

- [ ] **Step 3: Annotate all `llm/` files, add `# pyright: standard` to each**

```bash
poetry run pyright interpreter/llm/
```
Expected: 0 errors. No `# type: ignore` on internal code.

- [ ] **Step 4: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/llm/
git commit -m "types: annotate interpreter/llm/ — fix type: ignore[misc], litellm boundary documented"
```

---

## Task 14: `interpreter/project/` annotation

**Files:**
- Modify: `interpreter/project/compiler.py`
- Modify: `interpreter/project/entry_point.py`
- Modify: `interpreter/project/imports.py`
- Modify: `interpreter/project/linker.py`
- Modify: `interpreter/project/resolver.py`
- Modify: `interpreter/project/source_roots.py`
- Modify: `interpreter/project/types.py`

`entry_point.py` already uses `Callable[[FuncRef], bool]` correctly. `project/types.py` likely has the most type work. Add missing annotations, add `# pyright: standard`.

- [ ] **Step 1: Annotate all files, add `# pyright: standard`**

```bash
poetry run pyright interpreter/project/
```
Expected: 0 errors.

- [ ] **Step 2: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/project/
git commit -m "types: annotate interpreter/project/ — Any eliminated"
```

---

## Task 15: `interpreter/overload/`, `interpreter/interprocedural/`, `interpreter/ast_repair/`

**Files:**
- Modify: `interpreter/overload/ambiguity_handler.py`, `overload_resolver.py`, `resolution_strategy.py`
- Modify: `interpreter/interprocedural/analyze.py`, `call_graph.py`, `propagation.py`, `queries.py`, `summaries.py`, `types.py`
- Modify: `interpreter/ast_repair/error_span_extractor.py`, `error_span.py`, `repair_config.py`, `repair_prompter.py`, `repairing_frontend_decorator.py`, `source_patcher.py`

No `Any` uses in these modules. Work is adding missing arg/return type annotations and `# pyright: standard` to each file.

- [ ] **Step 1: Annotate all files, add `# pyright: standard`**

```bash
poetry run pyright interpreter/overload/ interpreter/interprocedural/ interpreter/ast_repair/
```
Expected: 0 errors.

- [ ] **Step 2: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/overload/ interpreter/interprocedural/ interpreter/ast_repair/
git commit -m "types: annotate overload/, interprocedural/, ast_repair/ — coverage complete"
```

---

## Task 16: Remaining root-level files and `interpreter/run.py`

**Files:**
- Modify: `interpreter/api.py`
- Modify: `interpreter/dataflow.py`
- Modify: `interpreter/frontend.py`
- Modify: `interpreter/parser.py`
- Modify: `interpreter/registry.py`
- Modify: `interpreter/run_types.py` (if not done in Task 7)
- Modify: `interpreter/run.py`

`run.py` is the largest root-level file. Key `Any` uses:
- `_format_val(v: Any) -> str` — genuine display boundary, document it
- `instruction: Any` at lines 224, 250 — should be `InstructionBase`
- `llm_client: Any = None` — pre_triage (Optional LLM client injection)

**Key pattern — `_format_val`:**

```python
def _format_val(v: Any) -> str:  # Any: display boundary — formats all runtime value types
```

- [ ] **Step 1: Annotate small root-level files (`api.py`, `dataflow.py`, `frontend.py`, `parser.py`, `registry.py`)**

Group into one commit:
```bash
poetry run pyright interpreter/api.py interpreter/dataflow.py interpreter/frontend.py \
  interpreter/parser.py interpreter/registry.py
```

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/api.py interpreter/dataflow.py interpreter/frontend.py \
  interpreter/parser.py interpreter/registry.py
git commit -m "types: annotate remaining root-level interpreter files"
```

- [ ] **Step 2: Annotate `interpreter/run.py`**

`run.py` is large — own commit.

```bash
poetry run pyright interpreter/run.py
```
Add `# pyright: standard`.

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/run.py
git commit -m "types: annotate interpreter/run.py — Any eliminated or documented"
```

---

## Task 17: `mcp_server/` annotation

**Files:**
- Modify: `mcp_server/__init__.py`
- Modify: `mcp_server/__main__.py`
- Modify: `mcp_server/formatting.py`
- Modify: `mcp_server/resources.py`
- Modify: `mcp_server/server.py`
- Modify: `mcp_server/session.py`
- Modify: `mcp_server/tools.py`

7 files, 1 `Any`. Add missing annotations throughout, add `# pyright: standard` to each.

- [ ] **Step 1: Annotate all files, add `# pyright: standard`**

```bash
poetry run pyright mcp_server/
```
Expected: 0 errors.

- [ ] **Step 2: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add mcp_server/
git commit -m "types: annotate mcp_server/ — Any eliminated"
```

---

## Task 18: Phase 3 — Gate upgrade

**Files:**
- Modify: `pyrightconfig.json`
- Modify: `.claude/core/workflow.md`

This task runs only after all files in `interpreter/` and `mcp_server/` carry `# pyright: standard`.

- [ ] **Step 1: Verify all files are promoted**

```bash
grep -rn "# pyright: standard" interpreter/ mcp_server/ | wc -l
```

Count should match total number of `.py` files (excluding `__init__.py` files if they have no annotations).

- [ ] **Step 2: Upgrade `pyrightconfig.json`**

```json
{
    "include": ["interpreter", "mcp_server"],
    "exclude": ["**/grammars/**", "**/__pycache__/**"],
    "typeCheckingMode": "standard",
    "pythonVersion": "3.13",
    "reportMissingImports": true,
    "reportMissingTypeStubs": false,
    "reportUnusedImport": false,
    "reportUnusedVariable": false
}
```

- [ ] **Step 3: Run pyright and fix any newly surfaced errors**

```bash
poetry run pyright interpreter/ mcp_server/
```

`standard` mode adds `reportMissingParameterType`, `reportUnknownVariableType`, `reportUnknownMemberType`. Fix any errors. If a fix requires logic changes: separate commit with test under TDD.

- [ ] **Step 4: Remove all `# pyright: standard` per-file comments (now redundant)**

```bash
grep -rln "# pyright: standard" interpreter/ mcp_server/ | xargs sed -i '' '/^# pyright: standard$/d'
```

Run pyright again to confirm still 0 errors.

- [ ] **Step 5: Update CLAUDE.md gate message**

In `.claude/core/workflow.md`, update the gate comment from `# type checking (basic mode initially)` to `# type checking (standard mode)`.

- [ ] **Step 6: Run full verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run pyright interpreter/ mcp_server/
poetry run python -m pytest tests/
bd backup
git add pyrightconfig.json .claude/core/workflow.md interpreter/ mcp_server/
git commit -m "chore: upgrade pyright gate to standard mode — all files annotated, Any eliminated"
```

---

## Testing Guidelines

Per the project TDD policy:

- **No new pytest tests are required for annotation-only changes.** The existing 13,235-test suite is the correctness safety net.
- **The pyright gate IS the test** for annotation work: `poetry run pyright interpreter/ mcp_server/` must pass on every commit.
- **If annotation exposes a latent bug** (a real type mismatch that was silently wrong at runtime):
  1. Do NOT fix it in the annotation commit
  2. Leave `# type: ignore[rule]  # see <issue-id>` as a temporary bridge
  3. File a Beads issue with: file path, line number, expected vs actual type, reproduction steps
  4. Fix in a follow-up commit: write failing test first, implement fix, verify test passes, commit
- **No `unittest.mock.patch`** — use dependency injection with mock objects for any test that needs fakes.
