# COBOL Register Naming Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the COBOL frontend emit registers named `%0, %1, …` (matching every tree-sitter frontend) instead of `%r0, %r1, …`, eliminating the naming divergence that caused red-dragon-irl8 (cross-module register collision in the linker).

**Architecture:** The change is a single line in `EmitContext.fresh_reg` (drop the `r`). The `%r` prefix is purely cosmetic and not load-bearing: `EmitContext.inline_ir` remaps **every** register of the spliced encode/decode IR (named params `%p_*` and internal temporaries `%<prefix>_r<n>`) to fresh registers from the same counter, so the final COBOL IR contains only `fresh_reg()` outputs. The generated IR has **no bare numbered registers**, so unifying to `%N` introduces no collisions. No production code branches on the `%r` prefix (all register-pattern code uses convention-agnostic `startswith("%")` except the linker — already robust to both — and `chunked_llm_frontend`, which is `%N`-only and never processes COBOL, and becomes universally correct after this change). The only fallout is test code that asserts on literal COBOL-emitted register names.

**Tech Stack:** Python 3.13 (poetry, pytest, pytest-xdist), the ProLeap COBOL bridge (`PROLEAP_BRIDGE_JAR`). Many COBOL integration tests skip without the JAR; this plan assumes the JAR is available so the full COBOL suite actually runs.

**Context for the implementer:**
- COBOL register source: `interpreter/cobol/emit_context.py` — `_reg_counter` starts at 0 (line 82); `fresh_reg` (lines 102–105) returns `Register(f"%r{self._reg_counter}")`.
- Tree-sitter equivalent (the target convention): `interpreter/frontends/context.py:197-200` returns `Register(f"%{self.reg_counter}")`.
- Do **not** revert the linker regex (`interpreter/project/linker.py:55`, `^%([A-Za-z]*)(\d+)$`) — keep it robust to both forms (defensive; harmless with `%N`).
- Do **not** change `chunked_llm_frontend.py` — its `^%(\d+)$` becomes universally correct once COBOL emits `%N`.
- Conventions: use `poetry run python -m pytest` (NOT `poetry run pytest`); format with `poetry run python -m black`; tests run in parallel via pytest-xdist.

---

## File Structure

- **`interpreter/cobol/emit_context.py`** (modify) — `fresh_reg` emits `%N` instead of `%rN`. The single source change.
- **`tests/unit/test_cobol_emit_context_registers.py`** (create) — a regression test locking the `%N` convention for the COBOL frontend.
- **Various COBOL test files** (modify, fallout-driven) — update any assertion that hard-codes a COBOL-emitted `%rN` register name to `%N`. Identified by running the suite; the set is not fully known up front (most COBOL IR-shape tests assert on opcodes, not register names).

---

## Task 1: Lock the `%N` convention and flip `fresh_reg`

**Files:**
- Create: `tests/unit/test_cobol_emit_context_registers.py`
- Modify: `interpreter/cobol/emit_context.py:102-105`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cobol_emit_context_registers.py`:

```python
"""The COBOL frontend must emit registers named %0, %1, ... (matching the
tree-sitter frontends), not %r0, %r1, .... Divergent naming caused a
cross-module register-collision bug (red-dragon-irl8)."""

from __future__ import annotations

from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.statement_dispatch import dispatch_statement
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fresh_reg_uses_plain_numeric_naming():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    r0 = ctx.fresh_reg()
    r1 = ctx.fresh_reg()
    assert str(r0) == "%0"
    assert str(r1) == "%1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_cobol_emit_context_registers.py -x -q`
Expected: FAIL — `assert '%r0' == '%0'` (current naming is `%r0`).

- [ ] **Step 3: Flip `fresh_reg`**

In `interpreter/cobol/emit_context.py`, change `fresh_reg` (lines 102–105) from:

```python
    def fresh_reg(self) -> Register:
        name = Register(f"%r{self._reg_counter}")
        self._reg_counter += 1
        return name
```

to:

```python
    def fresh_reg(self) -> Register:
        name = Register(f"%{self._reg_counter}")
        self._reg_counter += 1
        return name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_cobol_emit_context_registers.py -x -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/emit_context.py tests/unit/test_cobol_emit_context_registers.py
git commit -m "refactor(cobol): emit %N registers to match other frontends (red-dragon-irl8 follow-up)"
```

---

## Task 2: Fix register-literal test fallout in COBOL unit tests

The naming change breaks any test that asserts on a literal COBOL-emitted `%rN` register name. Most COBOL lowering tests assert on opcodes (via `_find_opcodes`) and are unaffected; this task finds and fixes the ones that aren't.

**Files:**
- Modify (fallout-driven): COBOL unit test files under `tests/unit/` that fail with a register-name mismatch.

- [ ] **Step 1: Run the COBOL unit suite and capture failures**

Run: `poetry run python -m pytest tests/unit/ -q -k "cobol or lower_call or call_with_memory or sectioned or region" 2>&1 | tail -40`
Expected: PASS, OR failures whose assertion diffs show a register-name mismatch (an expected `"%rN"` vs an actual `"%N"`, or vice-versa).

- [ ] **Step 2: For each failing test, confirm it is register-naming churn (not a real regression)**

For a failing test, read the assertion. It is churn **only if** the sole difference is `%rN` → `%N` on a value produced by the COBOL frontend / `EmitContext`. Example shape:

```python
# before (now fails):
assert str(inst.result_reg) == "%r5"
# after:
assert str(inst.result_reg) == "%5"
```

If a failure is **not** a simple `%rN`→`%N` rename (e.g. a wrong opcode, a missing instruction, a value mismatch), STOP — that indicates a real regression from the change, not churn. Re-investigate before editing (the change should be behavior-preserving; a non-rename failure means an unexamined dependency on the `%r` prefix). Report it.

- [ ] **Step 3: Update each churned assertion**

Replace the hard-coded `%rN` literal(s) with the corresponding `%N` in the failing assertions only. Do not touch tests that construct `%rN` as arbitrary hand-built VM inputs and still pass (those are independent of the frontend and the VM does not care about the prefix — leave them as-is to keep the diff minimal).

- [ ] **Step 4: Re-run the COBOL unit suite**

Run: `poetry run python -m pytest tests/unit/ -q -k "cobol or lower_call or call_with_memory or sectioned or region" 2>&1 | tail -10`
Expected: PASS (all green).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(cobol): update register-literal assertions for %N naming"
```

---

## Task 3: Full-suite verification (integration, dataflow, viz, multi-module)

The change affects every COBOL program's emitted IR, so anything that consumes COBOL IR — integration execution, dataflow analysis, multi-module linking, and viz/trace snapshots — must be re-verified.

**Files:**
- Modify (fallout-driven, if any): integration/dataflow/viz test files that assert on literal COBOL `%rN` register names.

- [ ] **Step 1: Run the full suite**

Run: `poetry run python -m pytest tests/ -q 2>&1 | tail -6`
Expected: all pass (baseline before this work was `13813 passed, 66 skipped, 17 xfailed`). The pass count may differ by 1 (the new Task-1 test); skipped/xfailed unchanged.

- [ ] **Step 2: Triage any failures**

Any remaining failure should be register-naming churn in integration/dataflow/viz tests (same `%rN`→`%N` rename as Task 2 Step 2-3). Apply the same rename. If a failure is NOT a register rename, STOP and re-investigate — it means a real behavioral dependency on the prefix that the architecture analysis missed.

- [ ] **Step 3: Verify feature coverage is unaffected (sanity)**

Run: `poetry run python scripts/feature_coverage_audit.py 2>&1 | tail -5`
Expected: 0 uncovered for all 15 languages (register naming has no effect on `@covers` coverage; this is a sanity check that nothing import-broke).

- [ ] **Step 4: Re-run the LINKAGE-only regression and the original irl8 repro to confirm the unification keeps it fixed**

Run: `poetry run python -m pytest "tests/integration/test_cobol_programs.py::TestCallUsingByReference::test_linkage_only_subprogram_reads_parameter" "tests/integration/test_cobol_copybook_inlining.py::test_copy_shared_record_across_call" -q 2>&1 | tail -4`
Expected: PASS (2 passed) — the unified `%N` naming is rebased correctly by the linker, so the LINKAGE-only subprogram still reads its parameter (7 + 10 → 17).

- [ ] **Step 5: Format and commit any remaining edits**

```bash
poetry run python -m black .
git add -A
git commit -m "test(cobol): update integration/dataflow/viz register-literals for %N naming" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- "COBOL emits `%N`" → Task 1 (the one-line `fresh_reg` change + locking test). ✓
- "No collision with inlined IR" → verified pre-plan (generated IR has only alpha-named registers, all remapped by `inline_ir`); no task needed, documented in Architecture. ✓
- "Linker still works / robust to both" → kept as-is (Architecture note); re-verified by Task 3 Step 4. ✓
- "Don't break other frontends / chunked_llm" → no change needed (Architecture note); guarded by Task 3 Step 1 full suite. ✓
- "Test fallout fixed" → Tasks 2 (unit) and 3 (integration/dataflow/viz). ✓

**Placeholder scan:** Task 2 and Task 3's edits are fallout-driven and cannot enumerate exact lines in advance (the churn set depends on running the suite), but each gives the concrete identification method, the exact edit shape (`%rN`→`%N`), and an explicit STOP condition distinguishing churn from a real regression. No "TBD"/"handle edge cases" hand-waving.

**Type consistency:** The only signature touched is `fresh_reg` (return type `Register`, unchanged). The locking test uses `EmitContext(dispatch_fn=dispatch_statement)` — the same construction pattern used in `tests/unit/test_lower_call_with_memory.py`.

**Risk note:** If Task 2 or Task 3 surfaces a failure that is *not* a `%rN`→`%N` rename, that is the signal that some consumer depended on the `%r` prefix after all — stop and reassess rather than forcing the rename.
