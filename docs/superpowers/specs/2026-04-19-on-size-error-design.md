# ON SIZE ERROR / Overflow Detection Design

**Issue:** red-dragon-4q25.5  
**Date:** 2026-04-19  
**Scope:** ADD, SUBTRACT, MULTIPLY, DIVIDE (ArithmeticStatement only)  
**Out of scope:** COMPUTE, ADD/SUBTRACT CORRESPONDING (separate issues filed)

---

## Problem

ON SIZE ERROR and arithmetic overflow detection are entirely absent. When a
computed result exceeds the target field's capacity, no error is raised and no
ON SIZE ERROR branch is taken. Division by zero propagates as a Python
exception. Overflow silently truncates.

---

## Design

### Principle

All overflow detection is pure IR — CONST, BINOP comparisons (GT, LT, EQ, OR),
and BRANCH_IF. No new Python builtins.

### Control Flow

When `on_size_error` or `not_on_size_error` is non-empty:

```
[decode operands]

# DIVIDE only: pre-Binop division-by-zero guard
CONST zero = 0
BINOP divzero_reg = (divisor_reg == zero)
BRANCH_IF divzero_reg → on_size_err_label, compute_label
Label(compute_label)

[emit Binop → result_reg]

# emit_overflow_check(ctx, result_reg, td, on_size_err_label, not_on_size_err_label)
CONST max_reg = 10^total_digits - 1
BINOP over_max = (result_reg > max_reg)
# signed fields additionally:
CONST min_reg = -(10^total_digits - 1)
BINOP under_min = (result_reg < min_reg)
BINOP overflow_reg = (over_max OR under_min)
# unsigned: overflow_reg = over_max
BRANCH_IF overflow_reg → on_size_err_label, not_on_size_err_label

Label(on_size_err_label)
  [lower on_size_error children]
Branch(end_label)

Label(not_on_size_err_label)
  [emit_encode_and_write]    ← result committed only on no-overflow
  [lower not_on_size_error children]
Branch(end_label)

Label(end_label)
```

When both `on_size_error` and `not_on_size_error` are **empty** (no clause):
skip overflow check entirely — emit Binop and encode_and_write directly as
today. No branches, no overhead.

### GIVING variant

For each GIVING field, overflow is checked independently against that field's
type descriptor. The overflow flags across all GIVING fields are OR'd — if any
target overflows, the on_size_err branch fires once.

### `emit_overflow_check` helper

New function in `lower_arithmetic.py`. Takes:
- `ctx: EmitContext`
- `result_reg: str`
- `td: CobolTypeDescriptor`
- `on_size_err_label: CodeLabel`
- `not_on_size_err_label: CodeLabel`

Emits CONST/BINOP/BRANCH_IF sequence. Uses `td.total_digits` and `td.signed`.
Called by both `lower_arithmetic` and `lower_arithmetic_giving`.

---

## Files Changed

| File | Change |
|------|--------|
| `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` | Extract and serialize `onSizeErrorPhrase()` / `notOnSizeErrorPhrase()` for ADD, SUBTRACT, MULTIPLY, DIVIDE as `"on_size_error"` / `"not_on_size_error"` JSON arrays |
| `interpreter/cobol/cobol_statements.py` | Add `on_size_error: list[CobolStatement]` and `not_on_size_error: list[CobolStatement]` to `ArithmeticStatement` (default empty lists) |
| `interpreter/cobol/lower_arithmetic.py` | Add `emit_overflow_check()` helper; restructure `lower_arithmetic` and `lower_arithmetic_giving` to branch on overflow when clause is present; add pre-Binop div-by-zero guard for DIVIDE |

---

## Acceptance Criteria

1. `ADD 999 TO WS-COUNTER` (PIC 9(3)) with ON SIZE ERROR branch → branch fires, field unchanged.
2. `DIVIDE 0 INTO X` with ON SIZE ERROR → branch fires.
3. Without ON SIZE ERROR, overflow does not raise a Python exception (silent truncation, current behavior preserved).
4. NOT ON SIZE ERROR branch executes when no overflow occurs.
5. Integration tests: ADD overflow, SUBTRACT underflow, MULTIPLY overflow, DIVIDE by zero — each with and without ON SIZE ERROR.
6. Signed fields (PIC S9(n)) check both upper and lower bounds.

---

## Testing

Run:
```
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestOnSizeError -x -q
poetry run python -m pytest tests/integration/ -x -q  # full regression
```

Integration tests go in `tests/integration/test_cobol_programs.py` in a new
`TestOnSizeError` class. Use byte-level assertions where appropriate
(e.g., assert field bytes unchanged when ON SIZE ERROR fires).
