# Go Frontend

> `interpreter/frontends/go.py` -- Extends `BaseFrontend` -- 1117 lines

## Overview

The Go frontend lowers tree-sitter Go ASTs into the RedDragon flattened TAC IR. It handles Go-specific constructs including goroutines (`go` statements), channels (`send_statement`, `select_statement`), multiple return values, short variable declarations (`:=`), range-based `for` loops, type assertions, slice expressions, composite literals, method declarations with receivers, `defer` statements, and both expression-switch and type-switch statements.

A notable design decision is the **hoisting of `func main()`**: rather than wrapping it in a function definition (which the VM would skip past), the Go frontend emits its body statements directly at the top level so that locals land in frame 0 of the VM.

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend
        +-- GoFrontend
```

`GoFrontend` extends `BaseFrontend` directly. No other frontend extends `GoFrontend`.

## Overridden Constants

| Constant | BaseFrontend Default | GoFrontend Value | Notes |
|---|---|---|---|
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"selector_expression"` | Go uses `pkg.Name` / `obj.Field` syntax |
| `ATTR_OBJECT_FIELD` | `"object"` | `"operand"` | tree-sitter Go names the LHS `operand` |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"field"` | tree-sitter Go names the RHS `field` |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` | Same as base |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"package_clause", "import_declaration", "\n"})` | Skips `package` and `import` declarations |

All other constants (`FUNC_NAME_FIELD`, `FUNC_PARAMS_FIELD`, `FUNC_BODY_FIELD`, `IF_CONDITION_FIELD`, `IF_CONSEQUENCE_FIELD`, `IF_ALTERNATIVE_FIELD`, `WHILE_CONDITION_FIELD`, `WHILE_BODY_FIELD`, `CALL_FUNCTION_FIELD`, `CALL_ARGUMENTS_FIELD`, `NONE_LITERAL`, `TRUE_LITERAL`, `FALSE_LITERAL`, `DEFAULT_RETURN_VALUE`, `PAREN_EXPR_TYPE`) retain their `BaseFrontend` defaults.

## Expression Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `"identifier"` | `_lower_identifier` | `LOAD_VAR` |
| `"int_literal"` | `_lower_const_literal` | `CONST` (raw text) |
| `"float_literal"` | `_lower_const_literal` | `CONST` (raw text) |
| `"interpreted_string_literal"` | `_lower_const_literal` | `CONST` (raw text) |
| `"raw_string_literal"` | `_lower_const_literal` | `CONST` (raw text) |
| `"true"` | `_lower_canonical_true` | `CONST "True"` |
| `"false"` | `_lower_canonical_false` | `CONST "False"` |
| `"nil"` | `_lower_canonical_none` | `CONST "None"` |
| `"binary_expression"` | `_lower_binop` | `BINOP` |
| `"unary_expression"` | `_lower_unop` | `UNOP` |
| `"call_expression"` | `_lower_go_call` | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `"selector_expression"` | `_lower_selector` | `LOAD_FIELD` |
| `"index_expression"` | `_lower_go_index` | `LOAD_INDEX` |
| `"parenthesized_expression"` | `_lower_paren` | (unwraps inner expression) |
| `"composite_literal"` | `_lower_composite_literal` | `NEW_OBJECT` + `STORE_FIELD` / `STORE_INDEX` |
| `"type_identifier"` | `_lower_identifier` | `LOAD_VAR` |
| `"field_identifier"` | `_lower_identifier` | `LOAD_VAR` |
| `"type_assertion_expression"` | `_lower_type_assertion` | `CALL_FUNCTION("type_assert", ...)` |
| `"slice_expression"` | `_lower_slice_expr` | `CALL_FUNCTION("slice", ...)` |
| `"func_literal"` | `_lower_func_literal` | `BRANCH` + `LABEL` + params + body + `RETURN` + `CONST func:ref` |

**19 entries total.**

## Statement Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `"expression_statement"` | `_lower_expression_statement` | (unwraps inner expression via `_lower_stmt`) |
| `"short_var_declaration"` | `_lower_short_var_decl` | `STORE_VAR` per variable |
| `"assignment_statement"` | `_lower_go_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `"return_statement"` | `_lower_go_return` | `RETURN` (one per return value) |
| `"if_statement"` | `_lower_go_if` | `BRANCH_IF` + `LABEL` + `BRANCH` |
| `"for_statement"` | `_lower_go_for` | Dispatches to `_lower_go_for_clause`, `_lower_go_range`, or `_lower_go_bare_for` |
| `"function_declaration"` | `_lower_go_func_decl` | `BRANCH` + `LABEL` + params + body + `RETURN` + `CONST func:ref` + `STORE_VAR` |
| `"method_declaration"` | `_lower_go_method_decl` | Same as func_decl but includes receiver as first param |
| `"type_declaration"` | `_lower_go_type_decl` | `SYMBOLIC("struct:Name")` or `SYMBOLIC("type:Name")` + `STORE_VAR` |
| `"inc_statement"` | `_lower_go_inc` | `BINOP("+", operand, 1)` + store |
| `"dec_statement"` | `_lower_go_dec` | `BINOP("-", operand, 1)` + store |
| `"block"` | `_lower_go_block` | Iterates named children |
| `"statement_list"` | `_lower_block` | Base class block lowering |
| `"source_file"` | `_lower_block` | Base class block lowering (top-level) |
| `"var_declaration"` | `_lower_go_var_decl` | `STORE_VAR` per `var_spec` |
| `"break_statement"` | `_lower_break` | `BRANCH` to break target |
| `"continue_statement"` | `_lower_continue` | `BRANCH` to continue label |
| `"defer_statement"` | `_lower_defer_stmt` | Lower call, then `CALL_FUNCTION("defer", call_reg)` |
| `"go_statement"` | `_lower_go_stmt` | Lower call, then `CALL_FUNCTION("go", call_reg)` |
| `"expression_switch_statement"` | `_lower_expression_switch` | if/else chain with `BINOP("==")` per case |
| `"type_switch_statement"` | `_lower_type_switch` | `CALL_FUNCTION("type_check")` per case |
| `"select_statement"` | `_lower_select_stmt` | `LABEL` per case, `BRANCH` to end |
| `"send_statement"` | `_lower_send_stmt` | `CALL_FUNCTION("chan_send", ch, val)` |
| `"labeled_statement"` | `_lower_labeled_stmt` | `LABEL(name)` + lower body |
| `"const_declaration"` | `_lower_go_const_decl` | `STORE_VAR` per `const_spec` |
| `"goto_statement"` | `_lower_goto_stmt` | `BRANCH(label_name)` |

**26 entries total.**

## Language-Specific Lowering Methods

### `_lower_go_block(node)`
Iterates all named children of a block node, lowering each as a statement. Used instead of the base `_lower_block` for Go blocks because Go uses `{}` delimiters rather than indentation-based block structure.

### `_lower_short_var_decl(node)`
Handles Go's `:=` short variable declaration. Extracts `left` (an `expression_list` of identifiers) and `right` (an `expression_list` of values), lowers each value, and emits `STORE_VAR` for each `(name, value)` pair using `zip`. Supports multiple assignment: `a, b := 1, 2`.

### `_lower_go_assignment(node)`
Handles Go's `=` assignment statement. Like short var declarations but uses `_lower_store_target` for each LHS target, supporting assignments to selectors (`obj.field`) and index expressions (`arr[i]`) in addition to plain identifiers.

### `_extract_expression_list(node) -> list[str]`
Extracts identifier names from an `expression_list` node. If the node is a single identifier, returns a one-element list. Used to destructure multi-value LHS patterns.

### `_get_expression_list_children(node) -> list`
Returns the raw child AST nodes from an `expression_list`. Used when the caller needs nodes (not text) for further processing (e.g., store targets).

### `_lower_expression_list(node) -> list[str]`
Lowers each expression in an `expression_list`, returns a list of registers holding the results.

### `_lower_go_return(node)`
Handles Go's return statement with support for multiple return values. If the return contains an `expression_list`, each sub-expression gets its own `RETURN` instruction. A bare `return` emits `CONST "None"` + `RETURN`.

### `_lower_go_call(node) -> str`
Lowers `call_expression`. Three paths:
1. **Method call via selector**: `obj.Method(...)` -- emits `CALL_METHOD`.
2. **Plain function call**: `func(...)` where `func` is an identifier -- emits `CALL_FUNCTION`.
3. **Dynamic call**: anything else (e.g., function from map lookup) -- emits `CALL_UNKNOWN`.

### `_lower_selector(node) -> str`
Lowers `selector_expression` (`obj.field`) as `LOAD_FIELD`. Uses Go-specific field names: `operand` for the object, `field` for the attribute.

### `_lower_go_index(node) -> str`
Lowers `index_expression` (`arr[i]`) as `LOAD_INDEX`. Uses Go-specific field names: `operand` for the array, `index` for the subscript.

### `_lower_go_if(node)`
Handles Go's `if` statement. Supports `else if` chains by recursively calling itself when the alternative is another `if_statement`. Otherwise, falls through to `_lower_go_block` for an `else` block.

### `_lower_go_for(node)`
Dispatches Go's `for` statement to one of three sub-handlers based on the presence of child nodes:
- `for_clause` child -> `_lower_go_for_clause` (C-style for)
- `range_clause` child -> `_lower_go_range` (range-based for)
- Neither -> `_lower_go_bare_for` (infinite or condition-only loop)

### `_lower_go_for_clause(clause, body_node, parent)`
Lowers C-style `for init; cond; update { body }`. Emits initializer, condition check with `BRANCH_IF`, body, update expression, and back-edge `BRANCH`. Uses `_push_loop`/`_pop_loop` for break/continue targeting.

### `_lower_go_range(clause, body_node, parent)`
Lowers `for k, v := range expr { body }`. Emits index-based iteration: initializes idx to 0, computes `len(expr)`, branches on `idx < len`, stores index/value variables, executes body, increments index.

### `_lower_go_bare_for(node, body_node)`
Lowers bare `for { ... }` (infinite loop) or `for cond { ... }` (condition-only loop). If no condition child is found, emits unconditional `BRANCH` to body (infinite loop).

### `_lower_go_func_decl(node)`
Lowers `function_declaration`. Special-cases `func main()` by hoisting its body to the top level via `_lower_go_main_hoisted`. All other functions get the standard function lowering: `BRANCH` past body, `LABEL`, params, body, implicit `RETURN`, `CONST func:ref`, `STORE_VAR`.

### `_lower_go_main_hoisted(body_node)`
Emits the body of `func main()` directly at the top level. This ensures `main`'s local variables land in VM frame 0, making Go programs behave like other languages where top-level code is the entry point.

### `_lower_go_method_decl(node)`
Lowers `method_declaration`. Identical to `_lower_go_func_decl` except it also lowers the receiver as the first parameter via `_lower_go_params(receiver_node)`.

### `_lower_go_params(params_node)`
Lowers Go-specific parameter declarations. Handles two cases:
- `parameter_declaration` nodes: extracts the `name` field.
- Direct `identifier` children (e.g., in receiver declarations).
Each parameter emits `SYMBOLIC("param:name")` + `STORE_VAR`.

### `_lower_go_inc(node)` / `_lower_go_dec(node)`
Lower Go's `i++` and `i--` statements (which are statements, not expressions in Go). Loads the operand, emits `BINOP("+"/"-", operand, 1)`, stores back via `_lower_store_target`.

### `_lower_store_target(target, val_reg, parent_node)`
**Overrides `BaseFrontend._lower_store_target`.** Handles Go-specific target types:
- `"identifier"` -> `STORE_VAR`
- `"selector_expression"` -> `STORE_FIELD` (using `operand`/`field` fields)
- `"index_expression"` -> `STORE_INDEX` (using `operand`/`index` fields)
- Fallback -> `STORE_VAR` with raw text

### `_lower_go_type_decl(node)`
Lowers `type_declaration` by iterating `type_spec` children. For each spec, emits `SYMBOLIC("struct:Name")` if the type is a `struct_type`, otherwise `SYMBOLIC("type:Name")`, followed by `STORE_VAR`.

### `_lower_go_var_decl(node)`
Lowers `var_declaration` by iterating `var_spec` children. For each spec with a value, lowers the value and emits `STORE_VAR`. Specs without values get `CONST "None"` + `STORE_VAR`.

### `_lower_composite_literal(node) -> str`
Lowers Go composite literals (e.g., `Point{X: 1, Y: 2}` or `[]int{1, 2, 3}`). Emits `NEW_OBJECT(type_name)`, then processes elements:
- `keyed_element` -> `STORE_FIELD(obj, key_name, val)`
- `literal_element` -> `STORE_INDEX(obj, idx, val)` (positional)
- Direct expression -> `STORE_INDEX(obj, idx, val)` (positional)

### `_lower_type_assertion(node) -> str`
Lowers `x.(Type)` as `CALL_FUNCTION("type_assert", x_reg, "Type")`. Falls back to `"interface{}"` if no type is specified.

### `_lower_slice_expr(node) -> str`
Lowers `a[low:high]` as `CALL_FUNCTION("slice", a_reg, start_reg, end_reg)`. Missing bounds default to `CONST "0"` (start) or `CONST "None"` (end).

### `_make_const(value) -> str`
Helper that emits a `CONST` instruction and returns the register. Used by `_lower_slice_expr`.

### `_lower_func_literal(node) -> str`
Lowers anonymous function expressions (`func(params) { body }`). Generates a unique name `__anon_N`, emits function body between labels, and returns a register holding `func:ref`.

### `_lower_defer_stmt(node)`
Lowers `defer f()`. Lowers the call expression child, then emits `CALL_FUNCTION("defer", call_reg)`.

### `_lower_go_stmt(node)`
Lowers `go f()`. Lowers the call expression child, then emits `CALL_FUNCTION("go", call_reg)`.

### `_lower_expression_switch(node)`
Lowers `switch expr { case val: ... }` as an if/else chain. For each `expression_case`, compares the switch value to the case value using `BINOP("==")` and branches accordingly. Default cases emit their body unconditionally. Uses `_push_loop`/`_pop_loop` with the end label so `break` exits the switch.

### `_lower_type_switch(node)`
Lowers `switch x.(type) { case int: ... }`. Extracts the expression from the `type_switch_header`, then for each `type_case` emits `CALL_FUNCTION("type_check", expr, "TypeName")` + `BRANCH_IF`. Uses `_push_loop`/`_pop_loop` for break support.

### `_lower_select_stmt(node)`
Lowers Go's `select { case <-ch: ... }`. Emits a `LABEL` for each `communication_case` or `default_case`, lowers the body, and branches to the end label.

### `_lower_send_stmt(node)`
Lowers `ch <- val` as `CALL_FUNCTION("chan_send", ch_reg, val_reg)`.

### `_lower_labeled_stmt(node)`
Lowers `label: stmt` by emitting `LABEL(label_name)` and then lowering the body statements.

### `_lower_go_const_decl(node)` / `_lower_const_spec(node)`
Lowers `const` declarations. Iterates `const_spec` children; each spec with a value emits the lowered value + `STORE_VAR`. Specs without values emit `CONST "None"` + `STORE_VAR`.

### `_lower_goto_stmt(node)`
Lowers `goto label` as `BRANCH(label_name)`.

## Canonical Literal Handling

| Go Node Type | Canonical Method | Emitted IR |
|---|---|---|
| `"nil"` | `_lower_canonical_none` | `CONST "None"` |
| `"true"` | `_lower_canonical_true` | `CONST "True"` |
| `"false"` | `_lower_canonical_false` | `CONST "False"` |

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

1. **`func main()` hoisting** -- The `_GO_MAIN_FUNC_NAME = "main"` class constant drives the hoisting check. When a `function_declaration` has name `"main"`, its body is emitted directly via `_lower_go_main_hoisted` rather than wrapped in the standard function definition pattern. This is critical for the VM to execute Go programs correctly.

2. **Multiple return values** -- Go functions can return multiple values (`return a, b`). The frontend handles this by emitting one `RETURN` instruction per value. The VM/analysis layer must handle multiple sequential `RETURN` opcodes.

3. **`for` statement dispatch** -- Go's single `for` keyword covers C-style loops, range-based iteration, condition-only loops, and infinite loops. The frontend detects the loop variant by looking for `for_clause`, `range_clause`, or bare condition children.

4. **Switch as if/else chain** -- Both `expression_switch_statement` and `type_switch_statement` are lowered as if/else chains. The switch end label is pushed onto the loop/break stack so that `break` statements within switch cases can exit the switch.

5. **Goroutines and channels** -- `go` and `defer` statements are modeled as `CALL_FUNCTION("go", ...)` and `CALL_FUNCTION("defer", ...)` respectively. Channel sends (`ch <- val`) become `CALL_FUNCTION("chan_send", ...)`. These are symbolic representations; the IR does not model true concurrency.

6. **Overridden `_lower_store_target`** -- Go's `selector_expression` and `index_expression` use different field names (`operand`/`field`/`index`) from the base class expectations, so the store target logic is fully reimplemented.

7. **Range-based for uses synthetic variables** -- The range loop increments `__for_idx` (a synthetic name) rather than the user's index variable. This is a known simplification.
