# C# Structural Pattern Matching — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** C# switch expression/statement pattern matching via common Pattern ADT
**Issue:** red-dragon-u0gv

## Problem

C# switch expressions and statements support `declaration_pattern` (`case int i:`), `constant_pattern` (`null`), `recursive_pattern` (`Circle { Radius: 0 }`), and `discard` (`_`). The current lowering treats all patterns as expressions and compares with `BINOP ==`, which doesn't handle type checking or property matching.

## Approach

Add `parse_csharp_pattern` that maps C# tree-sitter pattern nodes to the existing Pattern ADT. Refactor `lower_switch_expr` and `lower_switch` to use `compile_pattern_test`/`compile_pattern_bindings`. Enhance `isinstance` builtin to handle primitive types (int, string, float, bool) in addition to heap objects.

## Design

### 1. Pattern Mapping

| C# tree-sitter node | Pattern ADT |
|---|---|
| `constant_pattern` (`null`, `0`, `"hello"`) | `LiteralPattern(value)` |
| `discard` (`_`) | `WildcardPattern()` |
| `declaration_pattern` with explicit type (`int i`) | `AsPattern(ClassPattern("int"), "i")` |
| `declaration_pattern` with `implicit_type` (`var x`) | `CapturePattern("x")` |
| `recursive_pattern` (`Circle { Radius: 0 }`) | `ClassPattern("Circle", keyword=(("Radius", LiteralPattern(0)),))` |
| `recursive_pattern` with capture (`Circle { Radius: var r }`) | `ClassPattern("Circle", keyword=(("Radius", CapturePattern("r")),))` |

### 2. `isinstance` Builtin Enhancement

Add primitive type map so `isinstance(42, "int")` returns `True`:

```python
_PRIMITIVE_TYPE_MAP = {
    "int": int, "Int": int, "Integer": int,
    "string": str, "String": str,
    "float": float, "Float": float, "Double": float,
    "bool": bool, "Boolean": bool,
}
```

When subject is not a heap object, check `isinstance(value, _PRIMITIVE_TYPE_MAP.get(class_name))`. Falls through to heap `type_hint` check for class instances.

### 3. Refactored `lower_switch_expr`

Keep the `result_var` + `DECL_VAR` + `LOAD_VAR` wrapper. Replace inner loop: parse each arm's pattern via `parse_csharp_pattern`, use `compile_pattern_test`/`compile_pattern_bindings` for matching, `lower_expr(value_node)` + `DECL_VAR result_var` for the arm body.

### 4. Refactored `lower_switch` (statement form)

Same pattern parsing. Replace the `constant_pattern`-only lookup with `parse_csharp_pattern` on whatever pattern node the section contains. Body remains a list of statements lowered via `lower_stmt`.

### 5. Files Changed

**Created:**
- `interpreter/frontends/csharp/patterns.py` — `parse_csharp_pattern`

**Modified:**
- `interpreter/builtins.py` — enhance `isinstance` for primitives
- `interpreter/frontends/csharp/control_flow.py` — refactor `lower_switch_expr` and `lower_switch`
- `interpreter/frontends/csharp/node_types.py` — add `RECURSIVE_PATTERN`, `PROPERTY_PATTERN_CLAUSE`, `SUBPATTERN`

## Testing

**Integration tests:**
- `test_switch_expr_declaration_pattern` — `int i => "integer"` type check + binding
- `test_switch_expr_constant_null` — `null => "null"` literal match
- `test_switch_expr_discard` — `_ => "other"` wildcard
- `test_switch_expr_recursive_pattern` — `Circle { Radius: 0 } => "point"` property match
- `test_switch_expr_recursive_capture` — `Circle { Radius: var r } => r` property capture
- `test_switch_expr_var_pattern` — `var x => x` catch-all with binding
- `test_switch_stmt_declaration_pattern` — statement form with `case int i:`
- `test_isinstance_primitive_int` — verify `isinstance` works on native int
