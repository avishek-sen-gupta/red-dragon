# Kotlin `when` Pattern Matching — Design Spec

**Date:** 2026-03-21
**Issue:** red-dragon-y0df (P2)
**Approach:** Pattern ADT mapping (same as Rust ADR-117, Scala ADR-118)

## Summary

Hook Kotlin's `when` expression into the common Pattern ADT via `compile_pattern_test`/`compile_pattern_bindings`, replacing hand-rolled `==` comparisons. Same architecture as Rust and Scala.

## Scope

### In Scope

| Pattern | Example | Pattern ADT Type |
|---------|---------|-----------------|
| Literal | `1`, `"hello"`, `true` | `LiteralPattern(value)` |
| Else (no condition) | `else ->` | `WildcardPattern()` — detected by absence of `when_condition` |
| `is Type` | `is Int`, `is String` | `ClassPattern(type_name, (), ())` — isinstance check |
| Capture (bare identifier) | `x ->` | `CapturePattern("x")` |

### Out of Scope (issues filed)

| Feature | Issue |
|---------|-------|
| Range patterns (`in 1..10`) | `red-dragon-1qcf` |
| Destructuring patterns | `red-dragon-bijo` |
| Smart casts after `is` | `red-dragon-tq0m` |

## Architecture

### New File: `interpreter/frontends/kotlin/patterns.py`

```python
def parse_kotlin_pattern(ctx, node) -> Pattern
```

Maps the inner content of a `when_condition` node to the Pattern ADT:

- `integer_literal`, `real_literal`, `long_literal`, `hex_literal` → `LiteralPattern`
- `string_literal` → `LiteralPattern`
- `boolean_literal` → `LiteralPattern`
- `simple_identifier` → `CapturePattern(name)`
- `check_expression` / `type_test` containing `is Type` → `ClassPattern(type_name, (), ())`. Verify exact tree-sitter structure during implementation.
- `null_literal` → `LiteralPattern(None)`

**Else handling:** Kotlin `else` is NOT a pattern node — it's a `when_entry` with no `when_condition` child. Detection happens in `lower_when_expr`, not in `parse_kotlin_pattern`.

### Refactored: `lower_when_expr` in `expressions.py`

Replace lines 358-416 (the entry loop). **Preserve** lines 308-357 (subject binding, block scope) unchanged.

Key differences from Rust/Scala:
- Subject binding (`when(val x = expr)`) and block scope must be preserved
- Kotlin uses `when_entry` (not `match_arm` or `case_clause`)
- Pattern is inside `when_condition` child of `when_entry`
- `else` is a `when_entry` with no `when_condition` — treat as irrefutable `WildcardPattern`
- Body is either in `control_structure_body` child or direct named children after `->`
- Body lowered via `_lower_control_body(ctx, body_node)` (existing function)

**Do NOT use `compile_match()`** — Kotlin `when` is expression-style.

Structure for each `when_entry`:
1. If no `when_condition` → irrefutable (WildcardPattern), branch unconditionally
2. Otherwise: extract inner pattern from `when_condition`, `parse_kotlin_pattern` → Pattern
3. `compile_pattern_test(ctx, subject_reg, pattern)` → `test_reg`
4. `BRANCH_IF`, bind, lower body, store result

### No Dead Code to Delete

Unlike Scala, Kotlin doesn't have separate pattern lowering functions in the dispatch table. The `when_condition` content is lowered via `ctx.lower_expr` inline. No dispatch entries to remove.

## Testing

### Unit Tests: `tests/unit/test_kotlin_patterns.py`

- Integer, real, string, boolean literals
- `is Type` → ClassPattern
- Simple identifier → CapturePattern

### Integration Tests: `tests/integration/test_kotlin_pattern_matching.py`

| Test | Program | Expected |
|------|---------|----------|
| Literal match | `when(x) { 1 -> 10; else -> 0 }` | Correct arm |
| Else fallthrough | `when(x) { 1 -> 10; else -> 0 }` with x=5 | else arm |
| `is Type` check | `when(x) { is Int -> 1; else -> 0 }` | xfail if isinstance not wired for primitives |

### Existing Tests

2 existing when tests in `test_kotlin_p0_gaps_execution.py` must continue passing.

## Dependencies

- No changes to common Pattern ADT
- No changes to VM
- Relies on existing `isinstance` builtin for `is Type` checks
