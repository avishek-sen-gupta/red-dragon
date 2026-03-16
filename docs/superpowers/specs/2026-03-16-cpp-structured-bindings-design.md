# C++ Structured Bindings (Declaration-Level) Design

**Issue:** red-dragon-cq8
**Date:** 2026-03-16
**Status:** Approved

## Goal

Support declaration-level C++17 structured bindings (`auto [a, b] = expr;`) by reusing the existing `_lower_structured_binding` helper from range-for support. Positional decomposition only (LOAD_INDEX).

## Background

Range-for structured bindings (`for (auto [a, b] : pairs)`) already work via `_lower_structured_binding()` in `cpp/control_flow.py`. Declaration-level structured bindings (`auto [a, b] = expr;`) use the same tree-sitter node type (`STRUCTURED_BINDING_DECLARATOR`) but appear inside an `INIT_DECLARATOR` child of a `DECLARATION` node. The existing `_lower_init_declarator` in `c/declarations.py` doesn't handle this declarator type.

## Design

The tree-sitter parse of `auto [a, b] = expr;`:

```
declaration
  placeholder_type_specifier (auto)
  init_declarator
    structured_binding_declarator ([a, b])
      identifier (a)
      identifier (b)
    identifier (expr)           <- the "value" field
```

The `structured_binding_declarator` is inside an `init_declarator`, so the fix goes in `_lower_init_declarator` in `interpreter/frontends/c/declarations.py`. Early in that function, check if `decl_node.type == CppNodeType.STRUCTURED_BINDING_DECLARATOR`. If so:

1. Lower the `value_node` (RHS expression) to get `rhs_reg`
2. Call `_lower_structured_binding(ctx, decl_node, rhs_reg)` — emits `CONST i` + `LOAD_INDEX rhs, i` + `DECL_VAR name` per binding variable
3. Return early (skip the normal init_declarator logic)

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

- `interpreter/frontends/c/declarations.py` — add early return in `_lower_init_declarator` for `STRUCTURED_BINDING_DECLARATOR`
- `tests/unit/test_for_loop_destructuring.py` — add `TestCppStructuredBindingDeclaration`
- `tests/integration/test_cpp_frontend_execution.py` — add integration test

## Testing

- Unit: `auto [a, b] = expr;` emits LOAD_INDEX + DECL_VAR per binding variable
- Integration: `auto [a, b] = make_pair(1, 2); int sum = a + b;` produces `sum == 3`
