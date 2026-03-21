# Scala Structural Pattern Matching — Design Spec

**Date:** 2026-03-21
**Issue:** red-dragon-hgfq (P1)
**Approach:** Pattern ADT mapping (same as Rust ADR-117)

## Summary

Hook Scala's `match` into the common Pattern ADT via `compile_pattern_test`/`compile_pattern_bindings`, replacing the hand-rolled expression-based match lowering. Follows the identical architecture established for Rust (ADR-117) and C# switch expressions.

## Scope

### In Scope

| Pattern | Example | Pattern ADT Type |
|---------|---------|-----------------|
| Literal | `42`, `"hello"`, `true` | `LiteralPattern(value)` |
| Wildcard | `_` | `WildcardPattern()` |
| Capture | `x` | `CapturePattern("x")` |
| Alternative | `1 \| 2 \| 3` | `OrPattern(alternatives)` |
| Tuple | `(a, b)` | `SequencePattern(elements)` |
| Case class | `Circle(r)` | `ClassPattern("Circle", positional=(CapturePattern("r"),), keyword=())` |
| Typed | `i: Int` | `AsPattern(ClassPattern("Int", (), ()), "i")` — isinstance check + bind |
| Guard | `x if x > 0` | `guard_node` extracted from `case_clause` |
| Stable identifier | `Color.Red` | `ValuePattern(("Color", "Red"))` |
| Nested | `Some(Circle(r))` | Recursive composition |

### Out of Scope (issues filed)

| Feature | Issue |
|---------|-------|
| Infix patterns (`head :: tail`) | `red-dragon-hham` |
| As-patterns (`x @ Pattern`) | `red-dragon-4s1a` |
| Extractor patterns (custom unapply) | `red-dragon-loht` |

## Architecture

### New File: `interpreter/frontends/scala/patterns.py`

Single entry point:

```python
def parse_scala_pattern(ctx: LoweringContext, node: Node) -> Pattern
```

Maps tree-sitter Scala node types to the Pattern ADT:

- `wildcard` → `WildcardPattern()`. Scala uses a named node type `ScalaNodeType.WILDCARD`, unlike Rust's anonymous `_`.
- `integer_literal`, `floating_point_literal`, `string` / `string_literal`, `boolean_literal` → `LiteralPattern`. Note: Scala uses `floating_point_literal` (not `float_literal`) and `string` (not `string_literal`) for the primary string type.
- `identifier` → `CapturePattern(name)`. Identifiers in Scala patterns are variable captures.
- `alternative_pattern` → `OrPattern`. May need flattening like Rust's left-associative or-pattern tree.
- `tuple_pattern` → `SequencePattern`. Parse named children, filtering out `(`, `)`, `,`.
- `case_class_pattern` → `ClassPattern`. Type name from `type_identifier`, `identifier`, or `stable_type_identifier` child. Positional args from remaining named children.
- `typed_pattern` → `AsPattern(ClassPattern(type_name, (), ()), var_name)`. First named child is the variable identifier, type is extracted from the type child.
- `stable_type_identifier` (in pattern position) → `ValuePattern`. Split on `.` into tuple of parts. Example: `Color.Red`.

### Refactored: `lower_match_expr` in `expressions.py`

Current code (lines 191-246) replaced with the same `compile_pattern_test`/`compile_pattern_bindings` approach used in Rust.

**Do NOT use `compile_match()`** — it lowers bodies as statements via `lower_block`. Scala `match` is expression-style (returns a value). Use `compile_pattern_test`/`compile_pattern_bindings` directly, same as Rust's `_lower_match_arm`.

Key differences from Rust:
- Scala uses `case_clause` (not `match_arm`) with `child_by_field_name("pattern")` and `child_by_field_name("body")` fields
- Guard is a separate `guard` child node of `case_clause` — extract by iterating children: `next((c for c in clause.children if c.type == NT.GUARD), None)`. **NOT** via `child_by_field_name("guard")` — tree-sitter does not expose it as a field.
- Body is lowered via `_lower_body_as_expr()` (already exists in the file)
- Subject extracted via `node.child_by_field_name("value")` (same as existing code, line 192)

Structure:

1. Lower subject via `node.child_by_field_name("value")` → `subject_reg`
2. For each `case_clause`:
   a. Extract pattern via `clause.child_by_field_name("pattern")`
   b. Extract guard by iterating children for `NT.GUARD` type
   c. `parse_scala_pattern(ctx, pattern_node)` → `Pattern`
   d. `compile_pattern_test(ctx, subject_reg, pattern)` → `test_reg`
   e. Handle guard: pre-bind if `_needs_pre_guard_bindings(pattern)`, lower guard's condition child, AND with test
   f. Branch, bind, lower body via `_lower_body_as_expr`, store result via `DECL_VAR`
3. After all clauses: `LABEL end_label`, `LOAD_VAR` result variable

**Scala identifier convention:** In Scala, lowercase identifiers in patterns are variable captures, but uppercase identifiers (e.g., `Foo`) are stable identifiers (constants). For P1 scope, all identifiers are treated as captures. This is a known limitation — uppercase-as-constant would need symbol table lookup to distinguish. The existing typed pattern test (`case i: Int`) currently does NOT do a real type check (just falls through to expr dispatch); the Pattern ADT migration will make it a real `isinstance` check, which may cause the existing test to need adjustment if the VM lacks type info for the matched value.

**Stable identifier in patterns:** `Color.Red` in Scala pattern position needs verification of how tree-sitter parses it. It may appear as `stable_type_identifier` or as a `field_expression`. Verify during implementation with a diagnostic test and adjust mapping accordingly.

### Deleted Code

Delete these expression lowering functions (they were only used as fallback expression lowerers for patterns):
- `lower_wildcard` (line 331)
- `lower_case_class_pattern` (line 549)
- `lower_typed_pattern` (line 583)
- `lower_guard` (line 591)
- `lower_tuple_pattern_expr` (line 599)
- `lower_infix_pattern` (line 623) — **keep if still dispatched for non-match contexts**
- `lower_case_clause_expr` (line 700)
- `lower_alternative_pattern` (line 708)

Also remove corresponding entries from the `expr_dispatch` table in `frontend.py` (lines 94-104). Verify with grep first that nothing else calls them.

## Testing Strategy

### Unit Tests: `tests/unit/test_scala_patterns.py`

- `parse_scala_pattern` returns correct Pattern type for each node type
- Nested patterns, typed patterns, case class patterns
- Follow the same test helper pattern from `test_rust_patterns.py`

### Integration Tests: `tests/integration/test_scala_pattern_matching.py`

| Test | Program | Expected |
|------|---------|----------|
| Literal match | `x match { case 1 => 10; case _ => 0 }` | Correct arm |
| Capture binding | `x match { case n => n + 1 }` | `n` bound |
| Alternative | `x match { case 1 \| 2 => 10; case _ => 0 }` | Or works |
| Case class destructuring | `opt match { case Circle(r) => r; case _ => 0 }` | Field extracted |
| Typed pattern | `x match { case i: Int => i + 1; case _ => 0 }` | Type check + bind |
| Tuple | `pair match { case (a, b) => a + b }` | Elements extracted |
| Guard | `x match { case n if n > 0 => 1; case _ => -1 }` | Guard filters |

### Existing Tests

The 4 existing Scala match tests in `test_scala_frontend_execution.py` and `test_scala_p0_gaps_execution.py` must continue passing.

## Dependencies

- No changes to `interpreter/frontends/common/patterns.py`
- No changes to `interpreter/executor.py`
- No new opcodes or builtins
- Relies on existing case class emission for ClassPattern isinstance checks
