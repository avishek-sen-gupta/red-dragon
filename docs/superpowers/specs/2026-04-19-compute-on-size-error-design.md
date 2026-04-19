# Design: COMPUTE ON SIZE ERROR (red-dragon-zdac)

## Context

COBOL's `COMPUTE` statement evaluates an arithmetic expression and writes the result to one or more target fields. Like ADD/SUBTRACT/MULTIPLY/DIVIDE, it supports `ON SIZE ERROR` and `NOT ON SIZE ERROR` clauses that fire when the computed result overflows a target field's capacity.

RedDragon implemented ON SIZE ERROR for the four arithmetic statements in red-dragon-4q25.5. COMPUTE was left as a separate issue because it evaluates an arbitrary expression tree rather than a single operator, but the overflow detection and branching pattern is identical.

Reference: `interpreter/cobol/lower_arithmetic.py` — `lower_arithmetic_giving` (the established pattern).

---

## Scope

- **In scope**: overflow detection on the final result register against each target field's type descriptor; `ON SIZE ERROR` / `NOT ON SIZE ERROR` clause execution; multiple-target all-or-nothing semantics.
- **Out of scope**: division within the COMPUTE expression (e.g. `COMPUTE X = A / B`) — div-by-zero within an expression tree is not addressed in this issue.

---

## Design

### Semantics

All-or-nothing: if any target field would overflow, **no** target is written and `ON SIZE ERROR` fires. This matches IBM COBOL semantics and is consistent with how `lower_arithmetic_giving` handles GIVING targets today.

Fast path: when neither clause is present, `lower_compute` behaves exactly as today — expression evaluation followed by direct `encode_and_write` for each target, with no overhead.

### Layer 1 — Java Bridge (`StatementSerializer.java`)

`serializeCompute` gains two optional keys, added after the existing `targets` serialization:

```java
if (stmt.getOnSizeErrorPhrase() != null) {
    map.put("on_size_error", serializeStatements(
        stmt.getOnSizeErrorPhrase().getStatements()));
}
if (stmt.getNotOnSizeErrorPhrase() != null) {
    map.put("not_on_size_error", serializeStatements(
        stmt.getNotOnSizeErrorPhrase().getStatements()));
}
```

JAR rebuild required after this change.

### Layer 2 — AST (`ComputeStatement`)

Two new fields added to the frozen dataclass, defaulting to empty list:

```python
on_size_error: list[CobolStatement] = field(default_factory=list)
not_on_size_error: list[CobolStatement] = field(default_factory=list)
```

`from_dict` deserializes them using `cobol_statement_from_dict`, matching the pattern in `IfStatement`. `to_dict` is unchanged.

### Layer 3 — Lowering (`lower_compute`)

**Fast path** (no clause): unchanged — expression + `encode_and_write` loop.

**Overflow path** (either clause non-empty):

1. Evaluate expression → `result_reg` (once, shared across all targets)
2. For each valid target: call `_compute_overflow_flag(ctx, result_reg, td)` → accumulate OR chain across all target overflow flags
3. Emit single `BranchIf` → `on_size_err_label` / `not_on_size_err_label`
4. `on_size_err` branch: lower `on_size_error` children; `Branch(end_label)`
5. `not_on_size_err` branch: `encode_and_write` all targets, lower `not_on_size_error` children; `Branch(end_label)`
6. `end_label`

The helpers `_compute_overflow_flag` and `emit_overflow_check` from the ON SIZE ERROR implementation are reused directly. No new IR primitives needed.

### Layer 4 — Integration Tests (`TestComputeOnSizeError`)

Four tests, one discrete scenario each, all decorated with `@covers(CobolFeature.ON_SIZE_ERROR)`:

| Test | Scenario |
|------|----------|
| `test_compute_overflow_fires_on_size_error` | Single target overflows → flag set, target bytes unchanged |
| `test_compute_no_overflow_fires_not_on_size_error` | Single target fits → not_on_size_error flag set |
| `test_compute_multi_target_any_overflow_skips_all` | Two targets, one overflows → both unchanged, on_size_error flag set |
| `test_compute_no_clause_overflow_silent` | Overflow with no clause → no exception |

---

## Verification

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestComputeOnSizeError -x -q
poetry run python -m pytest -x -q
poetry run python -m black .
```
