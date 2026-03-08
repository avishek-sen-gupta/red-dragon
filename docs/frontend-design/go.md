# Go Frontend

> `interpreter/frontends/go/` -- Extends `BaseFrontend`

## Overview

The Go frontend lowers tree-sitter Go ASTs into the RedDragon flattened TAC IR. It handles Go-specific constructs including goroutines (`go` statements), channels (`send_statement`, `select_statement`), multiple return values, short variable declarations (`:=`), range-based `for` loops, type assertions, slice expressions, composite literals, method declarations with receivers, `defer` statements, and both expression-switch and type-switch statements.

A notable design decision is the **hoisting of `func main()`**: rather than wrapping it in a function definition (which the VM would skip past), the Go frontend emits its body statements directly at the top level so that locals land in frame 0 of the VM.

## Directory Structure

```
interpreter/frontends/go/
  frontend.py         GoFrontend class (thin orchestrator)
  node_types.py        GoNodeType constants
  expressions.py       Expression lowerers (pure functions)
  control_flow.py      Control flow lowerers (pure functions)
  declarations.py      Declaration lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend
        +-- GoFrontend
```

`GoFrontend` extends `BaseFrontend` directly. The class is a thin orchestrator that builds dispatch tables from pure functions defined in the sibling modules. No other frontend extends `GoFrontend`.

## Grammar Constants (`_build_constants()`)

| Field | Value | Notes |
|---|---|---|
| `attribute_node_type` | `"selector_expression"` | Go uses `pkg.Name` / `obj.Field` syntax |
| `attr_object_field` | `"operand"` | tree-sitter Go names the LHS `operand` |
| `attr_attribute_field` | `"field"` | tree-sitter Go names the RHS `field` |
| `comment_types` | `frozenset({"comment"})` | Same as base |
| `noise_types` | `frozenset({"package_clause", "import_declaration", "\n"})` | Skips `package` and `import` declarations |
| `block_node_types` | `frozenset({"block", "statement_list", "source_file"})` | Block-like containers |

All other `GrammarConstants` fields (`func_name_field`, `func_params_field`, `func_body_field`, `if_condition_field`, `if_consequence_field`, `if_alternative_field`, `while_condition_field`, `while_body_field`, `call_function_field`, `call_arguments_field`, `none_literal`, `true_literal`, `false_literal`, `default_return_value`, `paren_expr_type`) retain their defaults.

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `"identifier"` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `"int_literal"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"float_literal"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"interpreted_string_literal"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"raw_string_literal"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"true"` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `"false"` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `"nil"` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `"binary_expression"` | `common_expr.lower_binop` | `BINOP` |
| `"unary_expression"` | `common_expr.lower_unop` | `UNOP` |
| `"call_expression"` | `go_expr.lower_go_call` | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `"selector_expression"` | `go_expr.lower_selector` | `LOAD_FIELD` |
| `"parenthesized_expression"` | `common_expr.lower_paren` | (unwraps inner expression) |
| `"index_expression"` | `go_expr.lower_go_index` | `LOAD_INDEX` |
| `"composite_literal"` | `go_expr.lower_composite_literal` | `NEW_OBJECT` + `STORE_FIELD` / `STORE_INDEX` |
| `"type_identifier"` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `"field_identifier"` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `"type_assertion_expression"` | `go_expr.lower_type_assertion` | `CALL_FUNCTION("type_assert", ...)` |
| `"slice_expression"` | `go_expr.lower_slice_expr` | `CALL_FUNCTION("slice", ...)` |
| `"func_literal"` | `go_expr.lower_func_literal` | `BRANCH` + `LABEL` + params + body + `RETURN` + `CONST func:ref` |
| `"channel_type"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"slice_type"` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `"expression_list"` | `common_expr.lower_const_literal` | `CONST` (raw text) |

**22 entries total.**

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `"expression_statement"` | `common_assign.lower_expression_statement` | (unwraps inner expression via `lower_stmt`) |
| `"short_var_declaration"` | `go_decl.lower_short_var_decl` | `STORE_VAR` per variable |
| `"assignment_statement"` | `go_decl.lower_go_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `"return_statement"` | `go_cf.lower_go_return` | `RETURN` (one per return value) |
| `"if_statement"` | `go_cf.lower_go_if` | `BRANCH_IF` + `LABEL` + `BRANCH` |
| `"for_statement"` | `go_cf.lower_go_for` | Dispatches to `_lower_go_for_clause`, `_lower_go_range`, or `_lower_go_bare_for` |
| `"function_declaration"` | `go_decl.lower_go_func_decl` | `BRANCH` + `LABEL` + params + body + `RETURN` + `CONST func:ref` + `STORE_VAR` |
| `"method_declaration"` | `go_decl.lower_go_method_decl` | Same as func_decl but includes receiver as first param |
| `"type_declaration"` | `go_decl.lower_go_type_decl` | `SYMBOLIC("struct:Name")` or `SYMBOLIC("type:Name")` + `STORE_VAR` |
| `"inc_statement"` | `go_cf.lower_go_inc` | `BINOP("+", operand, 1)` + store |
| `"dec_statement"` | `go_cf.lower_go_dec` | `BINOP("-", operand, 1)` + store |
| `"block"` | `lambda ctx, node: ctx.lower_block(node)` | Iterates named children |
| `"statement_list"` | `lambda ctx, node: ctx.lower_block(node)` | Base class block lowering |
| `"source_file"` | `lambda ctx, node: ctx.lower_block(node)` | Base class block lowering (top-level) |
| `"var_declaration"` | `go_decl.lower_go_var_decl` | `STORE_VAR` per `var_spec` |
| `"break_statement"` | `common_cf.lower_break` | `BRANCH` to break target |
| `"continue_statement"` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `"defer_statement"` | `go_cf.lower_defer_stmt` | Lower call, then `CALL_FUNCTION("defer", call_reg)` |
| `"go_statement"` | `go_cf.lower_go_stmt` | Lower call, then `CALL_FUNCTION("go", call_reg)` |
| `"expression_switch_statement"` | `go_cf.lower_expression_switch` | if/else chain with `BINOP("==")` per case |
| `"type_switch_statement"` | `go_cf.lower_type_switch` | `CALL_FUNCTION("type_check")` per case |
| `"select_statement"` | `go_cf.lower_select_stmt` | `LABEL` per case, `BRANCH` to end |
| `"send_statement"` | `go_cf.lower_send_stmt` | `CALL_FUNCTION("chan_send", ch, val)` |
| `"labeled_statement"` | `go_cf.lower_labeled_stmt` | `LABEL(name)` + lower body |
| `"const_declaration"` | `go_decl.lower_go_const_decl` | `STORE_VAR` per `const_spec` |
| `"goto_statement"` | `go_cf.lower_goto_stmt` | `BRANCH(label_name)` |
| `"receive_statement"` | `go_cf.lower_receive_stmt` | `CALL_FUNCTION("chan_recv", ch)` + `STORE_VAR` |

**27 entries total.**

## Language-Specific Lowering Methods

### `go_decl.lower_short_var_decl(ctx, node)`
Handles Go's `:=` short variable declaration. Extracts `left` (an `expression_list` of identifiers) and `right` (an `expression_list` of values), lowers each value, and emits `STORE_VAR` for each `(name, value)` pair using `zip`. Supports multiple assignment: `a, b := 1, 2`.

### `go_decl.lower_go_assignment(ctx, node)`
Handles Go's `=` assignment statement. Like short var declarations but uses `go_expr.lower_go_store_target` for each LHS target, supporting assignments to selectors (`obj.field`) and index expressions (`arr[i]`) in addition to plain identifiers.

### `go_expr.extract_expression_list(ctx, node) -> list[str]`
Extracts identifier names from an `expression_list` node. If the node is a single identifier, returns a one-element list. Used to destructure multi-value LHS patterns.

### `go_expr.get_expression_list_children(node) -> list`
Returns the raw child AST nodes from an `expression_list`. Used when the caller needs nodes (not text) for further processing (e.g., store targets).

### `go_expr.lower_expression_list(ctx, node) -> list[str]`
Lowers each expression in an `expression_list`, returns a list of registers holding the results.

### `go_cf.lower_go_return(ctx, node)`
Handles Go's return statement with support for multiple return values. If the return contains an `expression_list`, each sub-expression gets its own `RETURN` instruction. A bare `return` emits `CONST "None"` + `RETURN`.

### `go_expr.lower_go_call(ctx, node) -> str`
Lowers `call_expression`. Three paths:
1. **Method call via selector**: `obj.Method(...)` -- emits `CALL_METHOD`.
2. **Plain function call**: `func(...)` where `func` is an identifier -- emits `CALL_FUNCTION`.
3. **Dynamic call**: anything else (e.g., function from map lookup) -- emits `CALL_UNKNOWN`.

### `go_expr.lower_selector(ctx, node) -> str`
Lowers `selector_expression` (`obj.field`) as `LOAD_FIELD`. Uses Go-specific field names: `operand` for the object, `field` for the attribute.

### `go_expr.lower_go_index(ctx, node) -> str`
Lowers `index_expression` (`arr[i]`) as `LOAD_INDEX`. Uses Go-specific field names: `operand` for the array, `index` for the subscript.

### `go_cf.lower_go_if(ctx, node)`
Handles Go's `if` statement. Supports `else if` chains by recursively calling itself when the alternative is another `if_statement`. Otherwise, falls through to `ctx.lower_block` for an `else` block.

### `go_cf.lower_go_for(ctx, node)`
Dispatches Go's `for` statement to one of three sub-handlers based on the presence of child nodes:
- `for_clause` child -> `_lower_go_for_clause` (C-style for)
- `range_clause` child -> `_lower_go_range` (range-based for)
- Neither -> `_lower_go_bare_for` (infinite or condition-only loop)

### `go_decl.lower_go_func_decl(ctx, node)`
Lowers `function_declaration`. Special-cases `func main()` by hoisting its body to the top level via `_lower_go_main_hoisted`. All other functions get the standard function lowering: `BRANCH` past body, `LABEL`, params, body, implicit `RETURN`, `CONST func:ref`, `STORE_VAR`.

### `go_decl.lower_go_method_decl(ctx, node)`
Lowers `method_declaration`. Identical to `lower_go_func_decl` except it also lowers the receiver as the first parameter via `go_decl.lower_go_params(ctx, receiver_node)`.

### `go_decl.lower_go_params(ctx, params_node)`
Lowers Go-specific parameter declarations. Handles two cases:
- `parameter_declaration` nodes: extracts the `name` field.
- Direct `identifier` children (e.g., in receiver declarations).
Each parameter emits `SYMBOLIC("param:name")` + `STORE_VAR`.

### `go_cf.lower_go_inc(ctx, node)` / `go_cf.lower_go_dec(ctx, node)`
Lower Go's `i++` and `i--` statements (which are statements, not expressions in Go). Loads the operand, emits `BINOP("+"/"-", operand, 1)`, stores back via `go_expr.lower_go_store_target`.

### `go_expr.lower_go_store_target(ctx, target, val_reg, parent_node)`
Handles Go-specific target types:
- `"identifier"` -> `STORE_VAR`
- `"selector_expression"` -> `STORE_FIELD` (using `operand`/`field` fields)
- `"index_expression"` -> `STORE_INDEX` (using `operand`/`index` fields)
- Fallback -> `STORE_VAR` with raw text

### `go_decl.lower_go_type_decl(ctx, node)`
Lowers `type_declaration` by iterating `type_spec` children. For each spec, emits a `CLASS` block if the type is a `struct_type`, otherwise `SYMBOLIC("type:Name")`, followed by `STORE_VAR`.

### `go_decl.lower_go_var_decl(ctx, node)`
Lowers `var_declaration` by iterating `var_spec` children. For each spec with a value, lowers the value and emits `STORE_VAR`. Specs without values get `CONST "None"` + `STORE_VAR`.

### `go_expr.lower_composite_literal(ctx, node) -> str`
Lowers Go composite literals (e.g., `Point{X: 1, Y: 2}` or `[]int{1, 2, 3}`). Emits `NEW_OBJECT(type_name)`, then processes elements:
- `keyed_element` -> `STORE_FIELD(obj, key_name, val)`
- `literal_element` -> `STORE_INDEX(obj, idx, val)` (positional)
- Direct expression -> `STORE_INDEX(obj, idx, val)` (positional)

### `go_expr.lower_type_assertion(ctx, node) -> str`
Lowers `x.(Type)` as `CALL_FUNCTION("type_assert", x_reg, "Type")`. Falls back to `"interface{}"` if no type is specified.

### `go_expr.lower_slice_expr(ctx, node) -> str`
Lowers `a[low:high]` as `CALL_FUNCTION("slice", a_reg, start_reg, end_reg)`. Missing bounds default to `CONST "0"` (start) or `CONST "None"` (end).

### `go_expr.lower_func_literal(ctx, node) -> str`
Lowers anonymous function expressions (`func(params) { body }`). Generates a unique name `__anon_N`, emits function body between labels, and returns a register holding `func:ref`.

### `go_cf.lower_defer_stmt(ctx, node)`
Lowers `defer f()`. Lowers the call expression child, then emits `CALL_FUNCTION("defer", call_reg)`.

### `go_cf.lower_go_stmt(ctx, node)`
Lowers `go f()`. Lowers the call expression child, then emits `CALL_FUNCTION("go", call_reg)`.

### `go_cf.lower_expression_switch(ctx, node)`
Lowers `switch expr { case val: ... }` as an if/else chain. For each `expression_case`, compares the switch value to the case value using `BINOP("==")` and branches accordingly. Default cases emit their body unconditionally. Uses `ctx.push_loop`/`ctx.pop_loop` with the end label so `break` exits the switch.

### `go_cf.lower_type_switch(ctx, node)`
Lowers `switch x.(type) { case int: ... }`. Extracts the expression from the `type_switch_header`, then for each `type_case` emits `CALL_FUNCTION("type_check", expr, "TypeName")` + `BRANCH_IF`. Uses `ctx.push_loop`/`ctx.pop_loop` for break support.

### `go_cf.lower_select_stmt(ctx, node)`
Lowers Go's `select { case <-ch: ... }`. Emits a `LABEL` for each `communication_case` or `default_case`, lowers the body, and branches to the end label.

### `go_cf.lower_send_stmt(ctx, node)`
Lowers `ch <- val` as `CALL_FUNCTION("chan_send", ch_reg, val_reg)`.

### `go_cf.lower_labeled_stmt(ctx, node)`
Lowers `label: stmt` by emitting `LABEL(label_name)` and then lowering the body statements.

### `go_decl.lower_go_const_decl(ctx, node)`
Lowers `const` declarations. Iterates `const_spec` children; each spec with a value emits the lowered value + `STORE_VAR`. Specs without values emit `CONST "None"` + `STORE_VAR`.

### `go_cf.lower_goto_stmt(ctx, node)`
Lowers `goto label` as `BRANCH(label_name)`.

### `go_cf.lower_receive_stmt(ctx, node)`
Lowers `v := <-ch` as `CALL_FUNCTION("chan_recv", ch_reg)` + `STORE_VAR`.

## Canonical Literal Handling

| Go Node Type | Handler | Emitted IR |
|---|---|---|
| `"nil"` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `"true"` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `"false"` | `common_expr.lower_canonical_false` | `CONST "False"` |

Go's `nil`, `true`, and `false` are mapped to the Python-canonical forms `"None"`, `"True"`, and `"False"` in the IR. This enables cross-language comparison and analysis.

## Example

**Go source:**
```go
package main

func add(a int, b int) int {
    return a + b
}

func main() {
    result := add(1, 2)
    fmt.Println(result)
}
```

**Emitted IR (simplified):**
```
LABEL         ENTRY
BRANCH        end_add_0
LABEL         func_add_0
SYMBOLIC      %0  "param:a"
STORE_VAR     a  %0
SYMBOLIC      %1  "param:b"
STORE_VAR     b  %1
LOAD_VAR      %2  a
LOAD_VAR      %3  b
BINOP         %4  "+"  %2  %3
RETURN        %4
CONST         %5  "None"
RETURN        %5
LABEL         end_add_0
CONST         %6  "func:add@func_add_0"
STORE_VAR     add  %6
# main is hoisted -- its body appears at top level:
CONST         %7  1
CONST         %8  2
CALL_FUNCTION %9  add  %7  %8
STORE_VAR     result  %9
LOAD_VAR      %10 fmt
CALL_METHOD   %11 %10  Println  %9
```

Note how `func main()` body is inlined at the top level (not wrapped in a function definition).

## Design Notes

1. **`func main()` hoisting** -- The `_GO_MAIN_FUNC_NAME = "main"` module-level constant in `declarations.py` drives the hoisting check. When a `function_declaration` has name `"main"`, its body is emitted directly via `_lower_go_main_hoisted` rather than wrapped in the standard function definition pattern. This is critical for the VM to execute Go programs correctly.

2. **Multiple return values** -- Go functions can return multiple values (`return a, b`). The frontend handles this by emitting one `RETURN` instruction per value. The VM/analysis layer must handle multiple sequential `RETURN` opcodes.

3. **`for` statement dispatch** -- Go's single `for` keyword covers C-style loops, range-based iteration, condition-only loops, and infinite loops. The frontend detects the loop variant by looking for `for_clause`, `range_clause`, or bare condition children.

4. **Switch as if/else chain** -- Both `expression_switch_statement` and `type_switch_statement` are lowered as if/else chains. The switch end label is pushed onto the loop/break stack so that `break` statements within switch cases can exit the switch.

5. **Goroutines and channels** -- `go` and `defer` statements are modeled as `CALL_FUNCTION("go", ...)` and `CALL_FUNCTION("defer", ...)` respectively. Channel sends (`ch <- val`) become `CALL_FUNCTION("chan_send", ...)`. Channel receives (`<-ch`) become `CALL_FUNCTION("chan_recv", ...)`. These are symbolic representations; the IR does not model true concurrency.

6. **Pure function store target** -- `go_expr.lower_go_store_target` handles Go-specific target types. Go's `selector_expression` and `index_expression` use different field names (`operand`/`field`/`index`) from the base class expectations.

7. **Range-based for uses synthetic variables** -- The range loop increments `__for_idx` (a synthetic name) rather than the user's index variable. This is a known simplification.

8. **`GoNodeType` constants** -- All tree-sitter node type strings are centralised in `node_types.py` as `GoNodeType` class attributes, so typos are caught at import time and grep/refactor is trivial.

9. **Scoping model** -- Uses `BLOCK_SCOPED = True` (LLVM-style name mangling). Shadowed variables in nested blocks, range-for loop variables, and C-style for-loop init declarations are renamed (`x` → `x$1`) to disambiguate. See [base-frontend.md](base-frontend.md#block-scopes) for the general mechanism.
