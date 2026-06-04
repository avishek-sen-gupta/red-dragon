# COBOL CALL USING BY REFERENCE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `CALL 'prog' USING BY REFERENCE field` allocate a fresh params region, copy caller fields into it before the call, and copy modified bytes back to caller WS after the callee returns.

**Architecture:** All changes are in `interpreter/cobol/lower_call.py`. When `stmt.using` is non-empty, `lower_call` allocates a fresh byte region sized to the sum of USING field byte lengths, copies each field from WS into the region in order, emits `CallWithMemory` with that region as `params_reg`, then reads each BY REFERENCE field back out of the region into WS. The callee already reads `__params_region` at its own LINKAGE byte offsets — no callee-side change needed. `_handle_call_with_memory` already injects `params_reg` as `__params_region` — no handler change needed.

**Tech Stack:** Python, existing COBOL IR instructions (`AllocRegion`, `LoadRegion`, `WriteRegion`, `CallWithMemory`), `EmitContext`, `MaterialisedSectionedLayout`.

---

## File Map

- **Modify**: `interpreter/cobol/lower_call.py` — add params region allocation + copy-in + copy-back logic
- **Modify**: `tests/unit/test_lower_call_with_memory.py` — add 3 new unit tests, update 1 docstring
- **Modify**: `tests/integration/test_cobol_programs.py` — add `TestCallUsingByReference` class

---

### Task 1: Failing unit tests — params region allocation and copy-in

**Files:**
- Modify: `tests/unit/test_lower_call_with_memory.py`

- [ ] **Step 1: Add three failing tests to `tests/unit/test_lower_call_with_memory.py`**

Add these three tests after the existing `test_lower_call_giving_result_written_back`. Also update the docstring of `test_lower_call_by_reference_params_eq_results` (the assertion still holds but the region is now a fresh alloc, not WS):

```python
@covers(CobolFeature.CALL_USING)
def test_lower_call_using_emits_alloc_region_before_call():
    """CALL with USING params must emit ALLOC_REGION before CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        program="DOUBLIT",
        using=[CallUsingParam(name="WS-INPUT", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    call_idx = next(i for i, op in enumerate(opcodes) if op == Opcode.CALL_WITH_MEMORY)
    assert Opcode.ALLOC_REGION in opcodes[:call_idx], (
        "ALLOC_REGION must appear before CALL_WITH_MEMORY"
    )


@covers(CobolFeature.CALL_USING)
def test_lower_call_using_copy_in_before_call():
    """CALL with USING: LOAD_REGION+WRITE_REGION (copy-in) appear before CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        program="DOUBLIT",
        using=[CallUsingParam(name="WS-INPUT", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    call_idx = next(i for i, op in enumerate(opcodes) if op == Opcode.CALL_WITH_MEMORY)
    pre_call = opcodes[:call_idx]
    assert Opcode.LOAD_REGION in pre_call, "LOAD_REGION (copy-in) must precede CALL_WITH_MEMORY"
    assert Opcode.WRITE_REGION in pre_call, "WRITE_REGION (copy-in) must precede CALL_WITH_MEMORY"


@covers(CobolFeature.USING_BY_REFERENCE)
def test_lower_call_by_reference_copy_back_after_call():
    """BY REFERENCE: LOAD_REGION+WRITE_REGION copy-back appear after CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        program="DOUBLIT",
        using=[CallUsingParam(name="WS-INPUT", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    call_idx = next(i for i, op in enumerate(opcodes) if op == Opcode.CALL_WITH_MEMORY)
    post_call = opcodes[call_idx + 1:]
    assert Opcode.LOAD_REGION in post_call, (
        "LOAD_REGION (copy-back) must follow CALL_WITH_MEMORY for BY REFERENCE"
    )
    assert Opcode.WRITE_REGION in post_call, (
        "WRITE_REGION (copy-back) must follow CALL_WITH_MEMORY for BY REFERENCE"
    )
```

Also add these imports at the top of the file (they may already be present — skip if so):

```python
from interpreter.cobol.features import CobolFeature
```

And update the docstring of `test_lower_call_by_reference_params_eq_results`:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_by_reference_params_eq_results():
    """params_reg == results_reg for CALL USING (fresh params region, not WS)."""
```

- [ ] **Step 2: Run the three new tests to confirm they fail**

```bash
poetry run python -m pytest tests/unit/test_lower_call_with_memory.py::test_lower_call_using_emits_alloc_region_before_call tests/unit/test_lower_call_with_memory.py::test_lower_call_using_copy_in_before_call tests/unit/test_lower_call_with_memory.py::test_lower_call_by_reference_copy_back_after_call -v
```

Expected: 3 FAILED (no ALLOC_REGION/LOAD_REGION/WRITE_REGION in current impl).

- [ ] **Step 3: Run the existing tests to confirm they still pass**

```bash
poetry run python -m pytest tests/unit/test_lower_call_with_memory.py -v
```

Expected: 3 PASS (existing), 3 FAIL (new).

---

### Task 2: Implement params region construction and BY REFERENCE copy-back

**Files:**
- Modify: `interpreter/cobol/lower_call.py`

- [ ] **Step 1: Replace the body of `lower_call` with the new implementation**

Full replacement of `interpreter/cobol/lower_call.py`:

```python
"""CALL, ALTER, ENTRY, CANCEL statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import (
    AlterStatement,
    CallStatement,
    CancelStatement,
    EntryStatement,
)
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    AllocRegion,
    CallWithMemory,
    Label_,
    LoadRegion,
    StoreVar,
    WriteRegion,
)
from interpreter.ir import CodeLabel

logger = logging.getLogger(__name__)


def lower_call(
    ctx: EmitContext,
    stmt: CallStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CALL 'program' USING params — region-passing subprogram invocation via CallWithMemory.

    When stmt.using is non-empty:
      1. Allocate a fresh params region (sum of USING field byte lengths).
      2. Copy each USING field from WS into the params region at cumulative byte offsets.
      3. Emit CallWithMemory with params_reg pointing at the fresh region.
      4. For BY REFERENCE params, copy bytes back from the params region into WS.

    When stmt.using is empty, the caller's WS region is passed as params_reg (legacy behaviour).
    """
    ws_layout, ws_reg = materialised.working_storage

    if stmt.using:
        # Resolve field layouts for all USING params (all are in WS).
        param_fls = []
        for param in stmt.using:
            fl, _ = materialised.resolve(param.name)
            param_fls.append((param, fl))

        # Allocate fresh params region sized to total USING bytes.
        total_bytes = sum(fl.byte_length for _, fl in param_fls)
        size_reg = ctx.const_to_reg(total_bytes)
        params_reg = ctx.fresh_reg()
        ctx.emit_inst(AllocRegion(result_reg=params_reg, size_reg=size_reg))

        # Copy-in: write each USING field from WS into the params region.
        cumulative = 0
        for _, fl in param_fls:
            src_off = ctx.const_to_reg(fl.offset)
            tmp = ctx.fresh_reg()
            ctx.emit_inst(
                LoadRegion(
                    result_reg=tmp,
                    region_reg=ws_reg,
                    offset_reg=src_off,
                    length=fl.byte_length,
                )
            )
            dst_off = ctx.const_to_reg(cumulative)
            ctx.emit_inst(
                WriteRegion(
                    region_reg=params_reg,
                    offset_reg=dst_off,
                    length=fl.byte_length,
                    value_reg=tmp,
                )
            )
            cumulative += fl.byte_length
    else:
        params_reg = ws_reg

    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallWithMemory(
            result_reg=result_reg,
            func_name=FuncName(stmt.program),
            params_reg=params_reg,
            results_reg=params_reg,
        )
    )

    # Copy-back: for BY REFERENCE params, write updated bytes from params region back to WS.
    if stmt.using:
        cumulative = 0
        for param, fl in param_fls:
            if param.param_type == "REFERENCE":
                src_off = ctx.const_to_reg(cumulative)
                tmp = ctx.fresh_reg()
                ctx.emit_inst(
                    LoadRegion(
                        result_reg=tmp,
                        region_reg=params_reg,
                        offset_reg=src_off,
                        length=fl.byte_length,
                    )
                )
                dst_off = ctx.const_to_reg(fl.offset)
                ctx.emit_inst(
                    WriteRegion(
                        region_reg=ws_reg,
                        offset_reg=dst_off,
                        length=fl.byte_length,
                        value_reg=tmp,
                    )
                )
            cumulative += fl.byte_length

    if stmt.giving and ctx.has_field(stmt.giving, materialised):
        giving_ref, giving_rr = ctx.resolve_field_ref(stmt.giving, materialised)
        str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            giving_rr, giving_ref.fl, str_reg, giving_ref.offset_reg
        )

    logger.info(
        "CALL %s with %d params (CallWithMemory)", stmt.program, len(stmt.using)
    )


def lower_alter(
    ctx: EmitContext,
    stmt: AlterStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ALTER para-1 TO PROCEED TO para-2."""
    for pt in stmt.proceed_tos:
        target_reg = ctx.const_to_reg(f"para_{pt.target}")
        ctx.emit_inst(
            StoreVar(
                name=VarName(f"__alter_{pt.source}"),
                value_reg=target_reg,
            )
        )
        logger.info("ALTER %s TO PROCEED TO %s", pt.source, pt.target)


def lower_entry(
    ctx: EmitContext,
    stmt: EntryStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ENTRY 'name' — alternate entry point for a subprogram."""
    if stmt.entry_name:
        ctx.emit_inst(Label_(label=CodeLabel(f"entry_{stmt.entry_name}")))
        logger.info("ENTRY %s", stmt.entry_name)


def lower_cancel(
    ctx: EmitContext,
    stmt: CancelStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CANCEL program — no-op for static analysis."""
    for prog in stmt.programs:
        logger.info("CANCEL %s (no-op for static analysis)", prog)
```

- [ ] **Step 2: Run all unit tests for lower_call**

```bash
poetry run python -m pytest tests/unit/test_lower_call_with_memory.py -v
```

Expected: all 6 PASS.

- [ ] **Step 3: Run full unit test suite to catch regressions**

```bash
poetry run python -m pytest tests/unit/ -x -q
```

Expected: all pass.

- [ ] **Step 4: Format**

```bash
poetry run python -m black interpreter/cobol/lower_call.py tests/unit/test_lower_call_with_memory.py
```

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/lower_call.py tests/unit/test_lower_call_with_memory.py
git commit -m "feat(cobol): CALL USING BY REFERENCE params region copy-in and copy-back"
```

---

### Task 3: Integration test — CALL USING BY REFERENCE end-to-end

**Files:**
- Modify: `tests/integration/test_cobol_programs.py`

This test runs two COBOL modules through the full pipeline. MAIN-PROG calls DOUBLIT passing WS-VALUE BY REFERENCE. DOUBLIT moves 42 into its LINKAGE field. After return, MAIN-PROG's WS-VALUE should be 42.

- [ ] **Step 1: Add `TestCallUsingByReference` to `tests/integration/test_cobol_programs.py`**

Add this class at the end of the file (before the final blank line):

```python
class TestCallUsingByReference:
    """CALL USING BY REFERENCE: callee modifies LINKAGE field; caller sees updated WS value."""

    @covers(CobolFeature.SECTION_LINKAGE)
    def test_callee_linkage_write_propagates_to_caller_ws(self, tmp_path):
        """BY REFERENCE: DOUBLIT moves 42 into LS-VALUE; MAIN-PROG sees WS-VALUE == 42."""
        (tmp_path / "main.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-VALUE PIC 9(4) VALUE 5.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'DOUBLIT' USING BY REFERENCE WS-VALUE.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "doublit.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. DOUBLIT.",
                    "DATA DIVISION.",
                    "LINKAGE SECTION.",
                    "01 LS-VALUE PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE 42 TO LS-VALUE.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        # Read WS-VALUE from MAINPROG's singleton.
        singleton_key = VarName("__prog_MAINPROG")
        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if singleton_key in frame.local_vars:
                singleton_ptr = frame.local_vars[singleton_key].value
                break
        assert singleton_ptr is not None, "__prog_MAINPROG singleton not found"
        assert isinstance(singleton_ptr, Pointer), (
            f"Expected Pointer, got {type(singleton_ptr)}"
        )
        singleton = vm.heap_get(singleton_ptr.base)
        ws_handle_tv = singleton.fields[FieldName("ws_handle")]
        ws_addr = Address(ws_handle_tv.value)
        region = vm.region_get(ws_addr)
        assert region is not None, f"WS region not found at {ws_addr}"

        ws_value = _decode_zoned_unsigned(region, offset=0, length=4)
        assert ws_value == 42, (
            f"Expected WS-VALUE=42 after BY REFERENCE call, got {ws_value}"
        )
```

- [ ] **Step 2: Run the new integration test to confirm it fails (or passes — either is fine as a baseline)**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestCallUsingByReference -v
```

Note: this test requires the ProLeap bridge JAR. If the JAR is absent the test is automatically skipped. If it runs and fails, investigate before proceeding.

- [ ] **Step 3: Run the full integration test suite to verify no regressions**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py -x -q
```

Expected: all pass (including new test).

- [ ] **Step 4: Format**

```bash
poetry run python -m black tests/integration/test_cobol_programs.py
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_cobol_programs.py
git commit -m "test(cobol): integration test for CALL USING BY REFERENCE end-to-end"
```

---

## Self-Review

**Spec coverage:**
- ✅ AllocRegion emitted for USING params → Task 1 test + Task 2 impl
- ✅ Copy-in (LoadRegion/WriteRegion before call) → Task 1 test + Task 2 impl
- ✅ CallWithMemory with fresh params_reg → Task 2 impl
- ✅ Copy-back for BY REFERENCE → Task 1 test + Task 2 impl
- ✅ `@covers(CobolFeature.CALL_USING)` and `@covers(CobolFeature.USING_BY_REFERENCE)` → Task 1
- ✅ `@covers(CobolFeature.SECTION_LINKAGE)` → Task 3
- ✅ Integration test with two-module COBOL program → Task 3

**Placeholder scan:** None found.

**Type consistency:**
- `param_fls: list[tuple[CallUsingParam, FieldLayout]]` — used consistently across copy-in and copy-back loops.
- `AllocRegion(result_reg, size_reg)`, `LoadRegion(result_reg, region_reg, offset_reg, length)`, `WriteRegion(region_reg, offset_reg, length, value_reg)` — field order matches `interpreter/instructions.py:876-945`.
- `ctx.const_to_reg(int)` used for all integer constants — consistent with existing `lower_data_division.py` usage.
