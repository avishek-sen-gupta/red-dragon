# PHP Frontend

> `interpreter/frontends/php/` -- Extends `BaseFrontend` -- per-language directory architecture

## Overview

The PHP frontend lowers tree-sitter PHP ASTs into the RedDragon three-address-code (TAC) IR. PHP's sigil-prefixed variables (`$var`), `->` member access, `::` static access, and extensive OOP constructs (classes, interfaces, traits, enums) all receive dedicated lowering functions. The frontend handles PHP-specific idioms including `echo`, `foreach` with key-value pairs, arrow functions (`fn() =>`), anonymous functions (closures), match expressions, heredoc/nowdoc strings, goto/labels, nullsafe member access (`?->`), string interpolation, dynamic variables, include/require, and variadic unpacking.

## Directory Structure

```
interpreter/frontends/php/
  frontend.py         -- PhpFrontend class (thin orchestrator)
  node_types.py       -- PHPNodeType constants class
  expressions.py      -- PHP-specific expression lowerers (pure functions)
  control_flow.py     -- PHP-specific control flow lowerers (pure functions)
  declarations.py     -- PHP-specific declaration lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (abstract)
  +-- BaseFrontend (_base.py)
        +-- PhpFrontend (php/frontend.py)
```

`PhpFrontend` is a thin orchestrator that builds dispatch tables from pure functions. All lowering logic lives in the `expressions`, `control_flow`, and `declarations` modules as pure functions taking `(ctx: TreeSitterEmitContext, node)`. Common lowering infrastructure (register allocation, label generation, `emit`, `lower_block`, canonical literal helpers) is inherited from `BaseFrontend`.

## Grammar Constants (`_build_constants()`)

| Field | Value |
|---|---|
| `attr_object_field` | `"object"` |
| `attr_attribute_field` | `"name"` |
| `attribute_node_type` | `PHPNodeType.MEMBER_ACCESS_EXPRESSION` |
| `comment_types` | `frozenset({PHPNodeType.COMMENT})` |
| `noise_types` | `frozenset({PHPNodeType.PHP_TAG, PHPNodeType.TEXT_INTERPOLATION, PHPNodeType.PHP_END_TAG, PHPNodeType.NEWLINE})` |
| `block_node_types` | `frozenset({PHPNodeType.COMPOUND_STATEMENT, PHPNodeType.PROGRAM})` |

Note: `none_literal`, `true_literal`, `false_literal`, `default_return_value` all retain their `GrammarConstants` defaults (`"None"`, `"True"`, `"False"`, `"None"` respectively), since canonical lowering methods are used.

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `variable_name` | `php_expr.lower_php_variable` | `LOAD_VAR` with `$`-prefixed name |
| `name` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `integer` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `float` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `string` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `encapsed_string` | `php_expr.lower_php_encapsed_string` | `CONST` or interpolation (`CONST` + `LOAD_VAR` + `BINOP +`) |
| `boolean` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `binary_expression` | `common_expr.lower_binop` | `BINOP` |
| `unary_op_expression` | `common_expr.lower_unop` | `UNOP` |
| `update_expression` | `common_expr.lower_update_expr` | `BINOP` + `STORE_VAR` (i++/i--) |
| `function_call_expression` | `php_expr.lower_php_func_call` | `CALL_FUNCTION` or `CALL_UNKNOWN` |
| `member_call_expression` | `php_expr.lower_php_method_call` | `CALL_METHOD` |
| `member_access_expression` | `php_expr.lower_php_member_access` | `LOAD_FIELD` |
| `subscript_expression` | `php_expr.lower_php_subscript` | `LOAD_INDEX` |
| `parenthesized_expression` | `common_expr.lower_paren` | (unwraps inner expr) |
| `array_creation_expression` | `php_expr.lower_php_array` | `NEW_ARRAY`/`NEW_OBJECT` + `STORE_INDEX` |
| `assignment_expression` | `php_expr.lower_php_assignment_expr` | `STORE_VAR`/`STORE_FIELD`/`STORE_INDEX` |
| `augmented_assignment_expression` | `php_expr.lower_php_augmented_assignment_expr` | `BINOP` + `STORE_*` |
| `cast_expression` | `php_expr.lower_php_cast` | (passthrough to inner expr) |
| `conditional_expression` | `php_expr.lower_php_ternary` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` |
| `throw_expression` | `php_expr.lower_php_throw_expr` | `THROW` + `CONST "None"` |
| `object_creation_expression` | `php_expr.lower_php_object_creation` | `NEW_OBJECT` + `CALL_METHOD("__construct")` |
| `match_expression` | `php_expr.lower_php_match_expression` | `BINOP ===` + `BRANCH_IF` chain |
| `arrow_function` | `php_expr.lower_php_arrow_function` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `scoped_call_expression` | `php_expr.lower_php_scoped_call` | `CALL_FUNCTION` (qualified `Class::method`) |
| `anonymous_function` | `php_expr.lower_php_anonymous_function` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `nullsafe_member_access_expression` | `php_expr.lower_php_nullsafe_member_access` | `LOAD_FIELD` (null-safety is semantic) |
| `class_constant_access_expression` | `php_expr.lower_php_class_constant_access` | `LOAD_FIELD` on class |
| `scoped_property_access_expression` | `php_expr.lower_php_scoped_property_access` | `LOAD_FIELD` on class |
| `yield_expression` | `php_expr.lower_php_yield` | `CALL_FUNCTION("yield", ...)` |
| `reference_assignment_expression` | `php_expr.lower_php_reference_assignment` | `STORE_VAR` (ignores reference semantics) |
| `heredoc` | `php_expr.lower_php_heredoc` | `CONST` or interpolation |
| `nowdoc` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `relative_scope` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `dynamic_variable_name` | `php_expr.lower_php_dynamic_variable` | Unwraps to inner variable/expression |
| `include_expression` | `php_expr.lower_php_include` | `CALL_FUNCTION("include", ...)` |
| `nullsafe_member_call_expression` | `php_expr.lower_php_nullsafe_method_call` | `CALL_METHOD` (like regular method call) |
| `require_once_expression` | `php_expr.lower_php_include` | `CALL_FUNCTION("require_once", ...)` |
| `variadic_unpacking` | `php_expr.lower_php_variadic_unpacking` | `CALL_FUNCTION("spread", inner)` |

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `common_assign.lower_expression_statement` | (unwraps inner expr) |
| `return_statement` | `php_cf.lower_php_return` | `RETURN` |
| `echo_statement` | `php_cf.lower_php_echo` | `CALL_FUNCTION("echo", ...)` |
| `if_statement` | `php_cf.lower_php_if` | `BRANCH_IF` + labels |
| `while_statement` | `common_cf.lower_while` | (inherited) `BRANCH_IF` loop |
| `for_statement` | `common_cf.lower_c_style_for` | (inherited) C-style for loop |
| `foreach_statement` | `php_cf.lower_php_foreach` | Index-based loop with `LOAD_INDEX` |
| `function_definition` | `php_decl.lower_php_func_def` | `BRANCH`/`LABEL`/`RETURN`/`DECL_VAR` |
| `method_declaration` | `php_decl.lower_php_method_decl` | `BRANCH`/`LABEL`/`RETURN`/`DECL_VAR` |
| `class_declaration` | `php_decl.lower_php_class` | `BRANCH`/`LABEL`/`DECL_VAR` (class ref) |
| `throw_expression` | `php_cf.lower_php_throw` | `THROW` |
| `compound_statement` | `php_cf.lower_php_compound` | (iterates children, skips `{`/`}`) |
| `program` | `lambda ctx, node: ctx.lower_block(node)` | (inherited block lowering) |
| `break_statement` | `common_cf.lower_break` | `BRANCH` to break target |
| `continue_statement` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `try_statement` | `php_cf.lower_php_try` | `LABEL`/`SYMBOLIC`/`BRANCH` (try/catch/finally) |
| `switch_statement` | `php_cf.lower_php_switch` | `BINOP ==` + `BRANCH_IF` chain |
| `do_statement` | `php_cf.lower_php_do` | Body-first loop + `BRANCH_IF` |
| `namespace_definition` | `php_cf.lower_php_namespace` | (lowers body compound_statement) |
| `interface_declaration` | `php_decl.lower_php_interface` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `trait_declaration` | `php_decl.lower_php_trait` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `function_static_declaration` | `php_decl.lower_php_function_static` | `STORE_VAR` per static variable |
| `enum_declaration` | `php_decl.lower_php_enum` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `named_label_statement` | `php_cf.lower_php_named_label` | `LABEL user_{name}` |
| `goto_statement` | `php_cf.lower_php_goto` | `BRANCH user_{name}` |
| `property_declaration` | `php_decl.lower_php_property_declaration` | `STORE_FIELD` on `"self"` |
| `use_declaration` | `php_decl.lower_php_use_declaration` | `SYMBOLIC("use_trait:{name}")` |
| `namespace_use_declaration` | `php_decl.lower_php_namespace_use_declaration` | No-op |
| `enum_case` | `php_decl.lower_php_enum_case` | `STORE_FIELD` on `"self"` |
| `global_declaration` | `php_decl.lower_php_global_declaration` | `LOAD_VAR` + `STORE_VAR` per variable |

## Language-Specific Lowering Methods

### `php_expr.lower_php_variable(ctx, node) -> str`
Handles PHP's `$`-prefixed variable names (`variable_name` nodes). Emits `LOAD_VAR` with the full `$`-prefixed text as the variable name. Unlike most languages that strip sigils, PHP variables retain their `$` prefix throughout IR.

### `php_expr.lower_php_encapsed_string(ctx, node) -> str`
Handles double-quoted strings with interpolation. If no interpolation variables are present, delegates to `lower_const_literal`. Otherwise decomposes into `CONST` fragments, `LOAD_VAR` for embedded variables, and `BINOP +` for concatenation.

### `php_expr.lower_php_heredoc(ctx, node) -> str`
Handles heredoc strings (`<<<EOT ... EOT`). Finds the `heredoc_body` child and checks for interpolation. If present, decomposes like encapsed strings; otherwise uses `lower_const_literal`.

### `php_expr.lower_php_func_call(ctx, node) -> str`
Handles `function_call_expression`. Extracts function and arguments fields. If the function node is of type `name` or `qualified_name`, emits `CALL_FUNCTION` with the plain name. Otherwise emits `CALL_UNKNOWN` with a dynamically-lowered target register. Uses `extract_call_args_unwrap` to handle PHP's `argument` wrapper nodes.

### `php_expr.lower_php_method_call(ctx, node) -> str`
Handles `member_call_expression` (`$obj->method(args)`). Extracts `object`, `name`, and `arguments` fields. Emits `CALL_METHOD` with `[obj_reg, method_name, ...arg_regs]`.

### `php_expr.lower_php_member_access(ctx, node) -> str`
Handles `member_access_expression` (`$obj->field`). Emits `LOAD_FIELD` with object register and field name.

### `php_expr.lower_php_subscript(ctx, node) -> str`
Handles `subscript_expression` (`$arr[$idx]`). Extracts the first two named children as object and index, emits `LOAD_INDEX`.

### `php_expr.lower_php_assignment_expr(ctx, node) -> str`
Handles `assignment_expression`. Lowers the right-hand side, then delegates to `php_expr.lower_php_store_target`. Returns the value register (assignments are expressions in PHP).

### `php_expr.lower_php_augmented_assignment_expr(ctx, node) -> str`
Handles `augmented_assignment_expression` (`$x += 1`). Strips `=` from the operator, emits `BINOP` then `php_expr.lower_php_store_target`. Returns the result register.

### `php_expr.lower_php_store_target(ctx, target, val_reg, parent_node)`
Handles PHP-specific target types for store operations:
- `variable_name` / `name` -> `STORE_VAR`
- `member_access_expression` -> `STORE_FIELD` (extracts `object` and `name` fields)
- `subscript_expression` -> `STORE_INDEX`
- Fallback -> `STORE_VAR` with raw text

### `php_cf.lower_php_return(ctx, node)`
Handles `return_statement`. Filters out the `return` keyword token, lowers the expression child. If no return value, emits `CONST "None"` (the `default_return_value`). Then emits `RETURN`.

### `php_cf.lower_php_echo(ctx, node)`
Handles `echo_statement`. Lowers all expression children and emits `CALL_FUNCTION("echo", ...arg_regs)`.

### `php_cf.lower_php_if(ctx, node)`
Handles `if_statement`. Extracts `condition` and `body` fields. Collects `else_clause` and `else_if_clause` children. Emits `BRANCH_IF` for the condition, lowers the body inside a true-label block, then processes else clauses via the private `_lower_php_else_clause` helper. Each `else_if_clause` creates a nested condition test with its own true/false labels.

### `php_cf.lower_php_foreach(ctx, node)`
Handles `foreach_statement`. Supports both `foreach ($arr as $v)` and `foreach ($arr as $k => $v)`. Desugars to an index-based loop:
1. Initializes an index register to `0`
2. Calls `len(iter_reg)` for the bound
3. On each iteration: `BINOP <`, `BRANCH_IF`, `LOAD_INDEX`, `STORE_VAR` for value (and key if present)
4. Increments index with `BINOP +`

### `php_decl.lower_php_func_def(ctx, node)` / `php_decl.lower_php_method_decl(ctx, node)`
Both handle function/method definitions with nearly identical logic. Extracts `name`, `parameters`, `body`. Emits: `BRANCH` to skip, `LABEL` for func entry, parameter lowering via `php_decl.lower_php_params`, body lowering via `php_cf.lower_php_compound`, implicit `RETURN`, end label, then `CONST`/`DECL_VAR` for the function reference. Method declarations additionally emit a `$this` parameter (via `_emit_this_param`) unless the method has a `static_modifier`.

### `php_decl.lower_php_params(ctx, params_node)`
Iterates parameter children. Handles `simple_parameter`, `variadic_parameter`, and bare `variable_name` nodes. For each, extracts the `name` field and emits `SYMBOLIC("param:{name}")` + `DECL_VAR`. Extracts type hints and seeds register/param/var types.

### `php_decl.lower_php_class(ctx, node)`
Handles `class_declaration`. Extracts parent classes from `base_clause`. Emits `BRANCH` to skip, `LABEL` for class, lowers body via `_lower_php_class_body`, end label, then `CONST`/`DECL_VAR` for the class reference using `make_class_ref`.

### `php_cf.lower_php_try(ctx, node)`
Handles `try_statement`. Extracts `body` field, iterates children for `catch_clause` (with `named_type`/`name`/`qualified_name` for exception type and `variable_name` for variable) and `finally_clause`. Delegates to `lower_try_catch`.

### `php_cf.lower_php_throw(ctx, node)` / `php_expr.lower_php_throw_expr(ctx, node) -> str`
`lower_php_throw` delegates to `lower_raise_or_throw(ctx, node, keyword="throw")`.
`lower_php_throw_expr` does the same but additionally returns a `CONST "None"` register (since `throw` can appear in expression context in PHP 8).

### `php_expr.lower_php_object_creation(ctx, node) -> str`
Handles `new Foo(args)`. Emits `NEW_OBJECT(type_name)` then `CALL_METHOD(obj_reg, "__construct", ...args)`. Returns the object register.

### `php_expr.lower_php_array(ctx, node) -> str`
Handles `array_creation_expression`. Detects whether the array is associative (any `=>` in elements):
- **Associative**: Emits `NEW_OBJECT("array")` + `STORE_INDEX(key, value)` per pair
- **Indexed**: Emits `NEW_ARRAY("array", size)` + `STORE_INDEX(idx, value)` per element

### `php_expr.lower_php_cast(ctx, node) -> str`
Handles `cast_expression` (`(int)$x`). Simply lowers the last named child (the cast operand), ignoring the cast type. Passthrough semantics.

### `php_expr.lower_php_ternary(ctx, node) -> str`
Handles `conditional_expression` (`$a ? $b : $c`). Emits `BRANCH_IF` with true/false labels, stores result in a temporary variable `__ternary_{counter}`, loads it at the merge point. Supports Elvis operator (`$a ?: $c`) where `true_node` may be absent (uses `cond_reg` as true value).

### `php_expr.lower_php_match_expression(ctx, node) -> str`
Handles PHP 8 `match(subject) { ... }`. Iterates `match_conditional_expression` arms, comparing with `BINOP ===` (strict equality). Handles `match_default_expression` as unconditional branch. Stores arm results in `__match_{counter}` temp variable.

### `php_expr.lower_php_arrow_function(ctx, node) -> str`
Handles `fn($x) => expr`. Creates a function body with implicit `RETURN` of the body expression. Returns a function reference constant.

### `php_expr.lower_php_scoped_call(ctx, node) -> str`
Handles `ClassName::method(args)`. Constructs qualified name `{scope}::{method}`, emits `CALL_FUNCTION(qualified_name, ...args)`.

### `php_expr.lower_php_anonymous_function(ctx, node) -> str`
Handles `function($x) use ($y) { body }`. Creates a named function body `__anon_{counter}` with parameter lowering and compound body. Returns a function reference constant. The `use` clause is not explicitly modeled (captured variables are not tracked).

### `php_cf.lower_php_switch(ctx, node)`
Handles `switch_statement`. Lowers selector expression, pushes end label to `break_target_stack`. Iterates `case_statement` and `default_statement` children. Cases emit `BINOP ==` + `BRANCH_IF`; default emits unconditional `BRANCH`.

### `php_cf.lower_php_do(ctx, node)`
Handles `do_statement` (`do { } while ()`). Body-first loop: emits body label, lowers body with loop context (`push_loop`/`pop_loop`), then condition check with `BRANCH_IF` looping back to body on true.

### `php_cf.lower_php_namespace(ctx, node)`
Handles `namespace_definition`. Finds the `compound_statement` child and lowers it. Namespace is purely structural.

### `php_decl.lower_php_interface(ctx, node)` / `php_decl.lower_php_trait(ctx, node)` / `php_decl.lower_php_enum(ctx, node)`
All three follow the same pattern as `php_decl.lower_php_class`: `BRANCH` to skip, `LABEL`, body via `_lower_php_class_body`, end label, class reference `CONST`/`STORE_VAR`.

### `php_decl.lower_php_function_static(ctx, node)`
Handles `function_static_declaration` (`static $x = val;`). Iterates `static_variable_declaration` children, extracts `name`/`value`, emits `STORE_VAR`.

### `php_cf.lower_php_named_label(ctx, node)` / `php_cf.lower_php_goto(ctx, node)`
Handle goto/label. `named_label_statement` emits `LABEL user_{name}`. `goto_statement` emits `BRANCH user_{name}`.

### `php_expr.lower_php_nullsafe_member_access(ctx, node) -> str`
Handles `$obj?->field`. Emits `LOAD_FIELD` identically to regular member access; null-safety is semantic, not structural in IR.

### `php_expr.lower_php_nullsafe_method_call(ctx, node) -> str`
Handles `$obj?->method(args)`. Emits `CALL_METHOD` identically to regular method call; null-safety is semantic.

### `php_expr.lower_php_class_constant_access(ctx, node) -> str` / `php_expr.lower_php_scoped_property_access(ctx, node) -> str`
Both handle `ClassName::CONST` and `ClassName::$prop` respectively. Lower the class as an expression, then emit `LOAD_FIELD` for the constant/property name.

### `php_expr.lower_php_yield(ctx, node) -> str`
Handles `yield_expression`. Lowers all named children as arguments, emits `CALL_FUNCTION("yield", ...args)`.

### `php_expr.lower_php_reference_assignment(ctx, node) -> str`
Handles `$x = &$y`. Ignores reference semantics; lowers right side and stores via `lower_php_store_target`.

### `php_decl.lower_php_property_declaration(ctx, node)`
Handles property declarations inside classes (`public $x = 10;`). Iterates `property_element` children, emits `STORE_FIELD("self", prop_name, val_reg)`. Uninitialized properties get `CONST "None"`.

### `php_decl.lower_php_use_declaration(ctx, node)`
Handles `use SomeTrait;` inside classes. Emits `SYMBOLIC("use_trait:{name}")` per trait.

### `php_decl.lower_php_namespace_use_declaration(ctx, node)`
Handles `use Some\Namespace;`. No-op (pass).

### `php_decl.lower_php_enum_case(ctx, node)`
Handles enum case inside `enum_declaration`. Emits `STORE_FIELD("self", case_name, val_reg)`. If no explicit value, uses the case name string as the value.

### `php_cf.lower_php_compound(ctx, node)`
Handles `compound_statement` (curly-brace blocks). Iterates named children, skipping `{` and `}`, dispatching each to `ctx.lower_stmt`.

### `php_expr.lower_php_dynamic_variable(ctx, node) -> str`
Handles `${x}` -- unwraps to the inner variable_name or expression.

### `php_expr.lower_php_include(ctx, node) -> str`
Handles `include 'file.php'` and `require_once 'file.php'`. Emits `CALL_FUNCTION` with the keyword as the function name.

### `php_expr.lower_php_variadic_unpacking(ctx, node) -> str`
Handles `...$arr`. Emits `CALL_FUNCTION("spread", inner_reg)`.

### `php_decl.lower_php_global_declaration(ctx, node)`
Handles `global $config;`. Emits `LOAD_VAR` + `STORE_VAR` for each `variable_name` child.

## Canonical Literal Handling

| PHP Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based detection) |
| `null` | `common_expr.lower_canonical_none` | `CONST "None"` |

PHP's `true`/`false`/`TRUE`/`FALSE` are all parsed as `boolean` nodes; `lower_canonical_bool` normalizes via `text.strip().lower()` comparison to `"true"`. PHP's `null`/`NULL` is parsed as the `null` node type.

## Example

**PHP source:**
```php
<?php
function add($a, $b) {
    return $a + $b;
}
$result = add(3, 4);
echo $result;
```

**Emitted IR (approximate):**
```
LABEL     __entry__
BRANCH    end_add_1
LABEL     func:add_0
SYMBOLIC  %0  "param:$a"
STORE_VAR $a  %0
SYMBOLIC  %1  "param:$b"
STORE_VAR $b  %1
LOAD_VAR  %2  "$a"
LOAD_VAR  %3  "$b"
BINOP     %4  "+"  %2  %3
RETURN    %4
CONST     %5  "None"
RETURN    %5
LABEL     end_add_1
CONST     %6  "func:add@func:add_0"
STORE_VAR add  %6
CONST     %7  "3"
CONST     %8  "4"
CALL_FUNCTION %9  "add"  %7  %8
STORE_VAR $result  %9
LOAD_VAR  %10  "$result"
CALL_FUNCTION %11  "echo"  %10
```

## Design Notes

1. **Variables retain `$` prefix**: Unlike some frontends that strip language-specific sigils, PHP variables keep their `$` prefix in IR. This is intentional -- it preserves PHP's variable semantics and avoids collision with function/class names.

2. **`lower_php_store_target` as a standalone function**: PHP has its own store target function (`php_expr.lower_php_store_target`) because PHP's assignment target types (`variable_name`, `member_access_expression`, `subscript_expression`) differ from other languages' expected types.

3. **Match uses strict equality (`===`)**: PHP's `match` expression uses strict comparison (`===`), which the frontend preserves in IR (unlike `switch` which uses `==`).

4. **Cast expressions are passthrough**: Type casts (`(int)`, `(string)`, etc.) are lowered as identity -- only the inner expression is evaluated. The type information is discarded.

5. **Reference semantics ignored**: `$x = &$y` is lowered as a plain assignment. Reference tracking would require more complex IR modeling.

6. **Null-safety is semantic**: `$obj?->field` and `$obj?->method()` produce the same IR as their non-nullsafe counterparts. The null-safety check is not represented in the IR.

7. **Echo is a function call**: `echo $x` is lowered as `CALL_FUNCTION("echo", $x)` rather than a special opcode, keeping the IR uniform.

8. **Foreach desugared to index loop**: PHP's `foreach` is lowered to an explicit index-based loop using `len()` and `LOAD_INDEX`, identical to how other languages' foreach/for-in are handled.

9. **Goto/label support**: PHP is one of the few frontends that supports `goto` statements, lowered directly to `BRANCH` and `LABEL` instructions with `user_` prefix.

10. **Object creation uses NEW_OBJECT + CALL_METHOD**: `new Foo(args)` emits `NEW_OBJECT("Foo")` followed by `CALL_METHOD(obj, "__construct", ...args)`, modeling PHP's two-phase construction.

11. **String interpolation decomposition**: Double-quoted strings and heredocs with embedded variables are decomposed into `CONST` + `LOAD_VAR` + `BINOP +` chains, making interpolation explicit in the IR.

12. **Scoping model** -- Uses default `BLOCK_SCOPED = False` (function-scoped). PHP variables are function-scoped, so no `$` mangling occurs. Note that PHP's tree-sitter grammar does not assign a field name to the for-loop initializer, so C-style for init scoping is not applicable.
