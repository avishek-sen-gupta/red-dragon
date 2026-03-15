# Lua Table-Based OOP Method Dispatch

> **Issue:** red-dragon-wxg — Lua method chaining with table-based OOP returns symbolic

## Problem

Lua has no classes. OOP is done via tables with function-valued fields:

```lua
Counter = {}

function Counter.new()
    local self = {count = 0}
    return self
end

function Counter.increment(self)
    self.count = self.count + 1
    return self
end

counter = Counter.new()
result = Counter.increment(counter)
```

Currently, the Lua frontend emits:
- `DECL_VAR "Counter.new" %func_reg` — stores the method as a **top-level variable** with a dotted name
- `CALL_METHOD %Counter "new"` — tries to dispatch via the class method registry

This fails because:
1. The methods are top-level variables, not fields on the heap object (so the table's fields dict is empty)
2. `CALL_METHOD` looks up `registry.class_methods["table"]` which is empty (no `CLASS_LABEL` blocks for tables)
3. Falls through to `call_resolver.resolve_method()` → symbolic

## Decision

Fix entirely in the Lua frontend. No VM changes.

### Change 1: Dotted function declarations emit STORE_FIELD

In `lower_lua_function_declaration`, when `name_node` is a `dot_index_expression` (tree-sitter AST for `Counter.new`):

- Extract table name (`Counter`) and method name (`new`) from the two identifier children of the `dot_index_expression`
- Use the method name (`new`) — not the dotted string `Counter.new` — as the function name for the label and func ref. This produces `<function:new@func_new_0>`, matching `FUNC_REF_PATTERN` without changes.
- Emit the function body and label as usual
- Replace `DECL_VAR "Counter.new" %func_reg` with:
  - `LOAD_VAR "Counter"` → `%obj_reg`
  - `STORE_FIELD %obj_reg "new" %func_reg`

This correctly models Lua semantics: `function Counter.new()` is sugar for `Counter.new = function()`, which is `Counter["new"] = function()`.

**Precondition:** The table variable (`Counter`) must be initialized before dotted function declarations. This matches Lua's runtime semantics — `function Counter.new()` without a preceding `Counter = {}` would also fail at runtime in Lua.

### Change 2: Dotted function calls emit LOAD_FIELD + CALL_UNKNOWN

In the Lua expression lowerer, when a `function_call` has a `dot_index_expression` as its function name (e.g., `Counter.increment(counter)`):

- Instead of `CALL_METHOD %obj "method" args...`, emit:
  - `LOAD_VAR "Counter"` → `%obj`
  - `LOAD_FIELD %obj "increment"` → `%func`
  - `CALL_UNKNOWN %func args...`

Uses `CALL_UNKNOWN` (not `CALL_FUNCTION`) because the function reference is in a register. `CALL_FUNCTION` treats its first operand as a literal variable name; `CALL_UNKNOWN` resolves it as a register value via `_resolve_binop_operand` and then dispatches via `_try_user_function_call`. This is the established pattern — the Lua frontend already uses `CALL_UNKNOWN` for all dynamic call targets.

This correctly models Lua semantics: `Counter.increment(counter)` is field access (`Counter["increment"]`) followed by a function call. The dot syntax in Lua is NOT method dispatch — only `:` syntax implies implicit self.

## Rationale

- **Frontend-only**: No VM complexity added
- **Semantically correct**: Lua's dot syntax IS field access + function call, not method dispatch
- **Prepares for colon syntax**: When `:` support is added later, it will correctly use `CALL_METHOD` with implicit self, while `.` uses `LOAD_FIELD` + `CALL_UNKNOWN` with explicit self — mirroring how Lua actually works
- **YAGNI**: A VM-level field-function fallback in `CALL_METHOD` was considered but rejected. Lua is the only supported language where table-based OOP is the primary mechanism. Other languages (JS, Python) have real class systems already handled by the registry.

## Scope

- **In scope:** Dot syntax for function declarations and calls on tables
- **Out of scope:** Colon syntax (`:`) with implicit self — separate issue to be filed

## Testing

- Unit tests: verify IR shape (STORE_FIELD for declarations, LOAD_FIELD + CALL_UNKNOWN for calls)
- Integration tests: Rosetta method chaining program produces `answer = 6`
- Regression: all existing Lua tests continue to pass

## Files

- `interpreter/frontends/lua/declarations.py` — dotted function declaration → STORE_FIELD
- `interpreter/frontends/lua/expressions.py` — dotted function call → LOAD_FIELD + CALL_UNKNOWN
- `tests/unit/test_lua_frontend.py` — IR shape tests
- `tests/integration/` — execution test for method chaining
