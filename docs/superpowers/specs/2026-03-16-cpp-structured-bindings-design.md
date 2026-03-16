# C++ Structured Bindings (Declaration-Level) Design

**Issue:** red-dragon-cq8
**Date:** 2026-03-16
**Status:** Approved

## Goal

Support declaration-level C++17 structured bindings (`auto [a, b] = expr;`) by reusing the existing `_lower_structured_binding` helper from range-for support. Positional decomposition only (LOAD_INDEX).

## Background

Range-for structured bindings (`for (auto [a, b] : pairs)`) already work via `_lower_structured_binding()` in `cpp/control_flow.py`. Declaration-level structured bindings (`auto [a, b] = expr;`) use the same tree-sitter node type (`STRUCTURED_BINDING_DECLARATOR`) but appear as children of a `DECLARATION` node rather than a `FOR_RANGE_LOOP` node. `lower_cpp_declaration()` currently doesn't handle this child type.

## Design

Add an `elif child.type == CppNodeType.STRUCTURED_BINDING_DECLARATOR` branch in `lower_cpp_declaration()`. The declaration node structure:

```
declaration
  placeholder_type_specifier (auto)
  structured_binding_declarator ([a, b])
    identifier (a)
    identifier (b)
  =
  <initializer expression>
```

The new branch:
1. Finds the initializer (next named sibling after the binding declarator, skipping `=`)
2. Lowers it to get `rhs_reg`
3. Calls `_lower_structured_binding(ctx, child, rhs_reg)` — emits `CONST i` + `LOAD_INDEX rhs, i` + `DECL_VAR name` per binding variable

No VM changes. No new opcodes. No changes to type inference or dataflow.

## Scope

**In scope:**
- `auto [a, b] = expr;` positional decomposition via LOAD_INDEX
- Unit and integration tests

**Out of scope:**
- Struct member decomposition via LOAD_FIELD (filed as red-dragon-cjl)
- `const auto&` / `auto&&` qualifiers (ignored, same as range-for)
- Nested structured bindings

## Files to Modify

- `interpreter/frontends/cpp/declarations.py` — add `elif` branch (~8 lines)
- `tests/unit/test_for_loop_destructuring.py` — add `TestCppStructuredBindingDeclaration`
- `tests/integration/test_cpp_frontend_execution.py` — add integration test

## Testing

- Unit: `auto [a, b] = expr;` emits LOAD_INDEX + DECL_VAR per binding variable
- Integration: `auto [a, b] = make_pair(1, 2); int sum = a + b;` produces `sum == 3`
