# Ruby `case/in` Pattern Matching — Design Spec

**Date:** 2026-03-21
**Issue:** red-dragon-6n0u (P1)
**Approach:** Pattern ADT mapping + unified match framework (ADR-117/118/119/120)

## Summary

Add Ruby 3.0+ `case/in` pattern matching via `parse_ruby_pattern` + `lower_match_as_expr` from the unified framework. Keep existing `case/when` (`lower_case`) unchanged.

## Scope

### In Scope

| Pattern | Example | Pattern ADT Type |
|---------|---------|-----------------|
| Literal | `1`, `"hello"`, `:sym` | `LiteralPattern(value)` |
| Wildcard | `_` or `else` | `WildcardPattern()` |
| Capture | `x` (bare identifier) | `CapturePattern("x")` |
| Alternative | `1 \| 2 \| 3` | `OrPattern(alternatives)` — `alternative_pattern` node |
| Array | `[a, b, c]` | `SequencePattern(elements)` — `array_pattern` node |
| Array with splat | `[a, *rest]` | `SequencePattern` with `StarPattern` |

### Out of Scope (issues filed)

| Feature | Issue |
|---------|-------|
| Hash patterns (`{x:, y:}`) | `red-dragon-kysi` |
| Find patterns (`[*, elem, *]`) | `red-dragon-swlt` |
| Pin patterns (`^variable`) | `red-dragon-ocvm` |
| Guard/if patterns | `red-dragon-3077` |

## Architecture

### New File: `interpreter/frontends/ruby/patterns.py`

```python
def parse_ruby_pattern(ctx, node) -> Pattern
```

Maps tree-sitter Ruby `case/in` pattern nodes to Pattern ADT:
- `integer` / `float` / `string` / `symbol` → `LiteralPattern`
- Wildcard `_` → `WildcardPattern()` — verify tree-sitter node type during implementation
- `identifier` → `CapturePattern(name)`
- `alternative_pattern` → `OrPattern` — may need flattening
- `array_pattern` → `SequencePattern` — parse element children recursively
- `splat_parameter` / `rest_assignment` inside array_pattern → `StarPattern`

### New: `lower_case_match` in `control_flow.py`

Uses `lower_match_as_expr` from `interpreter/frontends/common/match_expr.py` (ADR-120).

Ruby `case_match` node structure:
```
case_match
  <subject expression>
  in_clause
    <pattern>
    <body>
  in_clause
    ...
  else (optional)
    <body>
```

`MatchArmSpec` callbacks:
- `extract_arms`: collect `in_clause` children from `case_match`
- `pattern_of`: extract pattern from `in_clause`, call `parse_ruby_pattern`
- `guard_of`: return `None` (guards out of scope)
- `body_of`: lower body expression/statements from `in_clause`

**Else handling:** `else` clause in `case_match` is NOT an `in_clause` — it's a separate child. Handle by detecting the else clause and treating it as a `WildcardPattern` arm, or handling it after the framework loop.

### Dispatch Table Update

Add to `frontend.py`:
- Expression: `RubyNodeType.CASE_MATCH → lower_case_match_expr`
- Statement: `RubyNodeType.CASE_MATCH → lower_case_match_stmt` (delegates to expr, discards result)

Keep existing `RubyNodeType.CASE → lower_case` unchanged.

### Existing `case/when` Unchanged

`lower_case` (lines 168-244 in control_flow.py) stays as-is. It handles `case/when` which is a different tree-sitter node type (`case` vs `case_match`).

## Testing

Unit tests for `parse_ruby_pattern` + integration tests for `case/in` end-to-end. Add Ruby to the cross-language Rosetta pattern matching test.

## Dependencies

- `interpreter/frontends/common/match_expr.py` (ADR-120 framework)
- No changes to common Pattern ADT or VM
