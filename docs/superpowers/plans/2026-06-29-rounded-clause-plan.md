# ROUNDED_CLAUSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `ROUNDED` modifier for all COBOL arithmetic verbs (ADD, SUBTRACT, MULTIPLY, DIVIDE, COMPUTE), closing `CobolFeature.ROUNDED_CLAUSE` (red-dragon-4q25.4).

**Architecture:** Rounding is per-target (each result field can independently request it). The ProLeap bridge must serialize `isRounded()` for each target; `RefModOperand` gains a `rounded: bool` field; `ComputeStatement.targets` migrates from `list[str]` to `list[ComputeTarget]`; a new `__cobol_round` builtin applies half-away-from-zero rounding; `_emit_arithmetic_writeback` and `lower_compute` emit the builtin call when `rounded=True`, replacing `result_str_reg` before the existing `emit_encode_and_write` call. The encode pipeline (`align_decimal`, `__cobol_prepare_digits`, IR encoders) is untouched.

**Tech Stack:** Python (`decimal.ROUND_HALF_UP`), Java (ProLeap bridge `isRounded()` API), existing `byte_builtins.py` and `lower_arithmetic.py` patterns.

## Global Constraints

- `ROUND_HALF_UP` (half-away-from-zero) — not Python's default `ROUND_HALF_EVEN` — for all rounding.
- `decimal_digits` for a target is `fl.type_descriptor.decimal_digits` (0 for integer PIC — rounding still applies, e.g. `2.7 → 3`).
- `__cobol_round` must return `_UNCOMPUTABLE` if any argument is symbolic.
- Bridge JAR rebuild required after any Java change: `cd proleap-bridge && mvn package -q -DskipTests`.
- TDD: write the failing integration test BEFORE implementing the lowering hook (Tasks 1 and 6).
- `test_all_builtins_registered` must include `"__cobol_round"`.
- No comments added to code unless the WHY is non-obvious.
- Run `poetry run python -m black .` on the full repo before each commit.
- Full test suite: `poetry run python -m pytest tests/unit tests/integration -x`.
- NEVER reference external codebases, names, APIs, domains, or packages in any tracked artifact.

---

## File Map

| File | Change |
|------|--------|
| `tests/integration/test_cobol_programs.py` | New `TestRoundedClause` class + `_decode_zoned_with_decimal` helper |
| `tests/integration/cobol_helpers.py` | Add `decode_zoned_with_decimal` function |
| `interpreter/cobol/cobol_constants.py` | Add `BuiltinName.COBOL_ROUND = "__cobol_round"` |
| `interpreter/cobol/byte_builtins.py` | Add `_builtin_cobol_round` + register in `BYTE_BUILTINS` |
| `tests/unit/test_byte_builtins.py` | Add unit test + extend `test_all_builtins_registered` |
| `interpreter/cobol/ref_mod.py` | Add `rounded: bool = False` to `RefModOperand` |
| `interpreter/cobol/cobol_statements.py` | Add `ComputeTarget`; migrate `ComputeStatement.targets: list[ComputeTarget]` |
| `proleap-bridge/src/main/java/.../StatementSerializer.java` | Serialize `isRounded()` for all arithmetic verb targets |
| `interpreter/cobol/lower_arithmetic.py` | Rounding block in `_emit_arithmetic_writeback` and `lower_compute` |
| `docs/architectural-design-decisions.md` | New ADR entry |
| `beads/issues.jsonl` | Close red-dragon-4q25.4 |

---

### Task 1: Failing Integration Tests + Decode Helper

Write the failing integration tests that drive all downstream implementation. These tests will remain failing until Task 6.

**Files:**
- Modify: `tests/integration/cobol_helpers.py` (add helper)
- Modify: `tests/integration/test_cobol_programs.py` (add test class)

**Interfaces:**
- Consumes: `CobolFeature.ROUNDED_CLAUSE` (already in `interpreter/cobol/features.py`), `decode_zoned_unsigned` pattern from `cobol_helpers.py`
- Produces: `decode_zoned_with_decimal(region, offset, integer_digits, decimal_digits) -> Decimal`; `TestRoundedClause.test_add_rounded_*` and `test_compute_rounded_*`

- [ ] **Step 1: Add `decode_zoned_with_decimal` to `cobol_helpers.py`**

Add after the existing `decode_zoned_unsigned` function (around line 42):

```python
def decode_zoned_with_decimal(
    region: bytearray, offset: int, integer_digits: int, decimal_digits: int
) -> "Decimal":
    from decimal import Decimal

    n = integer_digits + decimal_digits
    digits = [region[offset + i] & 0x0F for i in range(n)]
    raw = sum(d * (10 ** (n - 1 - i)) for i, d in enumerate(digits))
    return Decimal(raw) / Decimal(10**decimal_digits)
```

- [ ] **Step 2: Add `decode_zoned_with_decimal` to the imports in `test_cobol_programs.py`**

Modify the import block at line 23–27 to add `decode_zoned_with_decimal`:

```python
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode_zoned_unsigned,
    decode_zoned_with_decimal as _decode_zoned_with_decimal,
    to_fixed as _to_fixed,
)
```

Also add at the top of the file:

```python
from decimal import Decimal
```

- [ ] **Step 3: Write the failing integration test class**

Add `TestRoundedClause` near the end of `test_cobol_programs.py` (before any IO-related test classes):

```python
class TestRoundedClause:
    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_add_rounded_rounds_to_nearest(self):
        # 1.23 + 0.007 = 1.237; with ROUNDED→ 1.24, without → 1.23
        vm = _run_cobol([
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ROUNDED-TEST.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-X PIC 9(3)V9(2) VALUE 1.23.",
            "PROCEDURE DIVISION.",
            "MAIN.",
            "    ADD 0.007 TO WS-X ROUNDED.",
            "    STOP RUN.",
        ])
        region = _first_region(vm)
        assert _decode_zoned_with_decimal(region, 0, 3, 2) == Decimal("1.24")

    def test_add_without_rounded_truncates(self):
        vm = _run_cobol([
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ROUNDED-TEST.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-X PIC 9(3)V9(2) VALUE 1.23.",
            "PROCEDURE DIVISION.",
            "MAIN.",
            "    ADD 0.007 TO WS-X.",
            "    STOP RUN.",
        ])
        region = _first_region(vm)
        assert _decode_zoned_with_decimal(region, 0, 3, 2) == Decimal("1.23")

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_compute_rounded_integer(self):
        # 10 / 6 = 1.666...; PIC 9(3) with ROUNDED → 2, without → 1
        vm = _run_cobol([
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ROUNDED-TEST.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-X PIC 9(3) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN.",
            "    COMPUTE WS-X ROUNDED = 10 / 6.",
            "    STOP RUN.",
        ])
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 3) == 2

    def test_compute_without_rounded_truncates(self):
        vm = _run_cobol([
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ROUNDED-TEST.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-X PIC 9(3) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN.",
            "    COMPUTE WS-X = 10 / 6.",
            "    STOP RUN.",
        ])
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 3) == 1
```

- [ ] **Step 4: Run the tests and confirm they fail**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestRoundedClause -v
```

Expected: `test_add_rounded_rounds_to_nearest` fails (result is `1.23`, not `1.24`). `test_add_without_rounded_truncates` may pass (truncation already works). `test_compute_rounded_integer` fails (result is `1`, not `2`).

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add tests/integration/cobol_helpers.py tests/integration/test_cobol_programs.py
git commit -m "test(cobol): failing integration tests for ROUNDED_CLAUSE arithmetic rounding"
```

---

### Task 2: `__cobol_round` Builtin

Add the rounding primitive that all lowering code will call. TDD: add the registration test entry first.

**Files:**
- Modify: `interpreter/cobol/cobol_constants.py`
- Modify: `interpreter/cobol/byte_builtins.py`
- Modify: `tests/unit/test_byte_builtins.py`

**Interfaces:**
- Consumes: `BuiltinResult`, `TypedValue`, `VMState`, `_is_symbolic`, `_UNCOMPUTABLE` (all already used in `byte_builtins.py`)
- Produces: `BuiltinName.COBOL_ROUND = "__cobol_round"`, `_builtin_cobol_round(args, vm) -> BuiltinResult` where `args[0].value` is a numeric string and `args[1].value` is `int` decimal_digits

- [ ] **Step 1: Add `"__cobol_round"` to `test_all_builtins_registered` (makes the test fail)**

In `tests/unit/test_byte_builtins.py`, find `test_all_builtins_registered` and add `"__cobol_round"` to the `expected_names` list. Add it after `"__cobol_blank_when_zero"`.

- [ ] **Step 2: Run to confirm the registration test fails**

```bash
poetry run python -m pytest tests/unit/test_byte_builtins.py -k "test_all_builtins_registered" -v
```

Expected: FAIL — `Missing __cobol_round`.

- [ ] **Step 3: Add `COBOL_ROUND` to `BuiltinName` in `cobol_constants.py`**

In `interpreter/cobol/cobol_constants.py`, add to the `BuiltinName` class after `COBOL_BLANK_WHEN_ZERO`:

```python
COBOL_ROUND = "__cobol_round"
```

- [ ] **Step 4: Implement `_builtin_cobol_round` in `byte_builtins.py`**

Add this function after `_builtin_cobol_blank_when_zero`:

```python
def _builtin_cobol_round(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from decimal import Decimal, ROUND_HALF_UP

    decimal_digits = int(args[1].value)
    quantizer = Decimal(10) ** -decimal_digits
    d = Decimal(str(args[0].value)).quantize(quantizer, rounding=ROUND_HALF_UP)
    return BuiltinResult(value=str(d))
```

- [ ] **Step 5: Register in `BYTE_BUILTINS`**

In `byte_builtins.py`, add to the `BYTE_BUILTINS` dict (around line 987, after `COBOL_BLANK_WHEN_ZERO`):

```python
FuncName(BuiltinName.COBOL_ROUND): _builtin_cobol_round,
```

- [ ] **Step 6: Add unit test class for the builtin**

Add a new test class in `tests/unit/test_byte_builtins.py` (also import `_builtin_cobol_round` at the top alongside the other imports):

```python
class TestCobolRound:
    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounds_up_at_halfway(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("1.235"), typed_from_runtime(2)], None
        )
        assert result.value == "1.24"

    def test_rounds_down_below_halfway(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("1.234"), typed_from_runtime(2)], None
        )
        assert result.value == "1.23"

    def test_rounds_away_from_zero_for_negatives(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("-1.235"), typed_from_runtime(2)], None
        )
        assert result.value == "-1.24"

    def test_zero_decimal_digits_rounds_to_integer(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("2.7"), typed_from_runtime(0)], None
        )
        assert result.value == "3"

    def test_zero_decimal_digits_rounds_down(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("2.3"), typed_from_runtime(0)], None
        )
        assert result.value == "2"

    def test_symbolic_returns_uncomputable(self):
        sym = typed_from_runtime(Operators.UNCOMPUTABLE)
        result = _builtin_cobol_round([sym, typed_from_runtime(2)], None)
        assert result.value == _UNCOMPUTABLE
```

Add `from interpreter.vm.vm import Operators` if not already imported. `_UNCOMPUTABLE = Operators.UNCOMPUTABLE` is already defined at the top of the test file.

- [ ] **Step 7: Run unit tests to confirm they all pass**

```bash
poetry run python -m pytest tests/unit/test_byte_builtins.py -v
```

Expected: All pass, including `test_all_builtins_registered`.

- [ ] **Step 8: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cobol/cobol_constants.py interpreter/cobol/byte_builtins.py tests/unit/test_byte_builtins.py
git commit -m "feat(cobol): add __cobol_round builtin for half-away-from-zero rounding"
```

---

### Task 3: Data Structures — `RefModOperand.rounded` + `ComputeTarget`

Add `rounded` to the operand types. This is pure data — no behavior change yet.

**Files:**
- Modify: `interpreter/cobol/ref_mod.py`
- Modify: `interpreter/cobol/cobol_statements.py`

**Interfaces:**
- Produces:
  - `RefModOperand.rounded: bool = False` — read by `from_dict({"rounded": True, ...})`
  - `ComputeTarget(name: str, rounded: bool = False)` with `from_dict` and `to_dict`
  - `ComputeStatement.targets: list[ComputeTarget]` — callers that previously iterated `str` now iterate `ComputeTarget.name`

- [ ] **Step 1: Add `rounded` field to `RefModOperand`**

In `interpreter/cobol/ref_mod.py`, add `rounded: bool = False` to the `RefModOperand` dataclass (after `subscripts`, line ~150):

```python
@dataclass(frozen=True)
class RefModOperand:
    name: str
    ref_mod_start: RefModExpr | None = None
    ref_mod_length: RefModExpr | None = None
    length_of: str = ""
    qualifiers: tuple[str, ...] = ()
    subscripts: tuple[ExprNode, ...] = ()
    rounded: bool = False
```

- [ ] **Step 2: Update `RefModOperand.from_dict` to read `rounded`**

In the `from_dict` classmethod (after constructing `subscripts`, before the final `return cls(...)`):

```python
        rounded = data.get("rounded", False) if isinstance(data, dict) else False

        return cls(
            name=name,
            ref_mod_start=ref_mod_start,
            ref_mod_length=ref_mod_length,
            qualifiers=qualifiers,
            subscripts=subscripts,
            rounded=rounded,
        )
```

- [ ] **Step 3: Update `RefModOperand.to_dict` to emit `rounded`**

In `to_dict`, after building the base dict but before returning, add:

```python
        if self.rounded:
            d["rounded"] = True
```

(omit when `False` to keep JSON compact — matches the existing pattern of omitting empty fields).

- [ ] **Step 4: Add `ComputeTarget` dataclass to `cobol_statements.py`**

Add this frozen dataclass near the top of `interpreter/cobol/cobol_statements.py`, before `ComputeStatement` (imports may need `from __future__ import annotations` which should already be present):

```python
@dataclass(frozen=True)
class ComputeTarget:
    name: str
    rounded: bool = False

    @classmethod
    def from_dict(cls, data: dict | str) -> "ComputeTarget":
        if isinstance(data, str):
            return cls(name=data)
        return cls(name=data["name"], rounded=data.get("rounded", False))

    def to_dict(self) -> dict:
        d: dict = {"name": self.name}
        if self.rounded:
            d["rounded"] = True
        return d
```

- [ ] **Step 5: Migrate `ComputeStatement.targets` from `list[str]` to `list[ComputeTarget]`**

In `ComputeStatement`:
- Change field: `targets: list[ComputeTarget] = field(default_factory=list)`
- Update `from_dict`:
  ```python
  targets=[ComputeTarget.from_dict(t) for t in data.get("targets", [])],
  ```
- Update `to_dict`:
  ```python
  if self.targets:
      result["targets"] = [t.to_dict() for t in self.targets]
  ```

- [ ] **Step 6: Update `lower_compute` in `lower_arithmetic.py` to use `target.name`**

In `lower_compute` (around line 1115), change all `target_name` references to use `target.name`. The function currently iterates `for target_name in stmt.targets:`. Change to `for target in stmt.targets:` and replace all `target_name` with `target.name`. Do NOT add the rounding block yet — that's Task 6.

Fast path (no SIZE ERROR), roughly lines 1112–1125:
```python
        for target in stmt.targets:
            if not ctx.has_field(target.name, materialised):
                logger.warning("COMPUTE target %s not found in layout", target.name)
                continue
            target_ref, target_rr = ctx.resolve_field_ref(target.name, materialised)
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, result_str_reg, target_ref.offset_reg
            )
```

ON SIZE ERROR path — change `target_pairs: list[tuple]` to `target_triples: list[tuple]` storing `(ref, rr, target)`:
```python
        target_triples: list[tuple] = []
        for target in stmt.targets:
            if not ctx.has_field(target.name, materialised):
                logger.warning("COMPUTE target %s not found in layout", target.name)
                continue
            ref, rr = ctx.resolve_field_ref(target.name, materialised)
            target_triples.append((ref, rr, target))
```

Update the overflow flag loop (which references `target_pairs`) to use `target_triples`:
```python
        overflow_flags = [
            _compute_overflow_flag(ctx, result_reg, ref.fl.type_descriptor)
            for ref, rr, _ in target_triples
        ]
```

Update the writeback loop in the `not_on_size_err_label` block:
```python
        for ref, rr, _ in target_triples:
            ctx.emit_encode_and_write(rr, ref.fl, result_str_reg, ref.offset_reg)
```

(The `_` placeholder holds the ComputeTarget but rounding is not wired yet — that's Task 6.)

- [ ] **Step 7: Run the unit tests to verify nothing broke**

```bash
poetry run python -m pytest tests/unit/ -x -q
```

Expected: All unit tests pass. Integration test `test_add_rounded_rounds_to_nearest` still fails (expected — rounding not yet in pipeline).

- [ ] **Step 8: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cobol/ref_mod.py interpreter/cobol/cobol_statements.py interpreter/cobol/lower_arithmetic.py
git commit -m "feat(cobol): add RefModOperand.rounded and ComputeTarget for ROUNDED_CLAUSE"
```

---

### Task 4: Bridge Java Serialization

Serialize `isRounded()` for every arithmetic verb target. **This task requires rebuilding the JAR after Java changes.**

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`

**Background:** ProLeap's ASG already captures ROUNDED — `To`, `From`, `Into`, `ByOperand`, `Giving`, `Store` classes all have `isRounded()`. The bridge currently calls `serializeRef(call)` which returns a `JsonObject` (a dict on the Python side). We need to add `"rounded": true/false` to that object for each target type.

The relevant Java classes per verb:
- **ADD TO**: `addTo.getTos()` → each `To` has `to.isRounded()` and `to.getToCall()`
- **ADD GIVING**: `addGiving.getGivings()` → each `Giving` has `g.isRounded()` and `g.getGivingCall()`
- **SUBTRACT FROM**: `subtractFrom.getFroms()` → each `From` target has `f.isRounded()` and `f.getFromCall()`
- **SUBTRACT GIVING**: `subtractGiving.getGivings()` → `g.isRounded()`
- **MULTIPLY BY**: `multiplyBy.getByOperands()` → each `ByOperand` has `b.isRounded()`
- **MULTIPLY GIVING**: `multiplyGiving.getGivingPhrases()` → each giving has `.isRounded()`
- **DIVIDE INTO**: `divideInto.getDivideIntoStatements()` → each into has `.isRounded()`
- **DIVIDE GIVING**: `divideGiving.getGivingPhrase()` → `.isRounded()`
- **COMPUTE**: `stmt.getStores()` → each `Store` has `store.isRounded()`

**Pattern for ADD TO** (apply analogously to all verbs):

Before change:
```java
for (To to : addTo.getTos()) {
    operands.add(serializeRef(to.getToCall()));
}
```

After change:
```java
for (To to : addTo.getTos()) {
    JsonObject t = serializeRef(to.getToCall());
    t.addProperty("rounded", to.isRounded());
    operands.add(t);
}
```

**Pattern for COMPUTE** (currently emits plain string; change to object):

Before change:
```java
for (Store store : stmt.getStores()) {
    Call storeCall = store.getStoreCall();
    if (storeCall != null) {
        targets.add(extractCallName(storeCall));
    }
}
```

After change:
```java
for (Store store : stmt.getStores()) {
    Call storeCall = store.getStoreCall();
    if (storeCall != null) {
        JsonObject t = new JsonObject();
        t.addProperty("name", extractCallName(storeCall));
        t.addProperty("rounded", store.isRounded());
        targets.add(t);
    }
}
```

- [ ] **Step 1: Apply the ADD change in `StatementSerializer.java`**

Find `serializeAdd` and update the `addTo.getTos()` loop and `addGiving.getGivings()` loop per the pattern above.

- [ ] **Step 2: Apply the same pattern to SUBTRACT, MULTIPLY, DIVIDE**

Find `serializeSubtract`, `serializeMultiply`, `serializeDivide` and add `t.addProperty("rounded", x.isRounded())` to each target object in their loops.

- [ ] **Step 3: Apply the COMPUTE change in `serializeCompute`**

Change `targets.add(extractCallName(storeCall))` to the object form shown above.

- [ ] **Step 4: Rebuild the JAR**

```bash
cd proleap-bridge && mvn package -q -DskipTests && cd ..
```

Expected: BUILD SUCCESS with no output.

- [ ] **Step 5: Verify the bridge serializes `rounded` correctly**

Quick smoke check — run one existing COBOL arithmetic integration test:

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestArithmetic -x -q
```

Expected: All pass. (Bridge changes are backward-compatible — `rounded: false` for un-rounded targets.)

- [ ] **Step 6: Commit**

```bash
git add proleap-bridge/
git commit -m "feat(bridge): serialize isRounded() for all arithmetic verb targets (ROUNDED_CLAUSE)"
```

---

### Task 5: Arithmetic Verb Lowering — `_emit_arithmetic_writeback`

Wire `__cobol_round` into the writeback for ADD/SUBTRACT/MULTIPLY/DIVIDE targets.

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py`

**Background:** `_emit_arithmetic_writeback` (around line 648) takes `target_op: RefModOperand` which now has `target_op.rounded: bool`. The function's non-ref-mod path is at line 729–730:
```python
    else:
        ctx.emit_encode_and_write(target_rr, fl, result_str_reg, offset_reg)
```

Add the rounding block immediately before `emit_encode_and_write` in that `else` branch. `CallFunction` is already imported.

**Interfaces:**
- Consumes: `BuiltinName.COBOL_ROUND` (from Task 2), `target_op.rounded` (from Task 3), `fl.type_descriptor.decimal_digits` (already on `ResolvedFieldRef.fl`)
- Produces: `_emit_arithmetic_writeback` rounds `result_str_reg` via `__cobol_round` when `target_op.rounded=True`

- [ ] **Step 1: Add the rounding block to `_emit_arithmetic_writeback`**

Change lines 729–730 in `lower_arithmetic.py` from:
```python
    else:
        ctx.emit_encode_and_write(target_rr, fl, result_str_reg, offset_reg)
```

To:
```python
    else:
        if target_op.rounded:
            dec_digits_reg = ctx.const_to_reg(fl.type_descriptor.decimal_digits)
            rounded_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=rounded_reg,
                    func_name=FuncName(BuiltinName.COBOL_ROUND),
                    args=(result_str_reg, dec_digits_reg),
                )
            )
            result_str_reg = rounded_reg
        ctx.emit_encode_and_write(target_rr, fl, result_str_reg, offset_reg)
```

`FuncName` and `CallFunction` are already imported in this file. Verify `BuiltinName` is imported (it already is, line ~9 of imports shown earlier).

- [ ] **Step 2: Run the ADD ROUNDED integration test**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestRoundedClause::test_add_rounded_rounds_to_nearest -v
```

Expected: PASS. `1.237` rounded to 2 decimal places → `1.24`.

- [ ] **Step 3: Run the ADD non-ROUNDED regression test**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestRoundedClause::test_add_without_rounded_truncates -v
```

Expected: PASS. `1.237` truncated → `1.23`.

- [ ] **Step 4: Run full arithmetic integration tests to check for regressions**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py -x -q
```

Expected: All pass (or same pass rate as before, minus `test_compute_rounded_integer` which still fails).

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cobol/lower_arithmetic.py
git commit -m "feat(cobol): apply ROUNDED rounding in arithmetic verb writeback via __cobol_round"
```

---

### Task 6: COMPUTE Lowering

Wire `__cobol_round` into `lower_compute`. This is the last implementation step — after this, the `test_compute_rounded_integer` test from Task 1 passes.

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py` (the `lower_compute` function, around line 1102)

**Background:** After Task 3, `lower_compute` iterates `ComputeTarget` objects via `target_triples`. The `target.rounded` flag is available but unused. Add the rounding block in both writeback paths.

**Interfaces:**
- Consumes: `ComputeTarget.rounded`, `BuiltinName.COBOL_ROUND`, `CallFunction`, `FuncName` — all already in scope

- [ ] **Step 1: Add rounding to the fast path in `lower_compute`**

Change the fast path writeback (no ON SIZE ERROR) from:
```python
            target_ref, target_rr = ctx.resolve_field_ref(target.name, materialised)
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, result_str_reg, target_ref.offset_reg
            )
```

To:
```python
            target_ref, target_rr = ctx.resolve_field_ref(target.name, materialised)
            write_reg = result_str_reg
            if target.rounded:
                dec_digits_reg = ctx.const_to_reg(
                    target_ref.fl.type_descriptor.decimal_digits
                )
                rounded_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=rounded_reg,
                        func_name=FuncName(BuiltinName.COBOL_ROUND),
                        args=(write_reg, dec_digits_reg),
                    )
                )
                write_reg = rounded_reg
            ctx.emit_encode_and_write(
                target_rr, target_ref.fl, write_reg, target_ref.offset_reg
            )
```

- [ ] **Step 2: Add rounding to the ON SIZE ERROR path in `lower_compute`**

Change the `not_on_size_err_label` writeback from:
```python
        for ref, rr, _ in target_triples:
            ctx.emit_encode_and_write(rr, ref.fl, result_str_reg, ref.offset_reg)
```

To:
```python
        for ref, rr, target in target_triples:
            write_reg = result_str_reg
            if target.rounded:
                dec_digits_reg = ctx.const_to_reg(
                    ref.fl.type_descriptor.decimal_digits
                )
                rounded_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=rounded_reg,
                        func_name=FuncName(BuiltinName.COBOL_ROUND),
                        args=(write_reg, dec_digits_reg),
                    )
                )
                write_reg = rounded_reg
            ctx.emit_encode_and_write(rr, ref.fl, write_reg, ref.offset_reg)
```

- [ ] **Step 3: Run the COMPUTE ROUNDED integration test**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestRoundedClause -v
```

Expected: All four tests in `TestRoundedClause` pass.

- [ ] **Step 4: Run full unit + integration suite**

```bash
poetry run python -m pytest tests/unit tests/integration -x -q
```

Expected: All tests pass (same count as before Task 1 plus the 4 new tests).

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cobol/lower_arithmetic.py
git commit -m "feat(cobol): apply ROUNDED rounding in COMPUTE target writeback (closes ROUNDED_CLAUSE)"
```

---

### Task 7: Housekeeping — ADR, Beads, Feature Coverage, Push

Close the tracking issue, add the ADR, verify coverage, push.

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `beads/issues.jsonl`

- [ ] **Step 1: Add ADR entry to `docs/architectural-design-decisions.md`**

Append at the end of the file:

```markdown
---

### ADR-NNN: COBOL ROUNDED CLAUSE — pre-round via `__cobol_round` builtin (2026-06-29)

**Context:** The COBOL `ROUNDED` modifier on arithmetic targets requires half-away-from-zero rounding of the computed result before it is stored to the target field. The existing encode pipeline (`align_decimal`, `__cobol_prepare_digits`) performs truncation by design. Three approaches were considered: (A) a new `ROUND_HALF_UP` mode threaded through `align_decimal`; (B) a standalone `__cobol_round` builtin injected before `emit_encode_and_write`; (C) post-encode integer arithmetic.

**Decision:** Approach B — inject a `__cobol_round(value_str, decimal_digits)` call in `_emit_arithmetic_writeback` and `lower_compute` when `target.rounded = True`. The builtin uses Python's `decimal.ROUND_HALF_UP`. The encode pipeline is not touched. `RefModOperand` gains `rounded: bool`; `ComputeStatement.targets` migrates to `list[ComputeTarget]` to carry the per-target flag. The ProLeap bridge serializes `isRounded()` from the ASG for all arithmetic verb targets.

**Consequences:** The encode pipeline remains stable; adding ROUNDED support to any future arithmetic verb only requires plumbing `rounded` through its target operand type and calling `__cobol_round` before the existing writeback. The `decimal` import is deferred to call time to avoid module-level overhead. `ComputeStatement.targets` is now `list[ComputeTarget]` — a narrow breaking change within `lower_arithmetic.py` (no external callers).
```

Replace `NNN` with the next ADR number (count existing `### ADR-` entries and add 1).

- [ ] **Step 2: Close issue red-dragon-4q25.4 in `beads/issues.jsonl`**

Append a single JSON line closing the issue (replace `YYYY-MM-DDThh:mm:ssZ` with the current UTC timestamp):

```json
{"_type":"issue","id":"red-dragon-4q25.4","status":"closed","updated_at":"2026-06-29T00:00:00Z","closed_at":"2026-06-29T00:00:00Z","close_reason":"ROUNDED_CLAUSE implemented: __cobol_round builtin (decimal.ROUND_HALF_UP), RefModOperand.rounded, ComputeTarget, bridge isRounded() serialization for all verbs. 4 integration tests green. CobolFeature.ROUNDED_CLAUSE now covered."}
```

**Do not modify any existing lines** — `beads/issues.jsonl` is append-only.

- [ ] **Step 3: Verify `CobolFeature.ROUNDED_CLAUSE` is now covered**

```bash
poetry run python scripts/feature_coverage_audit.py 2>&1 | grep -E "COBOL|uncovered|ROUNDED"
```

Expected: `ROUNDED_CLAUSE` no longer appears as uncovered.

- [ ] **Step 4: Run full test suite one final time**

```bash
poetry run python -m pytest tests/unit tests/integration -q
```

Expected: All tests pass.

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add docs/architectural-design-decisions.md beads/issues.jsonl
git commit -m "docs: ADR and Beads close for ROUNDED_CLAUSE (red-dragon-4q25.4)"
```

- [ ] **Step 6: Push**

```bash
git push
```

---

## Self-Review

**Spec coverage check:**
- Task 1: builtin `__cobol_round` ✓
- Task 2: data structures (`RefModOperand.rounded`, `ComputeTarget`, `ComputeStatement.targets`) ✓
- Task 3: bridge serialization for all verbs ✓
- Task 4: arithmetic verb lowering via `_emit_arithmetic_writeback` ✓
- Task 5: COMPUTE lowering ✓
- Task 6: integration tests (ADD ROUNDED, ADD non-ROUNDED, COMPUTE ROUNDED, COMPUTE non-ROUNDED) ✓
- Spec also called for `ComputeStatement.to_dict()` update ✓ (covered in Task 3 Step 5)
- Spec called for ADR + Beads close ✓ (Task 7)

**Missing from spec that plan covers additionally:**
- `decode_zoned_with_decimal` helper needed by tests — added to `cobol_helpers.py` (Task 1)
- `Decimal` import needed in test file — noted in Task 1
- ON SIZE ERROR path in `lower_compute` also needs rounding — covered in Task 6 Step 2
- `target_pairs` rename to `target_triples` for clarity — covered in Task 3 Step 6

**Placeholder scan:** None found.

**Type consistency:** `ComputeTarget.from_dict` defined in Task 3, consumed in Task 3 (`ComputeStatement.from_dict`). `BuiltinName.COBOL_ROUND` defined in Task 2, consumed in Tasks 5 and 6. `RefModOperand.rounded` defined in Task 3, consumed in Task 5 via `target_op.rounded`. All consistent.
