# C# Frontend

> `interpreter/frontends/csharp.py` · Extends `BaseFrontend` · ~1455 lines

## Overview

The C# frontend lowers tree-sitter C# ASTs into the RedDragon TAC IR. It handles C#'s rich type system constructs (classes, structs, interfaces, enums), OOP features (constructors, properties with accessors, method declarations), modern C# features (lambdas, switch expressions, pattern matching with `is`, `await`, tuples, conditional access `?.`), and infrastructure constructs (namespaces, `using` statements, `lock`, `checked`, `fixed`). The frontend uses a deferred class-body lowering strategy that hoists methods before field initializers.

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── CSharpFrontend (csharp.py)
```

`CSharpFrontend` inherits common lowering from `BaseFrontend` including `_lower_while`, `_lower_c_style_for`, `_lower_break`, `_lower_continue`, `_lower_expression_statement`, `_lower_try_catch`, `_lower_raise_or_throw`, `_lower_update_expr`, `_lower_paren`, `_lower_binop`, `_lower_unop`, `_lower_const_literal`, `_lower_identifier`, `_lower_block`, `_lower_return`, and all canonical literal helpers.

## Overridden Constants

| Constant | BaseFrontend Default | CSharpFrontend Value |
|---|---|---|
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"member_access_expression"` |
| `ATTR_OBJECT_FIELD` | `"object"` | `"expression"` |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"name"` |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` (same) |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"\n", "using_directive"})` |
| `BLOCK_NODE_TYPES` | `frozenset()` | `frozenset({"block"})` |

Note: `NONE_LITERAL`, `TRUE_LITERAL`, `FALSE_LITERAL`, `DEFAULT_RETURN_VALUE` retain their BaseFrontend defaults.

## Expression Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `real_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `character_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |
| `this_expression` | `_lower_identifier` | `LOAD_VAR "this"` |
| `binary_expression` | `_lower_binop` | `BINOP` |
| `prefix_unary_expression` | `_lower_unop` | `UNOP` |
| `postfix_unary_expression` | `_lower_update_expr` | `BINOP` + `STORE_VAR` |
| `parenthesized_expression` | `_lower_paren` | (unwraps inner expr) |
| `invocation_expression` | `_lower_invocation` | `CALL_FUNCTION`/`CALL_METHOD`/`CALL_UNKNOWN` |
| `object_creation_expression` | `_lower_object_creation` | `CALL_FUNCTION(type_name, ...)` |
| `member_access_expression` | `_lower_member_access` | `LOAD_FIELD` |
| `element_access_expression` | `_lower_element_access` | `LOAD_INDEX` |
| `initializer_expression` | `_lower_initializer_expr` | `NEW_ARRAY("list", size)` + `STORE_INDEX` |
| `assignment_expression` | `_lower_assignment_expr` | `STORE_VAR`/`STORE_FIELD`/`STORE_INDEX` |
| `cast_expression` | `_lower_cast_expr` | (passthrough to inner expr) |
| `conditional_expression` | `_lower_ternary` | `BRANCH_IF` + temp var |
| `interpolated_string_expression` | `_lower_const_literal` | `CONST` (raw text) |
| `type_identifier` | `_lower_identifier` | `LOAD_VAR` |
| `predefined_type` | `_lower_identifier` | `LOAD_VAR` |
| `typeof_expression` | `_lower_typeof` | `CALL_FUNCTION("typeof", type_reg)` |
| `is_expression` | `_lower_is_expr` | `CALL_FUNCTION("is_check", obj, type)` |
| `as_expression` | `_lower_as_expr` | (passthrough to left operand) |
| `lambda_expression` | `_lower_lambda` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `array_creation_expression` | `_lower_array_creation` | `NEW_ARRAY` + optional `STORE_INDEX` |
| `implicit_array_creation_expression` | `_lower_array_creation` | `NEW_ARRAY` + `STORE_INDEX` |
| `await_expression` | `_lower_await_expr` | `CALL_FUNCTION("await", inner)` |
| `switch_expression` | `_lower_switch_expr` | `BINOP ==` + `BRANCH_IF` chain |
| `conditional_access_expression` | `_lower_conditional_access` | `LOAD_FIELD` (null-safety semantic) |
| `member_binding_expression` | `_lower_member_binding` | `SYMBOLIC("member_binding:{name}")` |
| `tuple_expression` | `_lower_tuple_expr` | `NEW_ARRAY("tuple", size)` + `STORE_INDEX` |
| `is_pattern_expression` | `_lower_is_pattern_expr` | `CALL_FUNCTION("is_check", obj, type)` |

## Statement Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `_lower_expression_statement` | (unwraps inner expr) |
| `local_declaration_statement` | `_lower_local_decl_stmt` | `STORE_VAR` per declarator |
| `return_statement` | `_lower_return` | `RETURN` |
| `if_statement` | `_lower_if` | `BRANCH_IF` + labels |
| `while_statement` | `_lower_while` | (inherited) `BRANCH_IF` loop |
| `for_statement` | `_lower_c_style_for` | (inherited) C-style for loop |
| `foreach_statement` | `_lower_foreach` | Index-based loop with `LOAD_INDEX` |
| `method_declaration` | `_lower_method_decl` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `class_declaration` | `_lower_class_def` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `struct_declaration` | `_lower_class_def` | Same as class_declaration |
| `interface_declaration` | `_lower_interface_decl` | `NEW_OBJECT("interface:{name}")` + `STORE_INDEX` |
| `enum_declaration` | `_lower_enum_decl` | `NEW_OBJECT("enum:{name}")` + `STORE_INDEX` |
| `namespace_declaration` | `_lower_namespace` | (lowers body block) |
| `throw_statement` | `_lower_throw` | `THROW` |
| `block` | `_lower_block` | (inherited block lowering) |
| `global_statement` | `_lower_global_statement` | (unwraps inner statement) |
| `compilation_unit` | `_lower_block` | (inherited block lowering) |
| `declaration_list` | `_lower_block` | (inherited block lowering) |
| `using_directive` | `lambda _: None` | No-op |
| `do_statement` | `_lower_do_while` | Body-first loop + `BRANCH_IF` |
| `switch_statement` | `_lower_switch` | `BINOP ==` + `BRANCH_IF` chain |
| `try_statement` | `_lower_try` | `LABEL`/`SYMBOLIC`/`BRANCH` (try/catch/finally) |
| `constructor_declaration` | `_lower_constructor_decl` | Function def named `__init__` |
| `field_declaration` | `_lower_field_decl` | `STORE_VAR` per declarator |
| `property_declaration` | `_lower_property_decl` | `STORE_FIELD` on `this` |
| `break_statement` | `_lower_break` | `BRANCH` to break target |
| `continue_statement` | `_lower_continue` | `BRANCH` to continue label |
| `lock_statement` | `_lower_lock_stmt` | (lowers lock expr + body block) |
| `using_statement` | `_lower_using_stmt` | (lowers resource decl + body block) |
| `checked_statement` | `_lower_checked_stmt` | (lowers body block) |
| `fixed_statement` | `_lower_fixed_stmt` | (lowers body block) |
| `event_field_declaration` | `_lower_event_field_decl` | `STORE_VAR` via variable_declaration |
| `event_declaration` | `_lower_event_decl` | `CONST("event:{name}")` + `STORE_VAR` |
| `local_function_statement` | `_lower_local_function_stmt` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `yield_statement` | `_lower_yield_stmt` | `CALL_FUNCTION("yield", val)` or `CALL_FUNCTION("yield_break")` |

## Language-Specific Lowering Methods

### `_lower_global_statement(node)`
Unwraps `global_statement` nodes (top-level C# 9 statements). Iterates named children and dispatches each to `_lower_stmt`.

### `_lower_local_decl_stmt(node)` / `_lower_variable_declaration(node)` / `_lower_csharp_declarator(node)`
Three-level chain for local variable declarations:
1. `_lower_local_decl_stmt` finds `variable_declaration` children
2. `_lower_variable_declaration` finds `variable_declarator` children
3. `_lower_csharp_declarator` extracts the identifier (first named child before `=`) and the value (first named child after `=`). If no initializer, stores `CONST "None"`.

### `_lower_invocation(node) -> str`
Handles `invocation_expression`. Extracts `function` and `arguments` fields:
- If `function` is a `member_access_expression`: extracts `expression` (object) and `name` fields, emits `CALL_METHOD`
- If `function` is an `identifier`: emits `CALL_FUNCTION`
- Otherwise: emits `CALL_UNKNOWN` with dynamically-lowered target

### `_lower_object_creation(node) -> str`
Handles `new ClassName(args)`. Extracts `type` and `arguments` fields. Emits `CALL_FUNCTION(type_name, ...args)`.

### `_lower_member_access(node) -> str`
Handles `obj.Field`. Extracts `expression` (object) and `name` fields. Emits `LOAD_FIELD`.

### `_lower_element_access(node) -> str`
Handles `arr[idx]`. Extracts `expression` (object) and `subscript` (or `bracketed_argument_list` fallback). Delegates index extraction to `_extract_bracket_index`. Emits `LOAD_INDEX`.

### `_lower_extract_bracket_index(bracket_node) -> str`
Unwraps C#'s `bracketed_argument_list -> argument -> expression` chain to extract the actual index expression. Falls back to `SYMBOLIC("unknown_index")` if no argument found.

### `_lower_initializer_expr(node) -> str`
Handles `initializer_expression` (`{a, b, c}`). Creates `NEW_ARRAY("list", size)` and populates with `STORE_INDEX` per element.

### `_lower_assignment_expr(node) -> str`
Handles `assignment_expression`. Lowers RHS, delegates to `_lower_store_target`. Returns value register.

### `_lower_cast_expr(node) -> str`
Handles `cast_expression` (`(Type)expr`). Tries `value` field first, then falls back to last named child. Passthrough semantics (type info discarded).

### `_lower_ternary(node) -> str`
Handles `conditional_expression` (`a ? b : c`). Extracts `condition`, `consequence`, `alternative`. Emits `BRANCH_IF` with temp variable `__ternary_{counter}` to merge result.

### `_lower_typeof(node) -> str`
Handles `typeof(Type)`. Emits `CONST type_name` then `CALL_FUNCTION("typeof", type_reg)`.

### `_lower_is_expr(node) -> str`
Handles `x is Type`. Emits `CONST type_name` then `CALL_FUNCTION("is_check", obj_reg, type_reg)`.

### `_lower_as_expr(node) -> str`
Handles `x as Type`. Passthrough: lowers the left operand, ignoring the target type.

### `_lower_lambda(node) -> str`
Handles C# lambdas (`(params) => expr` or `(params) => { body }`). Creates a function body block:
- If body is a `block`: lowers block + implicit return
- If body is an expression: evaluates and emits `RETURN`
Returns a function reference constant `func:{label}`.

### `_lower_array_creation(node) -> str`
Handles `array_creation_expression` and `implicit_array_creation_expression`.
- **With initializer**: `NEW_ARRAY("array", size)` + `STORE_INDEX` per element
- **Without initializer** (sized): `NEW_ARRAY("array", size_reg)` where size comes from rank specifier

### `_lower_foreach(node)`
Handles `foreach (Type var in collection)`. Extracts `left` (variable), `right` (collection), `body`. Desugars to index-based loop identical to PHP's foreach pattern: `len()`, `LOAD_INDEX`, increment.

### `_lower_method_decl(node)`
Handles `method_declaration`. Extracts `name`, `parameters`, `body`. Emits function definition pattern with `_lower_csharp_params` for parameters.

### `_lower_csharp_params(params_node)`
Iterates `parameter` children, extracts `name` field, emits `SYMBOLIC("param:{name}")` + `STORE_VAR`.

### `_lower_constructor_decl(node)`
Handles `constructor_declaration`. Identical to `_lower_method_decl` except the function name is hardcoded to `"__init__"`.

### `_lower_class_def(node)`
Handles both `class_declaration` and `struct_declaration`. Uses deferred lowering via `_lower_class_body`:
1. Emits `BRANCH` to skip, `LABEL` for class entry
2. Collects class body children (methods first, then rest)
3. Emits end label and class reference
4. Lowers deferred children at top level via `_lower_deferred_class_child`

This ordering ensures function references are registered before field initializers that may call them.

### `_lower_class_body(node) -> list`
Partitions class body children into methods (`method_declaration`, `constructor_declaration`) and rest. Returns methods + rest for deferred lowering. Skips `modifier`, `attribute_list`, `{`, `}`.

### `_lower_deferred_class_child(child)`
Dispatches deferred class children: `method_declaration` -> `_lower_method_decl`, `constructor_declaration` -> `_lower_constructor_decl`, `field_declaration` -> `_lower_field_decl`, `property_declaration` -> `_lower_property_decl`, else -> `_lower_stmt`.

### `_lower_field_decl(node)`
Handles `field_declaration`. Finds `variable_declaration` child and delegates to `_lower_variable_declaration`.

### `_lower_property_decl(node)`
Handles `property_declaration`. Extracts property name, loads `this`, finds initializer (after `=` token). Emits `STORE_FIELD(this_reg, prop_name, val_reg)`. Also lowers accessor bodies (`get { ... }` / `set { ... }`) if present.

### `_lower_interface_decl(node)`
Handles `interface_declaration`. Creates `NEW_OBJECT("interface:{name}")` and populates with `STORE_INDEX` per named member (member name as key, index as value).

### `_lower_enum_decl(node)`
Handles `enum_declaration`. Creates `NEW_OBJECT("enum:{name}")` and populates with `STORE_INDEX` per `enum_member_declaration` (member name as key, ordinal as value).

### `_lower_namespace(node)`
Handles `namespace_declaration`. Simply lowers the `body` field as a block.

### `_lower_if(node)`
Handles `if_statement`. Extracts `condition` and `consequence` fields. Falls back to first `block` child if `consequence` field is absent. Handles `alternative` by iterating its children (skipping `else` keyword) and dispatching to `_lower_stmt`.

### `_lower_throw(node)`
Delegates to `_lower_raise_or_throw(node, keyword="throw")`.

### `_lower_do_while(node)`
Handles `do_statement`. Body-first loop: lowers body with loop context, then condition check with `BRANCH_IF`.

### `_lower_switch(node)`
Handles `switch_statement`. Extracts `value` (subject) and `body` (switch_body) fields. Iterates `switch_section` children. Each section with `constant_pattern` emits `BINOP ==` + `BRANCH_IF`; sections without pattern (default) emit unconditional `BRANCH`. Pushes `end_label` to `_break_target_stack`.

### `_lower_try(node)`
Handles `try_statement`. Extracts body, iterates children for `catch_clause` (with `catch_declaration` containing type/name identifiers) and `finally_clause`. Delegates to `_lower_try_catch`.

### `_lower_await_expr(node) -> str`
Handles `await_expression`. Lowers inner expression, emits `CALL_FUNCTION("await", inner_reg)`.

### `_lower_switch_expr(node) -> str`
Handles C# 8 `switch expression`. Iterates `switch_expression_arm` children. Each arm's pattern is compared with `BINOP ==`; discard pattern (`_`) treated as default. Stores results in temp variable `__switch_expr_{counter}`.

### `_lower_yield_stmt(node)`
Handles `yield_statement`. If `yield break`: emits `CALL_FUNCTION("yield_break")`. If `yield return expr`: emits `CALL_FUNCTION("yield", val_reg)`.

### `_lower_lock_stmt(node)` / `_lower_using_stmt(node)` / `_lower_checked_stmt(node)` / `_lower_fixed_stmt(node)`
Infrastructure statements. Each lowers the lock expression or resource declaration and then the body block. `checked` and `fixed` simply lower the body block.

### `_lower_event_field_decl(node)` / `_lower_event_decl(node)`
Event declarations. `event_field_declaration` delegates to `_lower_variable_declaration`. `event_declaration` emits `CONST("event:{name}")` + `STORE_VAR`.

### `_lower_conditional_access(node) -> str`
Handles `obj?.Field`. Lowers object, extracts field from `member_binding_expression` child. Emits `LOAD_FIELD`. Null-safety is semantic only.

### `_lower_member_binding(node) -> str`
Standalone fallback for `.Field` part of conditional access. Emits `SYMBOLIC("member_binding:{name}")`.

### `_lower_local_function_stmt(node)`
Handles local functions inside method bodies. Identical pattern to `_lower_method_decl` but searches for `identifier` and `parameter_list` children by type as fallback.

### `_lower_tuple_expr(node) -> str`
Handles `(a, b, c)` tuples. Iterates `argument` children, unwraps each to inner expression. Creates `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element.

### `_lower_is_pattern_expr(node) -> str`
Handles `x is int y` pattern matching. Emits `CALL_FUNCTION("is_check", obj_reg, type_reg)`.

### `_lower_store_target(target, val_reg, parent_node)`
**Overrides** `BaseFrontend._lower_store_target`. Handles:
- `identifier` -> `STORE_VAR`
- `member_access_expression` -> `STORE_FIELD` (extracts `expression` and `name` fields)
- `element_access_expression` -> `STORE_INDEX` (extracts `expression` and `subscript`/`bracketed_argument_list`)
- Fallback -> `STORE_VAR` with raw text

## Canonical Literal Handling

| C# Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based detection) |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |

C#'s `true`/`false` are parsed as `boolean_literal` nodes; `_lower_canonical_bool` normalizes via case-insensitive comparison. C#'s `null` is parsed as `null_literal`.

## Example

**C# source:**
```csharp
namespace App {
    class Calculator {
        public int Add(int a, int b) {
            return a + b;
        }
    }
}
```

**Emitted IR (approximate):**
```
LABEL     __entry__
BRANCH    end_class:Calculator_1
LABEL     class:Calculator_0
LABEL     end_class:Calculator_1
CONST     %0  "class:Calculator@class:Calculator_0"
STORE_VAR Calculator  %0
BRANCH    end_Add_3
LABEL     func:Add_2
SYMBOLIC  %1  "param:a"
STORE_VAR a   %1
SYMBOLIC  %2  "param:b"
STORE_VAR b   %2
LOAD_VAR  %3  "a"
LOAD_VAR  %4  "b"
BINOP     %5  "+"  %3  %4
RETURN    %5
CONST     %6  "None"
RETURN    %6
LABEL     end_Add_3
CONST     %7  "func:Add@func:Add_2"
STORE_VAR Add  %7
```

Note: Methods are lowered *after* the class label/ref is emitted due to the deferred lowering strategy.

## Design Notes

1. **Deferred class body lowering**: `_lower_class_def` collects class body members and lowers them at top level *after* the class reference is stored. Methods are lowered before fields/properties to ensure function references are available for initializers.

2. **`ATTR_OBJECT_FIELD = "expression"`**: C#'s tree-sitter grammar uses `expression` (not `object`) as the field name for the object in `member_access_expression`. This differs from PHP and most other frontends.

3. **Constructors mapped to `__init__`**: C# constructors are lowered as functions named `__init__`, matching Python's convention for interoperability in cross-language analysis.

4. **`using_directive` is noise**: Import directives are filtered as no-ops in the statement dispatch table.

5. **Properties emit `STORE_FIELD` on `this`**: Property declarations generate `LOAD_VAR "this"` followed by `STORE_FIELD`. Auto-properties without initializers get `CONST "None"`. Accessor bodies (`get { ... }` / `set { ... }`) are lowered as statements within the property.

6. **Switch expression vs switch statement**: The frontend supports both C#'s traditional `switch` statement (lowered as if/else chain with break targets) and C# 8's `switch` expression (value-producing, with discard `_` as default pattern).

7. **Structs treated as classes**: `struct_declaration` maps to the same `_lower_class_def` handler as `class_declaration`. No value-type semantics are modeled.

8. **Events as constants**: Event declarations emit `CONST("event:{name}")` + `STORE_VAR`. No delegate/subscription semantics are modeled.

9. **`as` cast is passthrough**: `x as Type` returns the left operand's register directly; the type check is not modeled. For safety-aware analysis, `is` expressions emit proper `CALL_FUNCTION("is_check", ...)`.
