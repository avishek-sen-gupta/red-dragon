# ROUNDED CLAUSE Implementation Design

## Goal

Implement `ROUNDED` modifier support for all COBOL arithmetic verbs (ADD, SUBTRACT, MULTIPLY, DIVIDE, COMPUTE), closing `CobolFeature.ROUNDED_CLAUSE` (red-dragon-4q25.4).

## Architecture

ROUNDED is per-target: each result field in a TO, FROM, INTO, BY, GIVING, or COMPUTE target can independently be rounded. The rounding step is injected just before the existing encode-and-write pipeline — the pipeline itself is unchanged.

**Rounding rule:** half-away-from-zero (`ROUND_HALF_UP` in Python's `decimal` module), matching the COBOL standard.

**Rounding location:** `_emit_arithmetic_writeback` emits a `__cobol_round(value_str, decimal_digits)` call when the target's `rounded` flag is true, replacing `result_str_reg` with the rounded result before passing it to `emit_encode_and_write`. The encode pipeline (`align_decimal`, `__cobol_prepare_digits`, IR encoders) is untouched.

## Tech Stack

Python (`decimal.ROUND_HALF_UP`), Java (ProLeap bridge `isRounded()` API), existing `byte_builtins.py` / `lower_arithmetic.py` patterns.

## Global Constraints

- `ROUND_HALF_UP` (not Python's default `ROUND_HALF_EVEN`) for all rounding.
- `decimal_digits` for a target field is `fl.type_descriptor.decimal_digits` (0 for integer PIC types — rounding still applies, e.g. `2.7 → 3`).
- `__cobol_round` must return `_UNCOMPUTABLE` if either argument is symbolic.
- TDD: write the failing integration test before any implementation.
- Bridge JAR rebuild required after Java changes: `mvn package -q -DskipTests` from `proleap-bridge/`.
- `test_all_builtins_registered` must include `"__cobol_round"`.

---

## Task 1: Data Structures

### Files

- Modify: `interpreter/cobol/ref_mod.py`
- Modify: `interpreter/cobol/cobol_statements.py`

### Changes

**`RefModOperand`** gains `rounded: bool = False`. `from_dict` reads `data.get("rounded", False)`. `to_dict` emits `"rounded": True` only when set (omit when False to keep JSON compact).

**`ComputeTarget`** — new frozen dataclass in `cobol_statements.py`:

```python
@dataclass(frozen=True)
class ComputeTarget:
    name: str
    rounded: bool = False

    @classmethod
    def from_dict(cls, data: dict | str) -> ComputeTarget:
        if isinstance(data, str):
            return cls(name=data)
        return cls(name=data["name"], rounded=data.get("rounded", False))

    def to_dict(self) -> dict:
        d: dict = {"name": self.name}
        if self.rounded:
            d["rounded"] = True
        return d
```

**`ComputeStatement.targets`** changes from `list[str]` to `list[ComputeTarget]`. `from_dict` parses each entry via `ComputeTarget.from_dict(entry)` (handles both plain string and dict). All existing callers that read `target` as a string must be updated to read `target.name`.

---

## Task 2: Bridge Serialization

### Files

- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`

### Changes

For each arithmetic verb serializer, add `"rounded"` to every target object:

**ADD** — in `serializeAdd`, for each `To` target:
```java
targetObj.addProperty("rounded", to.isRounded());
```

**SUBTRACT** — for each `From` target: `from.isRounded()`

**MULTIPLY** — for each `ByOperand` result target: `byOperand.isRounded()`

**DIVIDE** — for each `Into` / result `ByOperand` target: `.isRounded()`

**GIVING targets** (all verbs) — for each `Giving` entry: `giving.isRounded()`

**COMPUTE targets** — change from plain string array to object array:
```java
JsonObject t = new JsonObject();
t.addProperty("name", computeTarget.getName());
t.addProperty("rounded", computeTarget.isRounded());
targetsArray.add(t);
```

After editing, rebuild: `cd proleap-bridge && mvn package -q -DskipTests`.

---

## Task 3: `__cobol_round` Builtin

### Files

- Modify: `interpreter/cobol/cobol_constants.py`
- Modify: `interpreter/cobol/byte_builtins.py`
- Modify: `tests/unit/test_byte_builtins.py`

### Changes

**`cobol_constants.py`** — add to `BuiltinName`:
```python
COBOL_ROUND = "__cobol_round"
```

**`byte_builtins.py`** — add after the existing string builtins:
```python
def _builtin_cobol_round(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Round a numeric string to decimal_digits places, half-away-from-zero.
    Args: [value_str: str, decimal_digits: int]
    Returns: str — rounded value as string
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from decimal import Decimal, ROUND_HALF_UP
    value_str = str(args[0].value)
    decimal_digits = int(args[1].value)
    quantizer = Decimal(10) ** -decimal_digits
    d = Decimal(value_str).quantize(quantizer, rounding=ROUND_HALF_UP)
    return BuiltinResult(value=str(d))
```

Register in `BYTE_BUILTINS`:
```python
FuncName(BuiltinName.COBOL_ROUND): _builtin_cobol_round,
```

**`test_byte_builtins.py`** — add `"__cobol_round"` to the exhaustive list in `test_all_builtins_registered`, and add a unit test:
```python
def test_cobol_round_half_away_from_zero():
    assert _call("__cobol_round", ["1.235", 2]) == "1.24"
    assert _call("__cobol_round", ["1.234", 2]) == "1.23"
    assert _call("__cobol_round", ["-1.235", 2]) == "-1.24"
    assert _call("__cobol_round", ["2.7", 0]) == "3"
    assert _call("__cobol_round", ["2.3", 0]) == "2"
```

---

## Task 4: Lowering — Arithmetic Verbs

### Files

- Modify: `interpreter/cobol/lower_arithmetic.py`

### Changes

In `_emit_arithmetic_writeback`, after `result_str_reg` is established and before `emit_encode_and_write`, add:

```python
if target.rounded:
    dec_digits_reg = ctx.const_to_reg(fl.type_descriptor.decimal_digits)
    rounded_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(
        result_reg=rounded_reg,
        func_name=FuncName(BuiltinName.COBOL_ROUND),
        args=(result_str_reg, dec_digits_reg),
    ))
    result_str_reg = rounded_reg
```

`target` is already a `RefModOperand` in scope at this call site. This single block covers both TO and GIVING targets, since both flow through `_emit_arithmetic_writeback`.

---

## Task 5: Lowering — COMPUTE

### Files

- Modify: `interpreter/cobol/lower_compute.py` (or wherever COMPUTE targets are written)

### Changes

Wherever `ComputeStatement` iterates its targets to write back the computed value, update references from `target` (str) to `target.name`, and add the same rounding block as Task 4:

```python
for target in stmt.targets:
    fl, rr = materialised.resolve(target.name)
    value_reg = result_reg  # the computed expression result
    value_str_reg = ctx.emit_to_string(value_reg)
    if target.rounded:
        dec_digits_reg = ctx.const_to_reg(fl.type_descriptor.decimal_digits)
        rounded_reg = ctx.fresh_reg()
        ctx.emit_inst(CallFunction(
            result_reg=rounded_reg,
            func_name=FuncName(BuiltinName.COBOL_ROUND),
            args=(value_str_reg, dec_digits_reg),
        ))
        value_str_reg = rounded_reg
    ctx.emit_encode_and_write(rr, fl, value_str_reg, NO_REGISTER)
```

---

## Task 6: Integration Tests

### Files

- Modify: `tests/integration/test_cobol_programs.py`

### TDD Order: write failing test first, run to confirm failure, then implement.

**Test 1** — ADD ROUNDED on decimal field:
```python
@covers(CobolFeature.ROUNDED_CLAUSE)
def test_add_rounded_rounds_to_nearest():
    vm = _run_cobol([
        "IDENTIFICATION DIVISION.", "PROGRAM-ID. T.",
        "DATA DIVISION.", "WORKING-STORAGE SECTION.",
        "01 WS-X PIC 9(3)V9(2) VALUE 1.23.",
        "PROCEDURE DIVISION.", "MAIN.",
        "    ADD 0.007 TO WS-X ROUNDED.",
        "    STOP RUN.",
    ])
    # Without ROUNDED: 1.237 truncated → 1.23. With ROUNDED: → 1.24.
    region = _first_region(vm)
    assert _decode_zoned_with_decimal(region, 0, 3, 2) == Decimal("1.24")
```

**Test 2** — ADD without ROUNDED still truncates (regression guard):
```python
def test_add_without_rounded_truncates():
    vm = _run_cobol([...])  # same but no ROUNDED
    assert _decode_zoned_with_decimal(region, 0, 3, 2) == Decimal("1.23")
```

**Test 3** — COMPUTE ROUNDED on integer field:
```python
def test_compute_rounded_integer():
    vm = _run_cobol([
        ...,
        "01 WS-X PIC 9(3) VALUE 0.",
        "    COMPUTE WS-X ROUNDED = 10 / 6.",  # 1.666... → rounded → 2
    ])
    region = _first_region(vm)
    assert _decode_zoned_unsigned(region, 0, 3) == 2
```

A helper `_decode_zoned_with_decimal(region, offset, integer_digits, decimal_digits) -> Decimal` needs to be added to the test file or `cobol_helpers.py` — decodes EBCDIC zoned bytes and reconstructs a `Decimal` with the correct scale.
