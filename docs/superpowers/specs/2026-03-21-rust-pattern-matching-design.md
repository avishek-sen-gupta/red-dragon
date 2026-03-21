# Rust Structural Pattern Matching — Design Spec

**Date:** 2026-03-21
**Issue:** red-dragon-r06p (P1)
**Approach:** A — Pattern ADT mapping, no new VM infrastructure

## Summary

Hook Rust's `match`, `if let`, and `while let` into the common Pattern ADT (`interpreter/frontends/common/patterns.py`) using `compile_pattern_test` and `compile_pattern_bindings`. This replaces the hand-rolled literal-only match lowering with full structural pattern matching.

## Scope

### In Scope

| Pattern | Example | Pattern ADT Type |
|---------|---------|-----------------|
| Literal | `1`, `"hello"`, `true` | `LiteralPattern(value)` |
| Wildcard | `_` | `WildcardPattern()` |
| Capture | `x` | `CapturePattern("x")` |
| Or-pattern | `1 \| 2 \| 3` | `OrPattern(alternatives)` |
| Tuple | `(x, y, _)` | `SequencePattern(elements)` |
| Tuple-struct (prelude) | `Some(x)` | `ClassPattern("Option", positional=(CapturePattern("x"),))` |
| Struct | `Point { x, y }` | `ClassPattern("Point", keyword=(("x", CapturePattern("x")), ...))` |
| Scoped identifier | `Color::Red` | `ValuePattern(("Color", "Red"))` |
| Guard | `n if n > 0` | `guard_node` on `MatchCase` |
| Nested | `Some((a, b))` | Recursive composition |

### Out of Scope (follow-up issues)

| Feature | Issue |
|---------|-------|
| Custom enum variant classes | `red-dragon-vwqd` |
| Enum symbol table extraction | `red-dragon-laz4` |
| Range patterns (`1..=5`) | `red-dragon-htbw` |
| `ref`/`mut`/`@` bindings | `red-dragon-jasm` |

## Architecture

### New File: `interpreter/frontends/rust/patterns.py`

Single entry point:

```python
def parse_rust_pattern(ctx: LoweringContext, node: Node) -> Pattern
```

Maps tree-sitter Rust node types to the Pattern ADT:

- `integer_literal`, `float_literal`, `string_literal`, `boolean_literal` → `LiteralPattern`
- `negative_literal` / `unary_expression` (minus + literal) → `LiteralPattern` (negate child value). Verify which node type tree-sitter uses in pattern position.
- Anonymous `_` node (text `"_"`) → `WildcardPattern`. Note: tree-sitter Rust emits `_` as an **anonymous** (non-named) node, not as an `identifier`. Detection: check `node.type == "_"` or `ctx.node_text(node) == "_"` on leaf nodes.
- `identifier` → `CapturePattern(name)`
- `or_pattern` → `OrPattern` (recursive parse of named children)
- `tuple_pattern` → `SequencePattern` (recursive parse of elements)
- `tuple_struct_pattern` → `ClassPattern` with positional args. Constructor name extracted from `identifier` child (NOT `type_identifier`).
- `struct_pattern` → `ClassPattern` with keyword args. Type name from `type_identifier` child. Fields extracted from `field_pattern` children:
  - **Shorthand** `Point { x, y }`: `field_pattern` contains `shorthand_field_identifier` — both the field name and capture variable.
  - **Explicit** `Point { x: val }`: `field_pattern` contains `field_identifier` (name) + pattern child (value).
- `scoped_identifier` → `ValuePattern(parts)`. Split on `::` into tuple of strings.

**Prelude variant resolution:** A lookup table maps prelude variant names to their class names:

```python
VARIANT_TO_CLASS = {"Some": "Option", "Ok": "Result", "Err": "Result"}
```

When `parse_rust_pattern` encounters a `tuple_struct_pattern` with name `Some`, it resolves to `ClassPattern("Option", ...)`. Custom enum variants fall through unchanged — they'll work once `red-dragon-vwqd` adds variant classes.

### Refactored: `lower_match_expr` in `expressions.py`

**Key design decision:** Rust `match` is an expression (returns a value), but `compile_match` only supports statement-style (calls `ctx.lower_block` for bodies). Following the C# switch expression pattern (`lower_switch_expr` in `csharp/control_flow.py`), we use the lower-level `compile_pattern_test` and `compile_pattern_bindings` directly instead of `compile_match`.

Current code (lines 336-397) replaced with:

1. Lower subject expression → `subject_reg`
2. Allocate result variable `__match_result_N` via `DECL_VAR`
3. For each `match_arm`:
   a. Extract `match_pattern` child
   b. From `match_pattern`, extract the pattern (first named child) and guard (second named child after anonymous `if` token, if present). **Note:** the guard lives **inside** `match_pattern`, not as a sibling in `match_arm`.
   c. `parse_rust_pattern(ctx, pattern_node)` → `Pattern`
   d. `compile_pattern_test(ctx, subject_reg, pattern)` → `test_reg`
   e. If guard present: emit guard expression → `guard_reg`, AND with `test_reg`
   f. `BRANCH_IF test_reg, arm_label, next_label`
   g. At `arm_label`: `compile_pattern_bindings(ctx, subject_reg, pattern)`, lower body expression → `body_reg`, `STORE_VAR __match_result_N, body_reg`, `BRANCH end_label`
   h. At `next_label`: continue to next arm
4. After all arms: `LABEL end_label`, `LOAD_VAR __match_result_N` → return register

For irrefutable patterns (wildcard, capture without guard): skip test, branch unconditionally.

**Deleted code:** `_lower_arm_condition()` and manual label/branch logic in `lower_match_expr`.

### New: `if let` and `while let` support

Both desugar using `compile_pattern_test` and `compile_pattern_bindings` from the common infrastructure:

**`if let Some(x) = expr { body } else { alt }`:**

Tree-sitter structure:
```
if_expression
  let_condition
    <pattern_node>     ← first named child (e.g. tuple_struct_pattern)
    <value_node>       ← value field or last named child
  block                ← body
  else_clause          ← alternative (optional)
```

1. From `let_condition`: extract pattern node and value node (verify `child_by_field_name("pattern")` / `child_by_field_name("value")` field names against tree-sitter grammar during implementation)
2. Lower value expression → `subject_reg`
3. `parse_rust_pattern(ctx, pattern_node)` → `pattern`
4. `compile_pattern_test(ctx, subject_reg, pattern)` → `test_reg`
5. `BRANCH_IF test_reg, then_label, else_label`
6. In then_label: `compile_pattern_bindings(ctx, subject_reg, pattern)`, lower body
7. In else_label: lower else block (if any)

**`while let Some(x) = expr { body }`:**
1. `LABEL loop_start`
2. Lower expr → `subject_reg`
3. `compile_pattern_test(ctx, subject_reg, pattern)` → `test_reg`
4. `BRANCH_IF test_reg, body_label, exit_label`
5. In body_label: `compile_pattern_bindings(...)`, lower body, `BRANCH loop_start`
6. `LABEL exit_label`

These live in `interpreter/frontends/rust/control_flow.py` as `lower_if_let` and `lower_while_let`, dispatched from the existing `if_expression` and `while_expression` handlers when they detect a `let_condition` child.

## Testing Strategy

### Unit Tests: `tests/unit/test_rust_patterns.py`

- `parse_rust_pattern` returns correct Pattern type for each tree-sitter node type
- Nested patterns: `Some(Some(x))`, `Some((a, b))`
- Edge cases: anonymous `_` node vs identifier, negative literals, scoped identifiers
- Struct pattern shorthand vs explicit field binding

### Integration Tests: `tests/integration/test_rust_pattern_matching.py`

| Test | Program | Expected |
|------|---------|----------|
| Literal match | `match x { 1 => 10, 2 => 20, _ => 0 }` | Correct arm selected |
| Capture binding | `match x { n => n + 1 }` | `n` bound to subject |
| Or-pattern | `match x { 1 \| 2 => "small", _ => "big" }` | Or short-circuits |
| Tuple destructuring | `match pair { (0, y) => y, (x, 0) => x, _ => -1 }` | Elements extracted |
| Some(x) destructuring | `match opt { Some(v) => v, _ => 0 }` | `v` bound to inner value |
| Struct destructuring | `match p { Point { x, y } => x + y }` | Fields extracted by name |
| Guard clause | `match x { n if n > 0 => "pos", _ => "non-pos" }` | Guard evaluated |
| if let Some | `if let Some(v) = opt { v } else { 0 }` | Destructure or fallback |
| while let Some | `while let Some(v) = stack.pop() { sum += v }` | Loop until None |
| Nested pattern | `match opt { Some((a, b)) => a + b, _ => 0 }` | Recursive destructure |
| Scoped identifier | `match c { Color::Red => 1, _ => 0 }` | ValuePattern lookup |

### Existing Tests

The 6 tests in `test_rust_or_pattern_execution.py` must continue passing — they exercise the literal or-pattern subset. Output values will be identical; IR structure may differ.

## Dependencies

- No changes to `interpreter/frontends/common/patterns.py` (Pattern ADT)
- No changes to `interpreter/executor.py` (VM)
- No new opcodes or builtins
- Relies on existing `Option`/`Box` prelude classes for `Some(x)` destructuring
- Relies on existing struct class emission for struct pattern destructuring

## Risks

1. **Tree-sitter node structure assumptions:** Pattern node types need verification against actual tree-sitter-rust grammar. Mitigated by writing unit tests that parse real Rust snippets. Key items to verify during implementation: anonymous `_` node handling, `negative_literal` vs `unary_expression` in pattern position, `let_condition` field names.
2. **Struct field pattern extraction:** `field_pattern` / `shorthand_field_identifier` / `field_identifier` node structure must be verified. Mitigated by unit tests with shorthand and explicit struct patterns.
3. **`while let` with method calls:** `stack.pop()` requires method call lowering in the condition position, which should already work but needs integration test verification.
