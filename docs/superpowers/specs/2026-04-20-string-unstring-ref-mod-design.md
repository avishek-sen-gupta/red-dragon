# STRING/UNSTRING Reference Modification — Design Spec

## Goal

Extend COBOL reference modification (`WS-FIELD(start:length)` substring syntax) to STRING
sending operands and the UNSTRING source operand. MOVE already supports ref_mod; this brings
STRING and UNSTRING into alignment.

Closes: `red-dragon-4q25.36` (STRING sendings), `red-dragon-4q25.37` (UNSTRING source).

## Motivation

COBOL programs routinely use ref_mod on STRING and UNSTRING operands to work with fixed-layout
records (e.g. `STRING WS-RECORD(5:10) DELIMITED SIZE INTO WS-OUT`). Without this, any program
that slices a field before concatenating or splitting it will silently use the full field value.

## Prerequisites

Rename `MoveOperand` → `RefModOperand` in `interpreter/cobol/ref_mod.py` (separate commit
before this work). All existing MOVE usages in `cobol_statements.py` and `lower_arithmetic.py`
are updated in that commit.

## Architecture

Three coordinated layers, following the exact MOVE ref_mod pattern.

### Layer 1 — Java Bridge (`StatementSerializer.java`)

**STRING sendings (`serializeString`, line 855):**

Each sending value comes from `valueStmts.get(0)`, a `ValueStmt`. Two cases:

- `CallValueStmt`: cast to get the underlying `Call`, then call `serializeMoveOperand(call)`.
  This produces `{name, ref_mod_start?, ref_mod_length?}`.
- Any other `ValueStmt` (string/numeric literal): emit `{name: extractValueStmtText(vs)}`.
  Literals cannot carry ref_mod in standard COBOL.

`sendingObj.addProperty("value", ...)` becomes `sendingObj.add("value", ...)` in both cases,
so `value` is always a JSON object.

**UNSTRING source (`serializeUnstring`, line 887):**

`getSending().getSendingCall()` is already a `Call`. Replace:
```java
obj.addProperty("source", extractCallName(stmt.getSending().getSendingCall()));
```
with:
```java
obj.add("source", serializeMoveOperand(stmt.getSending().getSendingCall()));
```

`source` becomes a JSON object `{name, ref_mod_start?, ref_mod_length?}` instead of a string.

### Layer 2 — Python AST (`cobol_statements.py`)

**`StringSending`:**
- `value: str` → `value: RefModOperand`
- `from_dict`: `data.get("value", "")` → `RefModOperand.from_dict(data.get("value", {}))`
- `to_dict`: `"value": self.value` → `"value": self.value.to_dict()`

**`UnstringStatement`:**
- `source: str` → `source: RefModOperand`
- `from_dict`: `data.get("source", "")` → `RefModOperand.from_dict(data.get("source", {}))`
- `to_dict`: `"source": self.source` → `"source": self.source.to_dict()`

**Import change:** `from interpreter.cobol.ref_mod import MoveOperand` → `RefModOperand`.

### Layer 3 — Python Lowering (`lower_string_inspect.py`)

Add import: `from interpreter.cobol.lower_arithmetic import eval_ref_mod_expr`

**`lower_string()`:**

For each sending, after resolving the source field and producing `src_str_reg`:
```python
if sending.value.ref_mod_start is not None:
    # COBOL is 1-indexed; convert to 0-indexed before calling __string_slice
    raw_start_reg = eval_ref_mod_expr(ctx, sending.value.ref_mod_start, layout, region_reg)
    one_reg = ctx.const_to_reg(1)
    start_0indexed_reg = ctx.fresh_reg()
    ctx.emit_inst(Binop(
        result_reg=start_0indexed_reg,
        operator=resolve_binop("-"),
        left=Register(str(raw_start_reg)),
        right=Register(str(one_reg)),
    ))
    if sending.value.ref_mod_length is not None:
        length_reg = eval_ref_mod_expr(ctx, sending.value.ref_mod_length, layout, region_reg)
    else:
        # No length: rest of string. Use large sentinel constant (same pattern as MOVE).
        length_reg = ctx.const_to_reg(9999)
    sliced_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(
        result_reg=sliced_reg,
        func_name=FuncName(BuiltinName.STRING_SLICE),
        args=(Register(str(src_str_reg)), Register(str(start_0indexed_reg)), Register(str(length_reg))),
    ))
    src_str_reg = sliced_reg
```

The field resolution (has_field / const_to_reg) uses `sending.value.name` instead of the
former `sending.value` string. Literals land in the `else` branch via
`ctx.const_to_reg(str(sending.value.name))`.

**`lower_unstring()`:**

After resolving the source field and producing `src_str_reg`, apply the same ref_mod slice
pattern (including the 1→0 index conversion) using `stmt.source.ref_mod_start`/`ref_mod_length`.
Source field resolution uses `stmt.source.name` instead of `stmt.source`.

### JSON Schema

Breaking change coordinated between bridge and Python parser (no backward compat needed —
bridge output is always consumed by the Python parser in the same build).

| Field | Before | After |
|---|---|---|
| `StringSending.value` | `"WS-FIELD"` (string) | `{"name": "WS-FIELD"}` (object) |
| `UnstringStatement.source` | `"WS-FIELD"` (string) | `{"name": "WS-FIELD"}` (object) |

## Testing

Integration tests in `tests/integration/test_cobol_programs.py`.

**`TestStringRefMod`:**
- `test_string_field_ref_mod_basic` — `STRING WS_SRC(2:3) DELIMITED SIZE INTO WS_DST`,
  WS_SRC = "ABCDE" (PIC X(5)), WS_DST = PIC X(10). Assert WS_DST bytes start with "BCD".
- `test_string_multiple_sendings_one_has_ref_mod` — two sendings, only one has ref_mod; assert
  concat result is correct.
- `test_string_no_ref_mod_unchanged` — STRING without ref_mod produces same result as before.

**`TestUnstringRefMod`:**
- `test_unstring_source_ref_mod_basic` — `UNSTRING WS_SRC(3:7) DELIMITED SPACE INTO WS_A WS_B`,
  WS_SRC = "XXABC DE YY" (PIC X(11)); the substring "ABC DE" splits into "ABC" and "DE".
- `test_unstring_no_ref_mod_unchanged` — UNSTRING without ref_mod produces same result as before.

## Unit Test Migration

Any existing unit tests that directly construct `StringSending(value="WS-FIELD", ...)` or
`UnstringStatement(source="WS-FIELD", ...)` must be updated to use
`StringSending(value=RefModOperand(name="WS-FIELD"), ...)` and
`UnstringStatement(source=RefModOperand(name="WS-FIELD"), ...)`. Tests that go through
`from_dict()` will pass unchanged because `from_dict` handles the new JSON object schema.

## Out of Scope

- UNSTRING INTO target ref_mod (write-back via `__string_splice`) — tracked in `red-dragon-4q25.41`
- STRING INTO target ref_mod — `red-dragon-4q25.36` acceptance criteria does not include this;
  file a separate issue if needed
- Arithmetic, INSPECT, DISPLAY ref_mod — separate issues `red-dragon-4q25.38–40`
