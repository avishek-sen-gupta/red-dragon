# Lua Frontend

> `interpreter/frontends/lua/` -- Extends `BaseFrontend` -- per-language directory architecture

## Overview

The Lua frontend lowers tree-sitter Lua ASTs into the RedDragon flattened TAC IR. It handles Lua-specific constructs including table constructors (Lua's unified data structure for arrays, dictionaries, and objects), the `repeat ... until` loop (do-while), numeric `for` loops (`for i = start, end, step`), generic `for` loops (`for k, v in pairs(t)`), multiple assignment (`a, b = expr1, expr2`), `local` variable declarations, `goto`/label statements, dot-index expressions (`obj.field`), bracket-index expressions (`obj[key]`), method calls (`obj:method()`), anonymous function expressions, and the vararg expression (`...`).

Lua's tree-sitter grammar uses distinct node types for dot-index (`dot_index_expression`) and bracket-index (`bracket_index_expression`) access, rather than a single attribute/subscript node.

## Directory Structure

```
interpreter/frontends/lua/
  frontend.py         -- LuaFrontend class (thin orchestrator)
  node_types.py       -- LuaNodeType constants class
  expressions.py      -- Lua-specific expression lowerers (pure functions)
  control_flow.py     -- Lua-specific control flow lowerers (pure functions)
  declarations.py     -- Lua-specific declaration/assignment lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend (_base.py)
        +-- LuaFrontend (lua/frontend.py)
```

`LuaFrontend` is a thin orchestrator that builds dispatch tables from pure functions. All lowering logic lives in the `expressions`, `control_flow`, and `declarations` modules as pure functions taking `(ctx: TreeSitterEmitContext, node)`. No other frontend extends `LuaFrontend`.

## Grammar Constants (`_build_constants()`)

| Field | Value | Notes |
|---|---|---|
| `attr_object_field` | `"table"` | Lua names the LHS `table` |
| `attr_attribute_field` | `"field"` | Lua names the RHS `field` |
| `comment_types` | `frozenset({LuaNodeType.COMMENT})` | Same as default |
| `noise_types` | `frozenset({LuaNodeType.HASH_BANG_LINE, LuaNodeType.NEWLINE})` | Skips Lua shebang lines |
| `block_node_types` | `frozenset({LuaNodeType.BLOCK, LuaNodeType.CHUNK})` | Lua has explicit `block` and `chunk` nodes |
| `paren_expr_type` | `LuaNodeType.PARENTHESIZED_EXPRESSION` | Same as default |

Note: All literal constants (`none_literal`, `true_literal`, `false_literal`, `default_return_value`) retain their `GrammarConstants` defaults.

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `"identifier"` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `"number"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"string"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"true"` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `"false"` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `"nil"` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `"binary_expression"` | `common_expr.lower_binop` | `BINOP` |
| `"unary_expression"` | `common_expr.lower_unop` | `UNOP` |
| `"parenthesized_expression"` | `common_expr.lower_paren` | (unwraps inner expression) |
| `"function_call"` | `lua_expr.lower_lua_call` | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `"dot_index_expression"` | `lua_expr.lower_dot_index` | `LOAD_FIELD` |
| `"bracket_index_expression"` | `lua_expr.lower_bracket_index` | `LOAD_INDEX` |
| `"table_constructor"` | `lua_expr.lower_table_constructor` | `NEW_OBJECT("table")` + `STORE_INDEX` |
| `"expression_list"` | `lua_expr.lower_expression_list` | (unwraps to first named child) |
| `"function_definition"` | `lua_expr.lower_lua_function_definition` | `BRANCH` + `LABEL` + params + body + `RETURN` + `CONST func:ref` |
| `"vararg_expression"` | `lua_expr.lower_lua_vararg` | `SYMBOLIC("varargs")` |
| `"string_content"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"escape_sequence"` | `common_expr.lower_const_literal` | `CONST` (raw text) |

**18 entries total.**

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `"variable_declaration"` | `lua_decl.lower_lua_variable_declaration` | `CONST "None"` + `STORE_VAR` or delegates to assignment |
| `"assignment_statement"` | `lua_decl.lower_lua_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` per target |
| `"function_declaration"` | `lua_decl.lower_lua_function_declaration` | `BRANCH` + `LABEL` + params + body + `RETURN` + `STORE_VAR` |
| `"if_statement"` | `lua_cf.lower_lua_if` | `BRANCH_IF` + `LABEL` + `BRANCH` + elseif chain |
| `"while_statement"` | `lua_cf.lower_lua_while` | Loop with `BRANCH_IF` |
| `"for_statement"` | `lua_cf.lower_lua_for` | Dispatches to numeric or generic for |
| `"repeat_statement"` | `lua_cf.lower_lua_repeat` | Do-while with `UNOP("not")` + `BRANCH_IF` |
| `"return_statement"` | `lua_decl.lower_lua_return` | `RETURN` |
| `"do_statement"` | `lua_cf.lower_lua_do` | Plain block (scoping) |
| `"expression_statement"` | `common_assign.lower_expression_statement` | (unwraps inner expression) |
| `"break_statement"` | `common_cf.lower_break` | `BRANCH` to break target |
| `"goto_statement"` | `lua_cf.lower_lua_goto` | `BRANCH(label_name)` |
| `"label_statement"` | `lua_cf.lower_lua_label` | `LABEL(label_name)` |

**13 entries total.** Note: `chunk` and `block` are handled via `block_node_types` in `GrammarConstants`, not via the statement dispatch table.

## Language-Specific Lowering Methods

### `lua_decl.lower_lua_variable_declaration(ctx, node)`
Lowers `local x = expr`. Lua's `variable_declaration` wraps an `assignment_statement` child. If found, delegates to `lua_decl.lower_lua_assignment`. Otherwise, handles bare `local x` by emitting `CONST "None"` + `STORE_VAR` for each `identifier` child.

### `lua_decl.lower_lua_assignment(ctx, node)`
Lowers `a, b = expr1, expr2` (Lua's multi-assignment). Finds `variable_list` and `expression_list` children by node type (not field name). Lowers all RHS expressions first, then assigns each to the corresponding LHS target. If more targets than values, extra targets get `CONST "None"`. Falls back to positional named children if the expected node types are missing.

### `lua_decl.lower_lua_store_target(ctx, target, val_reg, parent_node)`
Handles Lua-specific target types for store operations:
- `"identifier"` -> `STORE_VAR`
- `"dot_index_expression"` -> `STORE_FIELD` (using `table`/`field` child fields)
- `"bracket_index_expression"` -> `STORE_INDEX` (using `table`/`field` child fields)
- Fallback -> `STORE_VAR` with raw text

### `lua_decl.lower_lua_function_declaration(ctx, node)`
Lowers `function name(params) ... end`. Standard function lowering: `BRANCH` past body, `LABEL`, params via `common_decl.lower_params`, body, implicit `RETURN "None"`, end label, `CONST func:ref`, `STORE_VAR`. Uses `"__anon"` if no name node exists.

### `lua_expr.lower_lua_call(ctx, node) -> str`
Lowers `function_call`. Uses Lua's `name` field (not `function`). Five paths:
1. **No name node**: emits `SYMBOLIC("unknown_call_target")` + `CALL_UNKNOWN`.
2. **Method call** (`name` is `method_index_expression`): extracts `table` and `method` children, emits `CALL_METHOD`. This handles `obj:method(args)` syntax.
3. **Dot-indexed call** (`name` is `dot_index_expression`): extracts `table` and `field` children, emits `CALL_METHOD`. This handles `obj.method(args)` syntax.
4. **Plain function call** (`name` is `identifier`): emits `CALL_FUNCTION`.
5. **Dynamic call**: any other `name` type, lowers name as expression, emits `CALL_UNKNOWN`.

### `lua_expr.lower_dot_index(ctx, node) -> str`
Lowers `obj.field` (Lua `dot_index_expression`) as `LOAD_FIELD`. Uses `table` and `field` child fields.

### `lua_expr.lower_bracket_index(ctx, node) -> str`
Lowers `obj[key]` (Lua `bracket_index_expression`) as `LOAD_INDEX`. Uses `table` and `field` child fields (note: the key is accessed via the `field` field name in tree-sitter Lua grammar).

### `lua_expr.lower_table_constructor(ctx, node) -> str`
Lowers `{key=val, val2, ...}` (Lua table constructors). Emits `NEW_OBJECT("table")`, then iterates `field` children:
- **Named field** (both `name` and `value`): emits `CONST(key_name)` + lowered value + `STORE_INDEX`.
- **Positional field** (only `value`): emits `CONST(positional_idx)` + lowered value + `STORE_INDEX`. Positional indices start at **1** (Lua convention).

### `lua_cf.lower_lua_if(ctx, node)`
Lowers `if cond then ... elseif ... else ... end`. Evaluates the condition, emits `BRANCH_IF`, lowers the consequence body. Collects all `elseif_statement` children and optional `else_statement` child, then delegates to the private `_lower_lua_elseif_chain` helper.

### `lua_cf.lower_lua_while(ctx, node)`
Lowers `while cond do ... end`. Standard while loop pattern: condition label, evaluate condition, `BRANCH_IF` to body or end, body with `push_loop`/`pop_loop`, back-edge branch.

### `lua_cf.lower_lua_for(ctx, node)`
Dispatches Lua's `for_statement` based on the clause child:
- `for_numeric_clause` -> `_lower_lua_for_numeric`
- `for_generic_clause` -> `_lower_lua_for_generic`

### `_lower_lua_for_numeric(ctx, clause, body_node, for_node)` (private)
Lowers `for i = start, end [, step] do ... end`. Emits:
1. Lowers start/end/step expressions. Step defaults to `CONST "1"`.
2. `STORE_VAR(var_name, start_reg)` to initialize.
3. Loop condition: `LOAD_VAR(var_name)`, `BINOP("<=", current, end)`, `BRANCH_IF`.
4. Body with `push_loop`/`pop_loop`.
5. Update: `LOAD_VAR(var_name)`, `BINOP("+", current, step)`, `STORE_VAR(var_name, next)`.
6. Back-edge `BRANCH`.

### `_lower_lua_for_generic(ctx, clause, body_node, for_node)` (private)
Lowers `for k, v in ipairs(t) do ... end` as index-based iteration. Extracts variable names from `variable_list`, lowers the iterable from `expression_list`, initializes idx to 0, computes `len(iter)` via `CALL_FUNCTION`, branches on `idx < len`, stores index to first variable and element (via `LOAD_INDEX`) to second variable, executes body, increments idx.

### `lua_cf.lower_lua_repeat(ctx, node)`
Lowers `repeat ... until cond` (do-while). Emits body label, executes body (with `push_loop`/`pop_loop`), evaluates condition, **negates** with `UNOP("not", cond)`, and branches: if negated is true (condition false), loops back; if negated is false (condition true), exits. This correctly implements "repeat until condition is true."

### `lua_decl.lower_lua_return(ctx, node)`
Lowers `return expr`. Filters out `"return"` tokens. Handles bare `return` by emitting `CONST "None"` + `RETURN`.

### `lua_expr.lower_expression_list(ctx, node) -> str`
Unwraps `expression_list` to its first named child. If empty, returns `CONST "None"`. Used when `expression_list` appears in expression context.

### `lua_cf.lower_lua_do(ctx, node)`
Lowers `do ... end` as a plain block (for scoping purposes). Tries the `body` field first; if absent, iterates named children excluding `do` and `end`.

### `lua_expr.lower_lua_function_definition(ctx, node) -> str`
Lowers anonymous function expressions (`function(params) ... end`). Generates a unique name via `ctx.fresh_label("anon_fn")`, emits function body between labels, and **returns** a register holding the `func:ref` constant. Unlike `lua_decl.lower_lua_function_declaration`, this does not emit a `STORE_VAR` (the result is an expression, not a declaration).

### `lua_expr.lower_lua_vararg(ctx, node) -> str`
Lowers the `...` vararg expression as `SYMBOLIC("varargs")`.

### `lua_cf.lower_lua_goto(ctx, node)`
Lowers `goto label` as `BRANCH(label_name)`. Extracts the label name from the first named child. Includes debug logging.

### `lua_cf.lower_lua_label(ctx, node)`
Lowers `::label::` (label statement) as `LABEL(label_name)`. Extracts the label name from the first named child. Includes debug logging.

## Canonical Literal Handling

| Lua Node Type | Canonical Method | Emitted IR |
|---|---|---|
| `"nil"` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `"true"` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `"false"` | `common_expr.lower_canonical_false` | `CONST "False"` |

Lua's `nil`, `true`, and `false` are mapped to the Python-canonical forms in the IR.

## Example

**Lua source:**
```lua
function factorial(n)
    if n <= 1 then
        return 1
    end
    return n * factorial(n - 1)
end

local result = factorial(5)
print(result)

local t = {x = 10, y = 20, "hello"}
for k, v in pairs(t) do
    print(k, v)
end
```

**Emitted IR (simplified):**
```
LABEL         ENTRY
BRANCH        end_factorial_0
LABEL         func_factorial_0
SYMBOLIC      %0  "param:n"
STORE_VAR     n  %0
LOAD_VAR      %1  n
CONST         %2  1
BINOP         %3  "<="  %1  %2
BRANCH_IF     %3  if_true_1,if_false_2
LABEL         if_true_1
CONST         %4  1
RETURN        %4
BRANCH        if_end_3
LABEL         if_end_3
LOAD_VAR      %5  n
LOAD_VAR      %6  n
CONST         %7  1
BINOP         %8  "-"  %6  %7
CALL_FUNCTION %9  factorial  %8
BINOP         %10 "*"  %5  %9
RETURN        %10
CONST         %11 "None"
RETURN        %11
LABEL         end_factorial_0
CONST         %12 "func:factorial@func_factorial_0"
STORE_VAR     factorial  %12
CONST         %13 5
CALL_FUNCTION %14 factorial  %13
STORE_VAR     result  %14
LOAD_VAR      %15 result
CALL_FUNCTION %16 print  %15
NEW_OBJECT    %17 "table"
CONST         %18 "x"
CONST         %19 10
STORE_INDEX   %17  %18  %19
CONST         %20 "y"
CONST         %21 20
STORE_INDEX   %17  %20  %21
CONST         %22 "1"
CONST         %23 "hello"
STORE_INDEX   %17  %22  %23
STORE_VAR     t  %17
# generic for: index-based iteration over pairs(t)
LOAD_VAR      %24 t
CALL_FUNCTION %25 pairs  %24
CONST         %26 "0"
CALL_FUNCTION %27 len  %25
LABEL         generic_for_cond_N
BINOP         %28 "<"  %26  %27
BRANCH_IF     %28  generic_for_body_N,generic_for_end_N
LABEL         generic_for_body_N
STORE_VAR     k  %26
LOAD_INDEX    %29 %25  %26
STORE_VAR     v  %29
LOAD_VAR      %30 k
LOAD_VAR      %31 v
CALL_FUNCTION %32 print  %30  %31
LABEL         generic_for_update_N
CONST         %33 "1"
BINOP         %34 "+"  %26  %33
STORE_VAR     __for_idx  %34
BRANCH        generic_for_cond_N
LABEL         generic_for_end_N
```

Note the table constructor: positional entries start at index 1 (Lua convention), but named entries use their key names.

## Design Notes

1. **Dual index expression types** -- Unlike most languages that use a single subscript/attribute node, Lua's tree-sitter grammar distinguishes `dot_index_expression` (`t.x`) from `bracket_index_expression` (`t[x]`). Both the expression dispatch table and `lua_decl.lower_lua_store_target` handle these separately.

2. **Method calls via `:` operator** -- Lua's `obj:method(args)` is represented as a `method_index_expression` inside a `function_call`. The `lua_expr.lower_lua_call` handler detects this and emits `CALL_METHOD`. The dot-call form `obj.method(args)` is also detected and treated as a method call.

3. **Table constructor positional indexing starts at 1** -- Lua arrays are 1-indexed by convention. The `lua_expr.lower_table_constructor` function initializes `positional_idx = 1` for positional entries, matching Lua semantics.

4. **`repeat ... until` uses negation** -- The `repeat` loop continues while the condition is FALSE. The frontend negates the condition with `UNOP("not", cond)` so that the `BRANCH_IF` pattern (branch to body when true, exit when false) correctly models the loop.

5. **`goto`/`label` as `BRANCH`/`LABEL`** -- Lua is one of the few languages that supports `goto`. The frontend maps `goto label` directly to `BRANCH(label_name)` and `::label::` to `LABEL(label_name)`, providing a clean mapping to the IR's control flow primitives.

6. **Block nodes handled via `block_node_types`** -- `chunk` and `block` are listed in `GrammarConstants.block_node_types`, so they are handled by the base `lower_block` method rather than needing explicit dispatch entries.

7. **Generic for uses synthetic index variable** -- The generic for loop stores the incremented index to `__for_idx` (a synthetic name) rather than updating the actual index register. This is a known simplification shared with Go's range-based for.

8. **No class/module support** -- Lua has no built-in class or module syntax. Object-oriented patterns in Lua are implemented via metatables, which are not modeled by this frontend.

9. **Anonymous functions vs. declarations** -- `function_definition` (expression) returns a register via `lua_expr.lower_lua_function_definition`, while `function_declaration` (statement) emits `STORE_VAR` via `lua_decl.lower_lua_function_declaration`. This distinction matches Lua's semantics where `local f = function() end` is an expression assignment and `function f() end` is a declaration.

10. **Scoping model** -- Uses default `BLOCK_SCOPED = False` (function-scoped). Lua's `local` variables are technically block-scoped in the real language, but the frontend treats them as function-scoped. No `$` mangling occurs.
