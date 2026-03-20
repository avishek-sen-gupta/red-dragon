# Value Patterns (Dotted Constants) — Design Spec

**Date:** 2026-03-20
**Status:** Approved
**Scope:** `case Color.RED:` value patterns via dotted name lookup
**Issue:** red-dragon-zuyo

## Problem

`case Color.RED:` is treated as `CapturePattern(name="Color.RED")`, which matches anything and binds the name. It should resolve `Color.RED` as a constant and compare with `==`.

In Python, a `dotted_name` with a `.` in a pattern is a value pattern (constant lookup), not a capture. Single-segment names are captures.

## Approach

Add `ValuePattern(parts: tuple[str, ...])` to the Pattern ADT. The compiler emits `LOAD_VAR` + `LOAD_FIELD` chain to resolve the constant, then `BINOP ==`. The parser distinguishes by checking if `dotted_name` contains multiple segments.

## Design

**New ADT variant:**
```python
@dataclass(frozen=True)
class ValuePattern(Pattern):
    """Match against a named constant via dotted lookup. Python's ``Color.RED``."""
    parts: tuple[str, ...]
```

**`compile_pattern_test`:** `LOAD_VAR parts[0]` → `LOAD_FIELD reg, parts[1]` → ... → `BINOP == subject, resolved`

**`compile_pattern_bindings`:** `case ValuePattern(): pass` — no bindings.

**`parse_pattern`:** When `dotted_name` has multiple `identifier` children (contains `.`), produce `ValuePattern(parts=("Color", "RED"))`. Single-segment stays `CapturePattern`.

### Files Changed

**Modified:**
- `interpreter/frontends/common/patterns.py` — add `ValuePattern`, handle in `compile_pattern_test` and `compile_pattern_bindings`
- `interpreter/frontends/python/patterns.py` — modify `dotted_name` handling in `parse_pattern`
- `tests/unit/test_pattern_compiler.py` — unit tests
- `tests/integration/test_python_pattern_matching.py` — integration tests + remove xfail

## Testing

**Unit:**
- `test_value_pattern_emits_load_var_and_load_field` — `ValuePattern(("Color", "RED"))` emits `LOAD_VAR Color` + `LOAD_FIELD RED` + `BINOP ==`
- `test_value_pattern_three_parts` — `ValuePattern(("a", "b", "c"))` emits `LOAD_VAR a` + `LOAD_FIELD b` + `LOAD_FIELD c`

**Integration:**
- `test_value_pattern_class_constant` — `case Color.RED:` with matching value → matches
- `test_value_pattern_rejects_mismatch` — non-matching value → falls to default
- `test_value_pattern_multi_level` — three-level dotted lookup
- `test_value_pattern_in_or` — `case Color.RED | Color.GREEN:`
- Remove xfail from existing `test_value_pattern_rejects_mismatch`
