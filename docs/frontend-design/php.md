# PHP Frontend

> `interpreter/frontends/php.py` · Extends `BaseFrontend` · ~1405 lines

## Overview

The PHP frontend lowers tree-sitter PHP ASTs into the RedDragon three-address-code (TAC) IR. PHP's sigil-prefixed variables (`$var`), `->` member access, `::` static access, and extensive OOP constructs (classes, interfaces, traits, enums) all receive dedicated lowering methods. The frontend handles PHP-specific idioms including `echo`, `foreach` with key-value pairs, arrow functions (`fn() =>`), anonymous functions (closures), match expressions, heredoc/nowdoc strings, goto/labels, and nullsafe member access (`?->`).

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── PhpFrontend (php.py)
```

`PhpFrontend` inherits all common lowering infrastructure from `BaseFrontend` (register allocation, label generation, `_emit`, `_lower_block`, `_lower_while`, `_lower_c_style_for`, `_lower_break`, `_lower_continue`, `_lower_expression_statement`, `_lower_try_catch`, `_lower_raise_or_throw`, `_lower_update_expr`, `_lower_paren`, `_lower_binop`, `_lower_unop`, `_lower_const_literal`, `_lower_identifier`, canonical literal helpers).

## Overridden Constants

| Constant | BaseFrontend Default | PhpFrontend Value |
|---|---|---|
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"member_access_expression"` |
| `ATTR_OBJECT_FIELD` | `"object"` | `"object"` (same) |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"name"` |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` (same) |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"php_tag", "text_interpolation", "php_end_tag", "\n"})` |

Note: `NONE_LITERAL`, `TRUE_LITERAL`, `FALSE_LITERAL`, `DEFAULT_RETURN_VALUE` all retain their BaseFrontend defaults (`"None"`, `"True"`, `"False"`, `"None"` respectively), since canonical lowering methods are used.

## Expression Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `variable_name` | `_lower_php_variable` | `LOAD_VAR` with `$`-prefixed name |
| `name` | `_lower_identifier` | `LOAD_VAR` |
| `integer` | `_lower_const_literal` | `CONST` (raw text) |
| `float` | `_lower_const_literal` | `CONST` (raw text) |
| `string` | `_lower_const_literal` | `CONST` (raw text) |
| `encapsed_string` | `_lower_const_literal` | `CONST` (raw text) |
| `boolean` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null` | `_lower_canonical_none` | `CONST "None"` |
| `binary_expression` | `_lower_binop` | `BINOP` |
| `unary_op_expression` | `_lower_unop` | `UNOP` |
| `update_expression` | `_lower_update_expr` | `BINOP` + `STORE_VAR` (i++/i--) |
| `function_call_expression` | `_lower_php_func_call` | `CALL_FUNCTION` or `CALL_UNKNOWN` |
| `member_call_expression` | `_lower_php_method_call` | `CALL_METHOD` |
| `member_access_expression` | `_lower_php_member_access` | `LOAD_FIELD` |
| `subscript_expression` | `_lower_php_subscript` | `LOAD_INDEX` |
| `parenthesized_expression` | `_lower_paren` | (unwraps inner expr) |
| `array_creation_expression` | `_lower_php_array` | `NEW_ARRAY`/`NEW_OBJECT` + `STORE_INDEX` |
| `assignment_expression` | `_lower_php_assignment_expr` | `STORE_VAR`/`STORE_FIELD`/`STORE_INDEX` |
| `augmented_assignment_expression` | `_lower_php_augmented_assignment_expr` | `BINOP` + `STORE_*` |
| `cast_expression` | `_lower_php_cast` | (passthrough to inner expr) |
| `conditional_expression` | `_lower_php_ternary` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` |
| `throw_expression` | `_lower_php_throw_expr` | `THROW` + `CONST "None"` |
| `object_creation_expression` | `_lower_php_object_creation` | `CALL_FUNCTION` (type name) |
| `match_expression` | `_lower_php_match_expression` | `BINOP ===` + `BRANCH_IF` chain |
| `arrow_function` | `_lower_php_arrow_function` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `scoped_call_expression` | `_lower_php_scoped_call` | `CALL_FUNCTION` (qualified `Class::method`) |
| `anonymous_function` | `_lower_php_anonymous_function` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `nullsafe_member_access_expression` | `_lower_php_nullsafe_member_access` | `LOAD_FIELD` (null-safety is semantic) |
| `class_constant_access_expression` | `_lower_php_class_constant_access` | `LOAD_FIELD` on class |
| `scoped_property_access_expression` | `_lower_php_scoped_property_access` | `LOAD_FIELD` on class |
| `yield_expression` | `_lower_php_yield` | `CALL_FUNCTION("yield", ...)` |
| `reference_assignment_expression` | `_lower_php_reference_assignment` | `STORE_VAR` (ignores reference semantics) |
| `heredoc` | `_lower_const_literal` | `CONST` (raw text) |
| `nowdoc` | `_lower_const_literal` | `CONST` (raw text) |

## Statement Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `_lower_expression_statement` | (unwraps inner expr) |
| `return_statement` | `_lower_php_return` | `RETURN` |
| `echo_statement` | `_lower_php_echo` | `CALL_FUNCTION("echo", ...)` |
| `if_statement` | `_lower_php_if` | `BRANCH_IF` + labels |
| `while_statement` | `_lower_while` | (inherited) `BRANCH_IF` loop |
| `for_statement` | `_lower_c_style_for` | (inherited) C-style for loop |
| `foreach_statement` | `_lower_php_foreach` | Index-based loop with `LOAD_INDEX` |
| `function_definition` | `_lower_php_func_def` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `method_declaration` | `_lower_php_method_decl` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `class_declaration` | `_lower_php_class` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `throw_expression` | `_lower_php_throw` | `THROW` |
| `compound_statement` | `_lower_php_compound` | (iterates children, skips `{`/`}`) |
| `program` | `_lower_block` | (inherited block lowering) |
| `break_statement` | `_lower_break` | `BRANCH` to break target |
| `continue_statement` | `_lower_continue` | `BRANCH` to continue label |
| `try_statement` | `_lower_try` | `LABEL`/`SYMBOLIC`/`BRANCH` (try/catch/finally) |
| `switch_statement` | `_lower_php_switch` | `BINOP ==` + `BRANCH_IF` chain |
| `do_statement` | `_lower_php_do` | Body-first loop + `BRANCH_IF` |
| `namespace_definition` | `_lower_php_namespace` | (lowers body compound_statement) |
| `interface_declaration` | `_lower_php_interface` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `trait_declaration` | `_lower_php_trait` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `function_static_declaration` | `_lower_php_function_static` | `STORE_VAR` per static variable |
| `enum_declaration` | `_lower_php_enum` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `named_label_statement` | `_lower_php_named_label` | `LABEL user_{name}` |
| `goto_statement` | `_lower_php_goto` | `BRANCH user_{name}` |
| `property_declaration` | `_lower_php_property_declaration` | `STORE_FIELD` on `"self"` |
| `use_declaration` | `_lower_php_use_declaration` | `SYMBOLIC("use_trait:{name}")` |
| `namespace_use_declaration` | `_lower_php_namespace_use_declaration` | No-op |
| `enum_case` | `_lower_php_enum_case` | `STORE_FIELD` on `"self"` |

## Language-Specific Lowering Methods

### `_lower_php_variable(node) -> str`
Handles PHP's `$`-prefixed variable names (`variable_name` nodes). Emits `LOAD_VAR` with the full `$`-prefixed text as the variable name. Unlike most languages that strip sigils, PHP variables retain their `$` prefix throughout IR.

### `_lower_php_func_call(node) -> str`
Handles `function_call_expression`. Extracts `function` and `arguments` fields. If the function node is of type `name` or `qualified_name`, emits `CALL_FUNCTION` with the plain name. Otherwise emits `CALL_UNKNOWN` with a dynamically-lowered target register. Uses `_extract_call_args_unwrap` to handle PHP's `argument` wrapper nodes.

### `_lower_php_method_call(node) -> str`
Handles `member_call_expression` (`$obj->method(args)`). Extracts `object`, `name`, and `arguments` fields. Emits `CALL_METHOD` with `[obj_reg, method_name, ...arg_regs]`.

### `_lower_php_member_access(node) -> str`
Handles `member_access_expression` (`$obj->field`). Emits `LOAD_FIELD` with object register and field name.

### `_lower_php_subscript(node) -> str`
Handles `subscript_expression` (`$arr[$idx]`). Extracts the first two named children as object and index, emits `LOAD_INDEX`.

### `_lower_php_assignment_expr(node) -> str`
Handles `assignment_expression`. Lowers the right-hand side, then delegates to `_lower_store_target`. Returns the value register (assignments are expressions in PHP).

### `_lower_php_augmented_assignment_expr(node) -> str`
Handles `augmented_assignment_expression` (`$x += 1`). Strips `=` from the operator, emits `BINOP` then `_lower_store_target`. Returns the result register.

### `_lower_php_return(node)`
Handles `return_statement`. Filters out the `return` keyword token, lowers the expression child. If no return value, emits `CONST "None"` (the `DEFAULT_RETURN_VALUE`). Then emits `RETURN`.

### `_lower_php_echo(node)`
Handles `echo_statement`. Lowers all expression children and emits `CALL_FUNCTION("echo", ...arg_regs)`.

### `_lower_php_if(node)`
Handles `if_statement`. Extracts `condition` and `body` fields. Collects `else_clause` and `else_if_clause` children. Emits `BRANCH_IF` for the condition, lowers the body inside a true-label block, then processes else clauses via `_lower_php_else_clause`. Each `else_if_clause` creates a nested condition test with its own true/false labels.

### `_lower_php_foreach(node)`
Handles `foreach_statement`. Supports both `foreach ($arr as $v)` and `foreach ($arr as $k => $v)`. Desugars to an index-based loop:
1. Initializes an index register to `0`
2. Calls `len(iter_reg)` for the bound
3. On each iteration: `BINOP <`, `BRANCH_IF`, `LOAD_INDEX`, `STORE_VAR` for value (and key if present)
4. Increments index with `BINOP +`

### `_lower_php_func_def(node)` / `_lower_php_method_decl(node)`
Both handle function/method definitions with nearly identical logic. Extracts `name`, `parameters`, `body`. Emits: `BRANCH` to skip, `LABEL` for func entry, parameter lowering via `_lower_php_params`, body lowering via `_lower_php_compound`, implicit `RETURN`, end label, then `CONST`/`STORE_VAR` for the function reference.

### `_lower_php_params(params_node)`
Iterates parameter children. Handles `simple_parameter`, `variadic_parameter`, and bare `variable_name` nodes. For each, extracts the `name` field and emits `SYMBOLIC("param:{name}")` + `STORE_VAR`.

### `_lower_php_class(node)`
Handles `class_declaration`. Emits `BRANCH` to skip, `LABEL` for class, lowers body via `_lower_php_class_body`, end label, then `CONST`/`STORE_VAR` for the class reference using `constants.CLASS_REF_TEMPLATE`.

### `_lower_php_class_body(node)`
Iterates `declaration_list` children. Dispatches `method_declaration` to `_lower_php_method_decl`, `property_declaration` to `_lower_php_property_declaration`, and other named children (excluding visibility/modifier nodes) to `_lower_stmt`.

### `_lower_store_target(target, val_reg, parent_node)`
**Overrides** `BaseFrontend._lower_store_target`. Handles PHP-specific target types:
- `variable_name` / `name` -> `STORE_VAR`
- `member_access_expression` -> `STORE_FIELD` (extracts `object` and `name` fields)
- `subscript_expression` -> `STORE_INDEX`
- Fallback -> `STORE_VAR` with raw text

### `_lower_try(node)`
Handles `try_statement`. Extracts `body` field, iterates children for `catch_clause` (with `named_type`/`name`/`qualified_name` for exception type and `variable_name` for variable) and `finally_clause`. Delegates to `_lower_try_catch`.

### `_lower_php_throw(node)` / `_lower_php_throw_expr(node) -> str`
`_lower_php_throw` delegates to `_lower_raise_or_throw(node, keyword="throw")`.
`_lower_php_throw_expr` does the same but additionally returns a `CONST "None"` register (since `throw` can appear in expression context in PHP 8).

### `_lower_php_object_creation(node) -> str`
Handles `new ClassName(args)`. Extracts the class name from `name` field and arguments, emits `CALL_FUNCTION(type_name, ...args)`.

### `_lower_php_array(node) -> str`
Handles `array_creation_expression`. Detects whether the array is associative (any `=>` in elements):
- **Associative**: Emits `NEW_OBJECT("array")` + `STORE_INDEX(key, value)` per pair
- **Indexed**: Emits `NEW_ARRAY("array", size)` + `STORE_INDEX(idx, value)` per element

### `_lower_php_cast(node) -> str`
Handles `cast_expression` (`(int)$x`). Simply lowers the last named child (the cast operand), ignoring the cast type. Passthrough semantics.

### `_lower_php_ternary(node) -> str`
Handles `conditional_expression` (`$a ? $b : $c`). Emits `BRANCH_IF` with true/false labels, stores result in a temporary variable `__ternary_{counter}`, loads it at the merge point. Supports Elvis operator (`$a ?: $c`) where `true_node` may be absent (uses `cond_reg` as true value).

### `_lower_php_match_expression(node) -> str`
Handles PHP 8 `match(subject) { ... }`. Iterates `match_conditional_expression` arms, comparing with `BINOP ===` (strict equality). Handles `match_default_expression` as unconditional branch. Stores arm results in `__match_{counter}` temp variable.

### `_lower_php_arrow_function(node) -> str`
Handles `fn($x) => expr`. Creates a function body with implicit `RETURN` of the body expression. Returns a function reference constant.

### `_lower_php_scoped_call(node) -> str`
Handles `ClassName::method(args)`. Constructs qualified name `{scope}::{method}`, emits `CALL_FUNCTION(qualified_name, ...args)`.

### `_lower_php_switch(node)`
Handles `switch_statement`. Lowers selector expression, pushes end label to `_break_target_stack`. Iterates `case_statement` and `default_statement` children. Cases emit `BINOP ==` + `BRANCH_IF`; default emits unconditional `BRANCH`.

### `_lower_php_do(node)`
Handles `do_statement` (`do { } while ()`). Body-first loop: emits body label, lowers body with loop context (`_push_loop`/`_pop_loop`), then condition check with `BRANCH_IF` looping back to body on true.

### `_lower_php_namespace(node)`
Handles `namespace_definition`. Finds the `compound_statement` child and lowers it. Namespace is purely structural.

### `_lower_php_interface(node)` / `_lower_php_trait(node)` / `_lower_php_enum(node)`
All three follow the same pattern as `_lower_php_class`: `BRANCH` to skip, `LABEL`, body via `_lower_php_class_body`, end label, class reference `CONST`/`STORE_VAR`.

### `_lower_php_function_static(node)`
Handles `function_static_declaration` (`static $x = val;`). Iterates `static_variable_declaration` children, extracts `name`/`value`, emits `STORE_VAR`.

### `_lower_php_named_label(node)` / `_lower_php_goto(node)`
Handle goto/label. `named_label_statement` emits `LABEL user_{name}`. `goto_statement` emits `BRANCH user_{name}`.

### `_lower_php_anonymous_function(node) -> str`
Handles `function($x) use ($y) { body }`. Creates a named function body `__anon_{counter}` with parameter lowering and compound body. Returns a function reference constant. The `use` clause is not explicitly modeled (captured variables are not tracked).

### `_lower_php_nullsafe_member_access(node) -> str`
Handles `$obj?->field`. Emits `LOAD_FIELD` identically to regular member access; null-safety is semantic, not structural in IR.

### `_lower_php_class_constant_access(node) -> str` / `_lower_php_scoped_property_access(node) -> str`
Both handle `ClassName::CONST` and `ClassName::$prop` respectively. Lower the class as an expression, then emit `LOAD_FIELD` for the constant/property name.

### `_lower_php_yield(node) -> str`
Handles `yield_expression`. Lowers all named children as arguments, emits `CALL_FUNCTION("yield", ...args)`.

### `_lower_php_reference_assignment(node) -> str`
Handles `$x = &$y`. Ignores reference semantics; lowers right side and stores via `_lower_store_target`.

### `_lower_php_property_declaration(node)`
Handles property declarations inside classes (`public $x = 10;`). Iterates `property_element` children, emits `STORE_FIELD("self", prop_name, val_reg)`. Uninitialized properties get `CONST "None"`.

### `_lower_php_use_declaration(node)`
Handles `use SomeTrait;` inside classes. Emits `SYMBOLIC("use_trait:{name}")` per trait.

### `_lower_php_namespace_use_declaration(node)`
Handles `use Some\Namespace;`. No-op (pass).

### `_lower_php_enum_case(node)`
Handles enum case inside `enum_declaration`. Emits `STORE_FIELD("self", case_name, val_reg)`. If no explicit value, uses the case name string as the value.

### `_lower_php_compound(node)`
Handles `compound_statement` (curly-brace blocks). Iterates named children, skipping `{` and `}`, dispatching each to `_lower_stmt`.

## Canonical Literal Handling

| PHP Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based detection) |
| `null` | `_lower_canonical_none` | `CONST "None"` |

PHP's `true`/`false`/`TRUE`/`FALSE` are all parsed as `boolean` nodes; `_lower_canonical_bool` normalizes via `text.strip().lower()` comparison to `"true"`. PHP's `null`/`NULL` is parsed as the `null` node type.

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

2. **`_lower_store_target` override**: PHP overrides the base `_lower_store_target` because PHP's assignment target types (`variable_name`, `member_access_expression`, `subscript_expression`) differ from the base class's expected types.

3. **Match uses strict equality (`===`)**: PHP's `match` expression uses strict comparison (`===`), which the frontend preserves in IR (unlike `switch` which uses `==`).

4. **Cast expressions are passthrough**: Type casts (`(int)`, `(string)`, etc.) are lowered as identity -- only the inner expression is evaluated. The type information is discarded.

5. **Reference semantics ignored**: `$x = &$y` is lowered as a plain assignment. Reference tracking would require more complex IR modeling.

6. **Null-safety is semantic**: `$obj?->field` produces the same IR as `$obj->field`. The null-safety check is not represented in the IR.

7. **Echo is a function call**: `echo $x` is lowered as `CALL_FUNCTION("echo", $x)` rather than a special opcode, keeping the IR uniform.

8. **Foreach desugared to index loop**: PHP's `foreach` is lowered to an explicit index-based loop using `len()` and `LOAD_INDEX`, identical to how C# and Rust foreach/for-in are handled.

9. **Goto/label support**: PHP is one of the few frontends that supports `goto` statements, lowered directly to `BRANCH` and `LABEL` instructions with `user_` prefix.
