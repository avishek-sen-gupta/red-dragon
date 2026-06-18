# PERFORM VARYING AFTER Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add support for COBOL PERFORM VARYING … AFTER … nested multi-index loops, both TEST BEFORE and TEST AFTER, across all three layers: Python dataclass, IR lowering, and the ProLeap bridge serializer.

**Architecture:** The existing `PerformVaryingSpec` gains an immutable `after_specs: tuple[PerformVaryingSpec, ...]` field (empty = existing single-variable behaviour, unchanged). The lowering dispatches to two new pure functions: a recursive helper for TEST BEFORE and an iterative cascade emitter for TEST AFTER. The bridge serializer serializes `VaryingClause.getAfters()` into a JSON `after_specs` array consumed by the Python parser.

**Tech Stack:** Python 3.13 (dataclasses, typing), Java 17 (Gson, ProLeap ASG), pytest, `poetry run python -m pytest`, `cd proleap-bridge && ./build.sh` to rebuild the bridge JAR.

**Constraints:** No mutation — `after_specs` is a `tuple`, lowering helpers are pure emitters. TDD — every step writes a failing test before implementation. FP principles — no shared mutable state, helpers take all inputs as parameters.

---

## File Map

| File | Change |
|---|---|
| `interpreter/cobol/features.py` | Add `PERFORM_VARYING_AFTER` enum member |
| `interpreter/cobol/cobol_statements.py` | Add `after_specs` field to `PerformVaryingSpec`; update `_parse_perform_spec` and `_spec_to_dict` |
| `interpreter/cobol/lower_perform.py` | Extract `_init_varying_var`; add `_emit_test_before_level`, `_emit_test_after_varying`; update `lower_perform_varying` dispatch |
| `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` | Serialize `vc.getAfters()` into `"after_specs"` JSON array |
| `tests/unit/test_cobol_statements.py` | New tests: after_specs parse and round-trip |
| `tests/unit/test_cobol_frontend.py` | New tests: IR structure for TEST BEFORE and TEST AFTER multi-variable |
| `tests/integration/test_cobol_programs.py` | New class `TestPerformVaryingAfter` with 2×3 and 2×2×2 integration tests |

---

## Task 1 — Feature Enum

**Files:**
- Modify: `interpreter/cobol/features.py`

- [ ] **Step 1: Add enum member**

Open `interpreter/cobol/features.py`. After the `PERFORM_VARYING` entry (line ~34), add:

```python
PERFORM_VARYING_AFTER = "PERFORM VARYING x ... AFTER y ... nested multi-index loop"
```

- [ ] **Step 2: Verify coverage tool still runs**

```bash
poetry run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -5
```

Expected: same pass count as before (no new failures).

- [ ] **Step 3: Commit**

```bash
git add interpreter/cobol/features.py
git commit -m "feat(cobol): add PERFORM_VARYING_AFTER feature enum member"
```

---

## Task 2 — Python Dataclass: `after_specs` field + parse + serialize

**Files:**
- Modify: `interpreter/cobol/cobol_statements.py`
- Test: `tests/unit/test_cobol_statements.py`

### 2a — Parse

- [ ] **Step 1: Write failing test for parse with after_specs**

In `tests/unit/test_cobol_statements.py`, inside `class TestPerformSpecs`, add:

```python
@covers(CobolFeature.PERFORM_VARYING_AFTER)
def test_varying_spec_with_after_specs(self):
    """PERFORM VARYING with one AFTER clause deserializes both loop variables."""
    stmt = parse_statement(
        {
            "type": "PERFORM",
            "perform_type": "VARYING",
            "varying_var": "WS-I",
            "varying_from": "1",
            "varying_by": "1",
            "until": {
                "not": False,
                "relation": {
                    "left": {"kind": "ref", "name": "WS-I"},
                    "op": ">",
                    "right": {"kind": "lit", "value": "3"},
                },
            },
            "test_before": True,
            "after_specs": [
                {
                    "varying_var": "WS-J",
                    "varying_from": "1",
                    "varying_by": "1",
                    "until": {
                        "not": False,
                        "relation": {
                            "left": {"kind": "ref", "name": "WS-J"},
                            "op": ">",
                            "right": {"kind": "lit", "value": "3"},
                        },
                    },
                }
            ],
        }
    )
    assert isinstance(stmt.spec, PerformVaryingSpec)
    assert len(stmt.spec.after_specs) == 1
    inner = stmt.spec.after_specs[0]
    assert inner.varying_var == "WS-J"
    assert inner.varying_from == "1"
    assert inner.varying_by == "1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run python -m pytest tests/unit/test_cobol_statements.py::TestPerformSpecs::test_varying_spec_with_after_specs -v
```

Expected: FAIL — `TypeError` because `PerformVaryingSpec` does not accept `after_specs`.

- [ ] **Step 3: Add `after_specs` field to `PerformVaryingSpec`**

In `interpreter/cobol/cobol_statements.py`, locate `PerformVaryingSpec` (~line 42). Replace with:

```python
@dataclass(frozen=True)
class PerformVaryingSpec:
    """PERFORM ... VARYING loop specification."""

    varying_var: str  # loop variable name
    varying_from: "str | dict"  # FROM value (structured expr dict, or legacy text)
    varying_by: str  # BY step value
    condition: dict
    test_before: bool = True
    after_specs: "tuple[PerformVaryingSpec, ...]" = field(default_factory=tuple)
```

Add `field` to the existing `dataclasses` import at the top of the file if not already imported:

```python
from dataclasses import dataclass, field
```

- [ ] **Step 4: Update `_parse_perform_spec` to read `after_specs`**

Locate `_parse_perform_spec` (~line 1045). Replace the `VARYING` branch:

```python
if perform_type == "VARYING":
    raw_afters = data.get("after_specs", [])
    after_specs: tuple[PerformVaryingSpec, ...] = tuple(
        PerformVaryingSpec(
            varying_var=a.get("varying_var", ""),
            varying_from=a.get("varying_from", ""),
            varying_by=a.get("varying_by", ""),
            condition=a.get("until", {}),
        )
        for a in raw_afters
    )
    return PerformVaryingSpec(
        varying_var=data.get("varying_var", ""),
        varying_from=data.get("varying_from", ""),
        varying_by=data.get("varying_by", ""),
        condition=data.get("until", {}),
        test_before=data.get("test_before", True),
        after_specs=after_specs,
    )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
poetry run python -m pytest tests/unit/test_cobol_statements.py::TestPerformSpecs::test_varying_spec_with_after_specs -v
```

Expected: PASS.

### 2b — Serialize (round-trip)

- [ ] **Step 6: Write failing round-trip test**

In `tests/unit/test_cobol_statements.py`, inside `class TestRoundTrip`, add:

```python
@covers(CobolFeature.PERFORM_VARYING_AFTER)
def test_perform_varying_after_round_trip(self):
    """PerformVaryingSpec with after_specs survives dict → spec → dict."""
    data = {
        "type": "PERFORM",
        "perform_type": "VARYING",
        "varying_var": "WS-I",
        "varying_from": "1",
        "varying_by": "1",
        "until": {
            "not": False,
            "relation": {
                "left": {"kind": "ref", "name": "WS-I"},
                "op": ">",
                "right": {"kind": "lit", "value": "3"},
            },
        },
        "test_before": True,
        "after_specs": [
            {
                "varying_var": "WS-J",
                "varying_from": "1",
                "varying_by": "1",
                "until": {
                    "not": False,
                    "relation": {
                        "left": {"kind": "ref", "name": "WS-J"},
                        "op": ">",
                        "right": {"kind": "lit", "value": "3"},
                    },
                },
            }
        ],
    }
    stmt = parse_statement(data)
    assert isinstance(stmt, PerformStatement)
    from interpreter.cobol.cobol_statements import _spec_to_dict
    result = _spec_to_dict(stmt.spec)
    assert result["after_specs"][0]["varying_var"] == "WS-J"
    assert result["after_specs"][0]["varying_by"] == "1"
```

- [ ] **Step 7: Run test to verify it fails**

```bash
poetry run python -m pytest tests/unit/test_cobol_statements.py::TestRoundTrip::test_perform_varying_after_round_trip -v
```

Expected: FAIL — `KeyError: 'after_specs'` because `_spec_to_dict` does not emit the field.

- [ ] **Step 8: Update `_spec_to_dict` to serialize `after_specs`**

Locate `_spec_to_dict` (~line 1068). Replace the `PerformVaryingSpec` branch:

```python
if isinstance(spec, PerformVaryingSpec):
    d: dict = {
        "perform_type": "VARYING",
        "varying_var": spec.varying_var,
        "varying_from": spec.varying_from,
        "varying_by": spec.varying_by,
        "until": spec.condition,
        "test_before": spec.test_before,
    }
    if spec.after_specs:
        d["after_specs"] = [
            {
                "varying_var": a.varying_var,
                "varying_from": a.varying_from,
                "varying_by": a.varying_by,
                "until": a.condition,
            }
            for a in spec.after_specs
        ]
    return d
```

- [ ] **Step 9: Run both new statement tests**

```bash
poetry run python -m pytest tests/unit/test_cobol_statements.py -k "after" -v
```

Expected: 2 PASS.

- [ ] **Step 10: Run full unit suite to confirm no regressions**

```bash
poetry run python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5
```

Expected: same pass count as before.

- [ ] **Step 11: Commit**

```bash
git add interpreter/cobol/cobol_statements.py tests/unit/test_cobol_statements.py
git commit -m "feat(cobol): add after_specs field to PerformVaryingSpec — parse and serialize"
```

---

## Task 3 — Lowering: Extract `_init_varying_var`

**Files:**
- Modify: `interpreter/cobol/lower_perform.py`

This is a pure refactor — existing tests must stay green throughout.

- [ ] **Step 1: Extract `_init_varying_var` helper**

In `interpreter/cobol/lower_perform.py`, add this function immediately before `lower_perform_varying` (~line 215):

```python
def _init_varying_var(
    ctx: EmitContext,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Write spec.varying_from into spec.varying_var in the heap."""
    if not ctx.has_field(spec.varying_var, materialised):
        return
    varying_ref, varying_rr = ctx.resolve_field_ref(spec.varying_var, materialised)
    from_val_reg = _eval_varying_from(ctx, spec.varying_from, materialised)
    from_str_reg = ctx.emit_to_string(from_val_reg)
    ctx.emit_encode_and_write(
        varying_rr, varying_ref.fl, from_str_reg, varying_ref.offset_reg
    )
```

- [ ] **Step 2: Replace inline init in `lower_perform_varying`**

In `lower_perform_varying` (~line 228), replace the existing init block:

```python
    # Before (remove these lines):
    if ctx.has_field(spec.varying_var, materialised):
        varying_ref, varying_rr = ctx.resolve_field_ref(spec.varying_var, materialised)
        from_val_reg = _eval_varying_from(ctx, spec.varying_from, materialised)
        from_str_reg = ctx.emit_to_string(from_val_reg)
        ctx.emit_encode_and_write(
            varying_rr, varying_ref.fl, from_str_reg, varying_ref.offset_reg
        )

    # After (replace with):
    _init_varying_var(ctx, spec, materialised)
```

- [ ] **Step 3: Verify existing tests unchanged**

```bash
poetry run python -m pytest tests/unit/test_cobol_frontend.py -k "varying" -v
```

Expected: all existing VARYING tests PASS.

- [ ] **Step 4: Commit**

```bash
git add interpreter/cobol/lower_perform.py
git commit -m "refactor(cobol): extract _init_varying_var helper in lower_perform"
```

---

## Task 4 — Lowering: TEST BEFORE multi-variable

**Files:**
- Modify: `interpreter/cobol/lower_perform.py`
- Test: `tests/unit/test_cobol_frontend.py`

- [ ] **Step 1: Write failing unit test**

In `tests/unit/test_cobol_frontend.py`, inside `class TestPerformLoopLowering`, add:

```python
@covers(CobolFeature.PERFORM_VARYING_AFTER)
def test_perform_varying_after_test_before_emits_nested_loops(self):
    """PERFORM VARYING I AFTER J (TEST BEFORE) emits two BRANCH_IF with nested structure.

    The outer BranchIf's true-target must be the overall exit label.
    The inner BranchIf's true-target must be the outer increment label (not exit).
    Both WRITE_REGIONs for FROM init appear before their respective loop tops.
    """
    fields = [
        CobolField(name="WS-I", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="0"),
        CobolField(name="WS-J", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="0"),
    ]
    until_i = {
        "not": False,
        "relation": {
            "left": {"kind": "ref", "name": "WS-I"},
            "op": ">",
            "right": {"kind": "lit", "value": "2"},
        },
    }
    until_j = {
        "not": False,
        "relation": {
            "left": {"kind": "ref", "name": "WS-J"},
            "op": ">",
            "right": {"kind": "lit", "value": "3"},
        },
    }
    stmts = [
        PerformStatement(
            children=[DisplayStatement(operand=RefModOperand(name="BODY"))],
            spec=PerformVaryingSpec(
                varying_var="WS-I",
                varying_from="1",
                varying_by="1",
                condition=until_i,
                test_before=True,
                after_specs=(
                    PerformVaryingSpec(
                        varying_var="WS-J",
                        varying_from="1",
                        varying_by="1",
                        condition=until_j,
                    ),
                ),
            ),
        )
    ]
    instructions = self._lower_with_field_and_stmts(fields, stmts)

    branch_ifs = _find_opcodes(instructions, Opcode.BRANCH_IF)
    # Two BRANCH_IF instructions: outer (I) and inner (J)
    assert len(branch_ifs) == 2

    # Two BRANCH (unconditional) instructions: inner loop-back and outer loop-back
    branches = _find_opcodes(instructions, Opcode.BRANCH)
    assert len(branches) >= 2

    # Two BINOP (+) for the two increment operations
    binops = _find_opcodes(instructions, Opcode.BINOP)
    plus_ops = [b for b in binops if b.operands[0] == "+"]
    assert len(plus_ops) == 2

    # Inner BRANCH_IF's true-target must NOT equal outer BRANCH_IF's true-target
    # (inner exits to outer's incr, not the same exit as outer)
    outer_true = branch_ifs[0].operands[1]
    inner_true = branch_ifs[1].operands[1]
    assert outer_true != inner_true
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run python -m pytest "tests/unit/test_cobol_frontend.py::TestPerformLoopLowering::test_perform_varying_after_test_before_emits_nested_loops" -v
```

Expected: FAIL — only 1 `BRANCH_IF` (existing single-variable behaviour ignores after_specs).

- [ ] **Step 3: Add `_emit_test_before_level` to `lower_perform.py`**

Add the following function after `_init_varying_var`:

```python
def _emit_test_before_level(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    body_fn: "Callable[[], None]",
    when_done_label: CodeLabel,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Emit one level of a TEST BEFORE VARYING … AFTER … nested loop.

    specs[0] is the current level's variable; specs[1:] are inner AFTER variables.
    when_done_label is where to jump when this level's UNTIL fires — the
    caller passes either the whole-loop exit (outermost call) or the parent's
    incr label (inner calls), so that a fired inner UNTIL cascades to the
    parent increment rather than exiting the whole PERFORM.
    """
    spec = specs[0]
    loop_label = ctx.fresh_label("pv_loop")
    body_label = ctx.fresh_label("pv_body")
    incr_label = ctx.fresh_label("pv_incr")

    _init_varying_var(ctx, spec, materialised)

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.lower_condition(spec.condition, materialised)
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(cond_reg)),
            branch_targets=(when_done_label, body_label),
        )
    )
    ctx.emit_inst(Label_(label=body_label))

    if specs[1:]:
        _emit_test_before_level(ctx, specs[1:], body_fn, incr_label, materialised)
    else:
        body_fn()

    ctx.emit_inst(Label_(label=incr_label))
    emit_varying_increment(ctx, spec, materialised)
    ctx.emit_inst(Branch(label=loop_label))
```

Add `Callable` to the imports at the top of `lower_perform.py`:

```python
from collections.abc import Callable
```

- [ ] **Step 4: Add `_emit_test_after_varying` stub and update `lower_perform_varying` dispatch**

Update `lower_perform_varying` to dispatch on `after_specs`. Replace the entire function body:

```python
def lower_perform_varying(
    ctx: EmitContext,
    stmt: PerformStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """PERFORM ... VARYING — counter variable loop with FROM/BY/UNTIL."""
    spec = stmt.spec
    assert isinstance(spec, PerformVaryingSpec)

    all_specs: tuple[PerformVaryingSpec, ...] = (spec,) + spec.after_specs

    if len(all_specs) == 1:
        _lower_perform_varying_single(ctx, stmt, spec, materialised)
    elif spec.test_before:
        exit_label = ctx.fresh_label("pv_exit")
        body_fn = lambda: lower_perform_body(ctx, stmt, materialised)
        _emit_test_before_level(ctx, all_specs, body_fn, exit_label, materialised)
        ctx.emit_inst(Label_(label=exit_label))
    else:
        _emit_test_after_varying(ctx, all_specs, lambda: lower_perform_body(ctx, stmt, materialised), materialised)
```

Extract the existing single-variable body into a private function `_lower_perform_varying_single` immediately before `lower_perform_varying`:

```python
def _lower_perform_varying_single(
    ctx: EmitContext,
    stmt: PerformStatement,
    spec: PerformVaryingSpec,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Original single-variable PERFORM VARYING lowering — unchanged."""
    loop_label = ctx.fresh_label("perform_varying_loop")
    body_label = ctx.fresh_label("perform_varying_body")
    exit_label = ctx.fresh_label("perform_varying_exit")

    _init_varying_var(ctx, spec, materialised)

    if spec.test_before:
        ctx.emit_inst(Label_(label=loop_label))
        cond_reg = ctx.lower_condition(spec.condition, materialised)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, body_label),
            )
        )
        ctx.emit_inst(Label_(label=body_label))
        lower_perform_body(ctx, stmt, materialised)
        emit_varying_increment(ctx, spec, materialised)
        ctx.emit_inst(Branch(label=loop_label))
        ctx.emit_inst(Label_(label=exit_label))
    else:
        ctx.emit_inst(Label_(label=loop_label))
        lower_perform_body(ctx, stmt, materialised)
        emit_varying_increment(ctx, spec, materialised)
        cond_reg = ctx.lower_condition(spec.condition, materialised)
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(exit_label, loop_label),
            )
        )
        ctx.emit_inst(Label_(label=exit_label))
```

Add a stub for TEST AFTER so the dispatch compiles (full implementation in Task 5):

```python
def _emit_test_after_varying(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    body_fn: "Callable[[], None]",
    materialised: MaterialisedSectionedLayout,
) -> None:
    raise NotImplementedError("TEST AFTER with AFTER specs — implemented in Task 5")
```

- [ ] **Step 5: Run new TEST BEFORE unit test**

```bash
poetry run python -m pytest "tests/unit/test_cobol_frontend.py::TestPerformLoopLowering::test_perform_varying_after_test_before_emits_nested_loops" -v
```

Expected: PASS.

- [ ] **Step 6: Run all existing VARYING tests to confirm no regressions**

```bash
poetry run python -m pytest tests/unit/ -k "varying" -v
```

Expected: all PASS (single-variable tests still go through `_lower_perform_varying_single`).

- [ ] **Step 7: Commit**

```bash
git add interpreter/cobol/lower_perform.py tests/unit/test_cobol_frontend.py
git commit -m "feat(cobol): PERFORM VARYING AFTER TEST BEFORE — recursive nested loop lowering"
```

---

## Task 5 — Lowering: TEST AFTER multi-variable

**Files:**
- Modify: `interpreter/cobol/lower_perform.py`
- Test: `tests/unit/test_cobol_frontend.py`

- [ ] **Step 1: Write failing unit test**

In `tests/unit/test_cobol_frontend.py`, inside `class TestPerformLoopLowering`, add:

```python
@covers(CobolFeature.PERFORM_VARYING_AFTER, CobolFeature.PERFORM_TEST_AFTER)
def test_perform_varying_after_test_after_emits_cascade(self):
    """PERFORM VARYING I AFTER J TEST AFTER emits body-first cascade structure.

    Expects:
    - Two BRANCH_IF: innermost (J) first in IR, then outer (I)
    - Innermost BRANCH_IF false-target == body_label (loop back directly)
    - Outer BRANCH_IF false-target is a continue block that re-inits J then goes to body
    - Two BINOP (+) for the two increments
    """
    fields = [
        CobolField(name="WS-I", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="0"),
        CobolField(name="WS-J", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="0"),
    ]
    until_i = {
        "not": False,
        "relation": {
            "left": {"kind": "ref", "name": "WS-I"},
            "op": ">",
            "right": {"kind": "lit", "value": "2"},
        },
    }
    until_j = {
        "not": False,
        "relation": {
            "left": {"kind": "ref", "name": "WS-J"},
            "op": ">",
            "right": {"kind": "lit", "value": "3"},
        },
    }
    stmts = [
        PerformStatement(
            children=[DisplayStatement(operand=RefModOperand(name="BODY"))],
            spec=PerformVaryingSpec(
                varying_var="WS-I",
                varying_from="1",
                varying_by="1",
                condition=until_i,
                test_before=False,
                after_specs=(
                    PerformVaryingSpec(
                        varying_var="WS-J",
                        varying_from="1",
                        varying_by="1",
                        condition=until_j,
                    ),
                ),
            ),
        )
    ]
    instructions = self._lower_with_field_and_stmts(fields, stmts)

    branch_ifs = _find_opcodes(instructions, Opcode.BRANCH_IF)
    assert len(branch_ifs) == 2

    # Two BINOP (+): one for J increment, one for I increment
    binops = _find_opcodes(instructions, Opcode.BINOP)
    plus_ops = [b for b in binops if b.operands[0] == "+"]
    assert len(plus_ops) == 2

    # The two BRANCH_IF true-targets are different (innermost → outer incr, outer → exit)
    assert branch_ifs[0].operands[1] != branch_ifs[1].operands[1]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run python -m pytest "tests/unit/test_cobol_frontend.py::TestPerformLoopLowering::test_perform_varying_after_test_after_emits_cascade" -v
```

Expected: FAIL — `NotImplementedError: TEST AFTER with AFTER specs`.

- [ ] **Step 3: Implement `_emit_test_after_varying`**

Replace the stub in `interpreter/cobol/lower_perform.py` with the full implementation:

```python
def _emit_test_after_varying(
    ctx: EmitContext,
    specs: tuple[PerformVaryingSpec, ...],
    body_fn: "Callable[[], None]",
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Emit a TEST AFTER VARYING … AFTER … nested loop.

    specs[0] is the outermost (primary VARYING); specs[-1] is the innermost
    (last AFTER). All variables are initialized before the body. After the
    body, increments cascade from innermost to outermost. When an outer UNTIL
    does not fire (loop continues), all exhausted inner variables are reset.

    IR shape (2-level example, I outer, J inner):
        init I; init J
        body_label:
          [body]
          # fall through to innermost incr
        incr_J:
          J += BY_J; if UNTIL_J → incr_I; else → body_label
        incr_I:
          I += BY_I; if UNTIL_I → exit; else → continue_I
        continue_I:
          J = FROM_J; → body_label
        exit_label:
    """
    n = len(specs)
    body_label = ctx.fresh_label("pv_body")
    exit_label = ctx.fresh_label("pv_exit")
    incr_labels = tuple(ctx.fresh_label("pv_incr") for _ in range(n))
    # continue_labels[i]: reset specs[i+1..n-1] to FROM, then jump to body.
    # Only needed for levels 0..n-2; the innermost (i=n-1) loops back to body directly.
    continue_labels = tuple(ctx.fresh_label("pv_continue") for _ in range(n - 1))

    # Initialise all variables (outermost first)
    for spec in specs:
        _init_varying_var(ctx, spec, materialised)

    # Body block
    ctx.emit_inst(Label_(label=body_label))
    body_fn()
    # Fall through into innermost increment (incr_labels[n-1])

    # Increment cascade: innermost → outermost
    for i in range(n - 1, -1, -1):
        spec = specs[i]
        ctx.emit_inst(Label_(label=incr_labels[i]))
        emit_varying_increment(ctx, spec, materialised)
        cond_reg = ctx.lower_condition(spec.condition, materialised)

        true_target = exit_label if i == 0 else incr_labels[i - 1]
        # Innermost (i == n-1): false → body directly (no inner vars to reset)
        false_target = body_label if i == n - 1 else continue_labels[i]

        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(true_target, false_target),
            )
        )

    # Continue blocks: reset exhausted inner variables, re-enter body
    for i in range(n - 2, -1, -1):
        ctx.emit_inst(Label_(label=continue_labels[i]))
        for j in range(i + 1, n):
            _init_varying_var(ctx, specs[j], materialised)
        ctx.emit_inst(Branch(label=body_label))

    ctx.emit_inst(Label_(label=exit_label))
```

- [ ] **Step 4: Run new TEST AFTER unit test**

```bash
poetry run python -m pytest "tests/unit/test_cobol_frontend.py::TestPerformLoopLowering::test_perform_varying_after_test_after_emits_cascade" -v
```

Expected: PASS.

- [ ] **Step 5: Run all unit tests**

```bash
poetry run python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add interpreter/cobol/lower_perform.py tests/unit/test_cobol_frontend.py
git commit -m "feat(cobol): PERFORM VARYING AFTER TEST AFTER — iterative cascade lowering"
```

---

## Task 6 — Bridge: Serialize `after_specs`

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`

This is the Java layer. No Python tests here — correctness is validated by the integration tests in Task 7.

- [ ] **Step 1: Add `after_specs` serialization in `StatementSerializer.java`**

Locate the `VARYING` branch (~line 641). After the block that serializes `vp` (the primary VaryingPhrase, ending with `serializeUntilFields` call ~line 658), add:

```java
List<After> afters = vc.getAfters();
if (afters != null && !afters.isEmpty()) {
    JsonArray afterArr = new JsonArray();
    for (After after : afters) {
        if (after == null) continue;
        VaryingPhrase ap = after.getVaryingPhrase();
        if (ap == null) continue;
        JsonObject aObj = new JsonObject();
        if (ap.getVaryingValueStmt() != null) {
            aObj.addProperty("varying_var",
                extractValueStmtText(ap.getVaryingValueStmt()));
        }
        if (ap.getFrom() != null && ap.getFrom().getFromValueStmt() != null) {
            aObj.add("varying_from",
                serializeFromValue(ap.getFrom().getFromValueStmt()));
        }
        if (ap.getBy() != null && ap.getBy().getByValueStmt() != null) {
            aObj.addProperty("varying_by",
                extractValueStmtText(ap.getBy().getByValueStmt()));
        }
        if (ap.getUntil() != null) {
            serializeUntilFields(ap.getUntil(), aObj);
        }
        afterArr.add(aObj);
    }
    if (afterArr.size() > 0) {
        obj.add("after_specs", afterArr);
    }
}
```

Add the missing import at the top of the file (if not already present):

```java
import io.proleap.cobol.asg.metamodel.procedure.perform.After;
import io.proleap.cobol.asg.metamodel.procedure.perform.VaryingPhrase;
```

Check existing imports first — `VaryingClause` is already imported (~line 74), `VaryingPhrase` may or may not be. Add only what is missing.

- [ ] **Step 2: Build the bridge**

```bash
cd proleap-bridge && ./build.sh
```

Expected: `Done. Fat JAR: target/proleap-bridge-0.1.0-shaded.jar`

- [ ] **Step 3: Commit**

```bash
cd ..
git add proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java
git commit -m "feat(bridge): serialize PERFORM VARYING AFTER clauses into after_specs JSON array"
```

---

## Task 7 — Integration Tests

**Files:**
- Test: `tests/integration/test_cobol_programs.py`

These tests exercise the full pipeline: COBOL source → ProLeap bridge → JSON → Python → IR → VM. They require the bridge JAR built in Task 6.

- [ ] **Step 1: Write failing TEST BEFORE integration test (2×3)**

In `tests/integration/test_cobol_programs.py`, add a new class after the existing `TestPerformVarying` class:

```python
class TestPerformVaryingAfter:
    """Integration tests for PERFORM VARYING … AFTER … multi-index nested loops."""

    @covers(CobolFeature.PERFORM_VARYING_AFTER)
    def test_perform_varying_after_test_before_2x3(self):
        """PERFORM VARYING I AFTER J (TEST BEFORE) runs body 2×3=6 times.

        WS-I varies 1..2, WS-J varies 1..3 — 6 body executions, each adds 1
        to WS-CNT, so WS-CNT must equal 6 at program exit.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PVAFTER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-CNT PIC 9(4) VALUE 0.",
                "01 WS-I   PIC 9(4) VALUE 0.",
                "01 WS-J   PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 2",
                "        AFTER WS-J FROM 1 BY 1 UNTIL WS-J > 3",
                "            ADD 1 TO WS-CNT",
                "    END-PERFORM.",
                "    STOP RUN.",
            ],
            max_steps=5000,
        )
        region = _first_region(vm)
        # WS-CNT at offset 0 (first field, PIC 9(4))
        assert _decode_zoned_unsigned(region, 0, 4) == 6
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run python -m pytest "tests/integration/test_cobol_programs.py::TestPerformVaryingAfter::test_perform_varying_after_test_before_2x3" -v
```

Expected: FAIL — bridge does not yet emit `after_specs` (or, if Task 6 is done, the loop counter will be wrong because only a single-variable loop ran).

- [ ] **Step 3: Verify it passes (Task 6 must be complete first)**

After rebuilding the bridge in Task 6:

```bash
poetry run python -m pytest "tests/integration/test_cobol_programs.py::TestPerformVaryingAfter::test_perform_varying_after_test_before_2x3" -v
```

Expected: PASS. WS-CNT decoded as 6.

- [ ] **Step 4: Add TEST BEFORE 3-level smoke test**

In `TestPerformVaryingAfter`, add:

```python
@covers(CobolFeature.PERFORM_VARYING_AFTER)
def test_perform_varying_after_test_before_3_levels(self):
    """PERFORM VARYING I AFTER J AFTER K (TEST BEFORE) runs body 2×2×2=8 times."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. TEST-PV3LVL.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-CNT PIC 9(4) VALUE 0.",
            "01 WS-I   PIC 9(4) VALUE 0.",
            "01 WS-J   PIC 9(4) VALUE 0.",
            "01 WS-K   PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 2",
            "        AFTER WS-J FROM 1 BY 1 UNTIL WS-J > 2",
            "        AFTER WS-K FROM 1 BY 1 UNTIL WS-K > 2",
            "            ADD 1 TO WS-CNT",
            "    END-PERFORM.",
            "    STOP RUN.",
        ],
        max_steps=10000,
    )
    region = _first_region(vm)
    assert _decode_zoned_unsigned(region, 0, 4) == 8
```

- [ ] **Step 5: Run 3-level test**

```bash
poetry run python -m pytest "tests/integration/test_cobol_programs.py::TestPerformVaryingAfter::test_perform_varying_after_test_before_3_levels" -v
```

Expected: PASS.

- [ ] **Step 6: Add TEST AFTER integration test**

In `TestPerformVaryingAfter`, add:

```python
@covers(CobolFeature.PERFORM_VARYING_AFTER, CobolFeature.PERFORM_TEST_AFTER)
def test_perform_varying_after_test_after_2x3(self):
    """PERFORM VARYING I AFTER J TEST AFTER runs body 2×3=6 times.

    TEST AFTER executes the body before checking UNTIL, so with I ranging
    1..2 and J ranging 1..3 the body still runs 6 times and WS-CNT == 6.
    """
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. TEST-PVTA.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-CNT PIC 9(4) VALUE 0.",
            "01 WS-I   PIC 9(4) VALUE 0.",
            "01 WS-J   PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 2",
            "        AFTER WS-J FROM 1 BY 1 UNTIL WS-J > 3",
            "        TEST AFTER",
            "            ADD 1 TO WS-CNT",
            "    END-PERFORM.",
            "    STOP RUN.",
        ],
        max_steps=5000,
    )
    region = _first_region(vm)
    assert _decode_zoned_unsigned(region, 0, 4) == 6
```

- [ ] **Step 7: Run TEST AFTER integration test**

```bash
poetry run python -m pytest "tests/integration/test_cobol_programs.py::TestPerformVaryingAfter::test_perform_varying_after_test_after_2x3" -v
```

Expected: PASS.

- [ ] **Step 8: Run full integration test class**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestPerformVaryingAfter -v
```

Expected: 3 PASS.

- [ ] **Step 9: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -10
```

Expected: all tests PASS, count higher than before by the new tests.

- [ ] **Step 10: Commit**

```bash
git add tests/integration/test_cobol_programs.py
git commit -m "test(cobol): integration tests for PERFORM VARYING AFTER — TEST BEFORE and TEST AFTER"
```

---

## Task 8 — Format and final check

- [ ] **Step 1: Run Black**

```bash
poetry run python -m black interpreter/cobol/cobol_statements.py interpreter/cobol/lower_perform.py tests/unit/test_cobol_statements.py tests/unit/test_cobol_frontend.py tests/integration/test_cobol_programs.py
```

- [ ] **Step 2: Run full suite one last time**

```bash
poetry run python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "style: black formatting for perform-varying-after changes"
```
