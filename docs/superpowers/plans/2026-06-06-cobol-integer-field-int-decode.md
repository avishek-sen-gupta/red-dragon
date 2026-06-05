# COBOL Integer Fields Decode to `int` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make COBOL integer fields (`PIC 9(n)` / `S9(n)` with zero decimal places) decode and compute as Python `int` instead of `float`, fixing silent corruption of integers beyond 2^53 (e.g. `PIC 9(18)`) and the cosmetic `7.0`; also stop a spurious "bare heap address" warning.

**Architecture:** Four integer-capable decode builders in `interpreter/cobol/ir_encoders.py` each deliberately convert the accumulated integer to `float` in their `decimal_digits == 0` branch. Remove that conversion so the `int` accumulator flows through unchanged. The encode path is string-based (`str(value)` → `COBOL_PREPARE_DIGITS`), so `str(7)`→`"7"` works as well as `str(7.0)`→`"7.0"` — no encode changes needed. Separately, tighten the warning guard in `_unwrap_builtin_result` so plain numeric strings no longer trip a heap-address check. Decimal fields (`decimal_digits > 0`) and COMP-1/COMP-2 stay float (out of scope — that's red-dragon-4q25.1).

**Tech Stack:** Python 3.13 (poetry, pytest, pytest-xdist), the COBOL IR encoders/decoders, the VM `_execute_ir` test harness, the ProLeap COBOL bridge (`PROLEAP_BRIDGE_JAR`) for the integration test.

**Spec:** `docs/superpowers/specs/2026-06-06-cobol-integer-field-int-decode-design.md`

**Conventions:** use `poetry run python -m pytest` (NOT `poetry run pytest`); format with `poetry run python -m black`. The pre-commit hook runs the full test suite, so commits take ~30s.

---

## File Structure

- **`interpreter/cobol/ir_encoders.py`** (modify) — remove the `float()` conversion in the `decimal_digits == 0` branch of the four integer-capable decode builders; correct their docstrings.
- **`tests/unit/test_ir_encoders.py`** (modify) — add a test class asserting integer fields decode to `int` and decimal fields still decode to `float`, across all four builders.
- **`interpreter/handlers/calls.py`** (modify) — add a precise `_looks_like_heap_address` predicate and use it to gate the bare-heap-address warning in `_unwrap_builtin_result`.
- **`tests/unit/test_unwrap_builtin_result.py`** (modify) — add tests: no warning for a plain numeric string, warning still fires for an address-shaped string.
- **`tests/integration/test_cobol_programs.py`** (modify) — add an integration test proving an 18-digit field survives a `MOVE` round-trip exactly (today it returns `1`).

---

## Task 1: Integer-capable decoders return `int`

The four decoders each end their `decimal_digits == 0` branch with a `CallFunction("float", …)`. Remove it so the integer accumulator flows through. The downstream sign math uses integer literals (`1`, `2`), so the result stays `int` for integer fields.

**Files:**
- Modify: `interpreter/cobol/ir_encoders.py` (lines ~347-355, ~629-635, ~972-978, ~1155-1161, plus docstrings at ~312, ~1120)
- Test: `tests/unit/test_ir_encoders.py`

- [ ] **Step 1: Write the failing test**

Add this class at the end of `tests/unit/test_ir_encoders.py` (it uses the module-level `_execute_ir` helper and the already-imported builders):

```python
class TestIntegerFieldsDecodeToInt:
    """Integer COBOL fields (decimal_digits == 0) must decode to Python int,
    not float — converting to float silently corrupts integers beyond 2^53
    (e.g. PIC 9(18)). Decimal fields (decimal_digits > 0) stay float."""

    def test_zoned_integer_returns_int(self):
        data = [0xF1, 0xF2, 0xF3, 0xF4, 0xF5]  # zoned 12345
        ir = build_decode_zoned_ir("z", total_digits=5, decimal_digits=0)
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 12345
        assert isinstance(result, int)

    def test_zoned_decimal_still_float(self):
        data = [0xF1, 0xF2, 0xF3, 0xF4, 0xF5]
        ir = build_decode_zoned_ir("z", total_digits=5, decimal_digits=2)
        result = _execute_ir(ir, {"%p_data": data})
        assert isinstance(result, float)

    def test_zoned_separate_integer_returns_int(self):
        data = [0xF1, 0xF2, 0xF3, 0x4E]  # 123 with trailing '+'
        ir = build_decode_zoned_separate_ir(
            "zs", total_digits=3, decimal_digits=0, sign_leading=False
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 123
        assert isinstance(result, int)

    def test_comp3_integer_returns_int(self):
        data = [0x12, 0x34, 0x5F]  # packed 12345, positive
        ir = build_decode_comp3_ir("c3", total_digits=5, decimal_digits=0)
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 12345
        assert isinstance(result, int)

    def test_binary_integer_returns_int(self):
        data = list((1234).to_bytes(2, "big", signed=False))
        ir = build_decode_binary_ir(
            "bin", byte_count=2, decimal_digits=0, signed=False
        )
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 1234
        assert isinstance(result, int)

    def test_large_zoned_integer_exact(self):
        """18-digit value must be exact — the failure mode that motivated this."""
        data = [0xF0 | int(ch) for ch in "123456789012345678"]
        ir = build_decode_zoned_ir("z18", total_digits=18, decimal_digits=0)
        result = _execute_ir(ir, {"%p_data": data})
        assert result == 123456789012345678
        assert isinstance(result, int)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_ir_encoders.py::TestIntegerFieldsDecodeToInt -v`
Expected: the `isinstance(result, int)` assertions FAIL (result is currently `float`); `test_large_zoned_integer_exact` fails the exactness assertion too (float rounds it). The `*_decimal_still_float` test passes.

- [ ] **Step 3: Remove the float conversion in `build_decode_zoned_ir`**

In `interpreter/cobol/ir_encoders.py`, replace (around line 346-355):

```python
        accum = scaled
    else:
        # Convert to float for consistency
        as_float = rc.next()
        instructions.append(
            CallFunction(
                result_reg=as_float, func_name=FuncName("float"), args=(accum,)
            )
        )
        accum = as_float
```

with:

```python
        accum = scaled
    # Integer field (decimal_digits == 0): keep accum as int. Converting to
    # float silently corrupts integers beyond 2^53 (e.g. PIC 9(18)).
```

- [ ] **Step 4: Remove the float conversion in `build_decode_zoned_separate_ir`**

Replace (around line 627-635):

```python
        accum = scaled
    else:
        as_float = rc.next()
        instructions.append(
            CallFunction(
                result_reg=as_float, func_name=FuncName("float"), args=(accum,)
            )
        )
        accum = as_float
```

with:

```python
        accum = scaled
    # Integer field (decimal_digits == 0): keep accum as int (see build_decode_zoned_ir).
```

- [ ] **Step 5: Remove the float conversion in `build_decode_comp3_ir`**

Replace (around line 970-978):

```python
        accum = scaled
    else:
        as_float = rc.next()
        instructions.append(
            CallFunction(
                result_reg=as_float, func_name=FuncName("float"), args=(accum,)
            )
        )
        accum = as_float
```

with:

```python
        accum = scaled
    # Integer field (decimal_digits == 0): keep accum as int (see build_decode_zoned_ir).
```

- [ ] **Step 6: Remove the float conversion in `build_decode_binary_ir`**

Replace (around line 1153-1161):

```python
        int_val = scaled
    else:
        as_float = rc.next()
        instructions.append(
            CallFunction(
                result_reg=as_float, func_name=FuncName("float"), args=(int_val,)
            )
        )
        int_val = as_float
```

with:

```python
        int_val = scaled
    # Integer field (decimal_digits == 0): keep int_val as int (see build_decode_zoned_ir).
```

- [ ] **Step 7: Correct the docstrings**

In the same file, update the four decoder docstrings that say `Output: float`:
- `build_decode_zoned_ir` (~line 312), `build_decode_zoned_separate_ir`, `build_decode_comp3_ir`, `build_decode_binary_ir` (~line 1120).

Change each `Output: float` line to:

```
    Output: int when decimal_digits == 0, else float
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_ir_encoders.py::TestIntegerFieldsDecodeToInt -v`
Expected: PASS (all 6).

- [ ] **Step 9: Run the full encoders suite for regressions**

Run: `poetry run python -m pytest tests/unit/test_ir_encoders.py tests/unit/test_zoned_decimal.py tests/unit/test_redefines.py -q`
Expected: PASS. Existing decode tests assert `== 123.0` etc.; `123 == 123.0` is `True` in Python, so they remain green.

- [ ] **Step 10: Format and commit**

```bash
poetry run python -m black interpreter/cobol/ir_encoders.py tests/unit/test_ir_encoders.py
git add interpreter/cobol/ir_encoders.py tests/unit/test_ir_encoders.py
git commit -m "fix(cobol): integer fields decode to int, not float (red-dragon-4q25.42)"
```

---

## Task 2: Tighten the bare-heap-address warning

`_unwrap_builtin_result` warns when a builtin returns a "bare heap address". The check `_heap_addr(result.value)` is truthy for *any* non-empty string (because `_heap_addr` returns `Address(val)` for every string), so a plain `str()` result like `"7"` trips it. Gate the warning on a precise predicate instead.

**Files:**
- Modify: `interpreter/handlers/calls.py` (the `_unwrap_builtin_result` function, ~lines 65-75)
- Test: `tests/unit/test_unwrap_builtin_result.py`

- [ ] **Step 1: Write the failing test**

Add these methods inside the existing `TestUnwrapBuiltinResult` class in `tests/unit/test_unwrap_builtin_result.py` (add `import logging` at the top of the file):

```python
    def test_plain_numeric_string_does_not_warn(self, caplog):
        """A plain str() result like "7" is NOT a heap address — no warning."""
        with caplog.at_level(logging.WARNING):
            _unwrap_builtin_result(BuiltinResult(value="7"), "str")
        assert "bare heap address" not in caplog.text

    def test_address_shaped_string_still_warns(self, caplog):
        """An address-shaped string (obj_ prefix) still triggers the warning."""
        with caplog.at_level(logging.WARNING):
            _unwrap_builtin_result(BuiltinResult(value="obj_Point_1"), "make")
        assert "bare heap address" in caplog.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_unwrap_builtin_result.py -v`
Expected: `test_plain_numeric_string_does_not_warn` FAILS (it currently warns for `"7"`); `test_address_shaped_string_still_warns` passes.

- [ ] **Step 3: Add the predicate and gate the warning**

In `interpreter/handlers/calls.py`, replace the `_unwrap_builtin_result` function (lines ~65-75):

```python
def _unwrap_builtin_result(result: BuiltinResult, name: str) -> TypedValue:
    """Extract TypedValue from BuiltinResult, warning if heap address returned bare."""
    if isinstance(result.value, TypedValue):
        return result.value
    if isinstance(result.value, (Pointer, str)) and _heap_addr(result.value):
        logger.warning(
            "Builtin %s returned bare heap address %r, expected TypedValue",
            name,
            result.value,
        )
    return typed_from_runtime(result.value)
```

with:

```python
# Strings that genuinely name a heap/region address start with one of these.
# (See NEW_OBJECT/NEW_ARRAY/ALLOC_REGION and _handle_address_of's "mem_".)
_HEAP_ADDR_PREFIXES = (
    constants.OBJ_ADDR_PREFIX,
    constants.ARR_ADDR_PREFIX,
    constants.REGION_ADDR_PREFIX,
    "mem_",
)


def _looks_like_heap_address(value: object) -> bool:
    """True only for values that genuinely reference a heap address: a Pointer,
    or a string with a known address prefix. Plain strings (e.g. "7" from the
    str builtin) are NOT addresses, so they do not trip the bare-address warning.
    """
    if isinstance(value, Pointer):
        return True
    if isinstance(value, str):
        return value.startswith(_HEAP_ADDR_PREFIXES)
    return False


def _unwrap_builtin_result(result: BuiltinResult, name: str) -> TypedValue:
    """Extract TypedValue from BuiltinResult, warning if heap address returned bare."""
    if isinstance(result.value, TypedValue):
        return result.value
    if _looks_like_heap_address(result.value):
        logger.warning(
            "Builtin %s returned bare heap address %r, expected TypedValue",
            name,
            result.value,
        )
    return typed_from_runtime(result.value)
```

(`constants` is already imported in this file via `from interpreter import constants`; `Pointer` is already imported.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_unwrap_builtin_result.py -v`
Expected: PASS (all methods, including the two new ones).

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black interpreter/handlers/calls.py tests/unit/test_unwrap_builtin_result.py
git add interpreter/handlers/calls.py tests/unit/test_unwrap_builtin_result.py
git commit -m "fix(vm): only warn on genuinely address-shaped bare builtin results"
```

---

## Task 3: Integration regression — 18-digit `MOVE` is exact

Before the fix, `MOVE` of an 18-digit field decodes to float, stringifies to scientific notation (`"1.2345678901234568e+17"`), and `COBOL_PREPARE_DIGITS` can't parse it — the destination ends up `1`. This test proves the end-to-end fix.

**Files:**
- Test: `tests/integration/test_cobol_programs.py`

- [ ] **Step 1: Write the failing test**

Add this method to the `TestSectionedDataDivision` class in `tests/integration/test_cobol_programs.py` (it reuses the file's existing `_to_fixed`, `_decode_zoned_unsigned`, `_run_cobol`, and `_first_region` helpers, and the `_JAR_AVAILABLE` skip):

```python
    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_eighteen_digit_move_is_exact(self):
        """An 18-digit integer field survives MOVE exactly. Before integer
        fields decoded to int, MOVE went through float -> scientific-notation
        string -> COBOL_PREPARE_DIGITS, which could not parse it, leaving the
        destination = 1 instead of the original value (red-dragon-4q25.42)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. BIGT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 BIG PIC 9(18) VALUE 123456789012345678.",
                "77 OUT PIC 9(18) VALUE 0.",
                "PROCEDURE DIVISION.",
                "    MOVE BIG TO OUT.",
                "    STOP RUN.",
            ],
            max_steps=20000,
        )
        region = _first_region(vm)
        # Layout: BIG at offset 0 (18 bytes), OUT at offset 18 (18 bytes).
        assert _decode_zoned_unsigned(region, 0, 18) == 123456789012345678
        assert _decode_zoned_unsigned(region, 18, 18) == 123456789012345678
```

If `NotLanguageFeature` is not already imported in this file, add it: locate the existing `from tests.covers import covers` line and change it to `from tests.covers import covers, NotLanguageFeature`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run python -m pytest "tests/integration/test_cobol_programs.py::TestSectionedDataDivision::test_eighteen_digit_move_is_exact" -v`
Expected: FAIL — the `OUT` assertion sees `1` (or another corrupted value), not `123456789012345678`. (The `BIG` assertion passes — VALUE encoding from the literal string is already correct.)

- [ ] **Step 3: Verify the fix already makes it pass**

Task 1 fixed the decode path, so no new production code is needed here. Re-run:

Run: `poetry run python -m pytest "tests/integration/test_cobol_programs.py::TestSectionedDataDivision::test_eighteen_digit_move_is_exact" -v`
Expected: PASS.

If it still fails, STOP and investigate — it means `MOVE`'s decode path is not covered by the Task 1 change (the design assumed it is; a genuine failure here is a real gap to surface, not to paper over).

- [ ] **Step 4: Run the full COBOL suite for regressions**

Run: `poetry run python -m pytest tests/unit/cobol/ tests/integration/test_cobol_programs.py tests/integration/test_cobol_e2e_features.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_cobol_programs.py
git commit -m "test(cobol): 18-digit MOVE round-trips exactly (red-dragon-4q25.42)"
```

---

## Self-Review

**Spec coverage:**
- "Integer fields decode to int" → Task 1 (the four decoder edits + unit tests). ✓
- "Decimal fields stay float" → Task 1 `test_zoned_decimal_still_float` (over-reach guard). ✓
- "COMP-1/COMP-2 untouched" → not modified; `build_*_float_ir` are out of the edited set. ✓
- "Encode needs no changes (string path)" → no encode task; verified by the passing round-trip/regression suites in Task 1 Step 9 and Task 3 Step 4. ✓
- "Tighten the spurious warning" → Task 2. ✓
- "18-digit round-trip exact" (acceptance) → Task 3. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/vague steps. Every code step shows the exact before/after. The one conditional (Task 3 Step 3 "if it still fails, STOP") is a genuine TDD verification branch with a concrete action, not a placeholder.

**Type consistency:** `_looks_like_heap_address(value: object) -> bool` is defined and used once in Task 2. `_HEAP_ADDR_PREFIXES` is defined before use. Test helper names (`_execute_ir`, `_run_cobol`, `_first_region`, `_decode_zoned_unsigned`, `_to_fixed`, `_JAR_AVAILABLE`) match the existing definitions in their respective files. Builder signatures match `interpreter/cobol/ir_encoders.py`.

**Out of scope (unchanged):** decimal/money precision (red-dragon-4q25.1), `ROUNDED` mode (red-dragon-4q25.4/.30).
