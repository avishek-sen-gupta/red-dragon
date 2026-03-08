# C# Frontend

> `interpreter/frontends/csharp/` · Extends `BaseFrontend` · Directory structure below

## Overview

The C# frontend lowers tree-sitter C# ASTs into the RedDragon TAC IR. It handles C#'s rich type system constructs (classes, structs, records, interfaces, enums), OOP features (constructors, properties with accessors, method declarations), modern C# features (lambdas, switch expressions, pattern matching with `is`, `await`, tuples, conditional access `?.`, LINQ queries, interpolated strings), and infrastructure constructs (namespaces, `using` statements, `lock`, `checked`, `fixed`). The frontend uses a deferred class-body lowering strategy that hoists methods before field initializers.

## Directory Structure

```
interpreter/frontends/csharp/
  frontend.py       CSharpFrontend class (thin orchestrator)
  node_types.py     CSharpNodeType constants for tree-sitter node type strings
  expressions.py    C#-specific expression lowerers (pure functions)
  control_flow.py   C#-specific control flow lowerers (pure functions)
  declarations.py   C#-specific declaration lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (abstract)
  +-- BaseFrontend
        +-- CSharpFrontend  <-- interpreter/frontends/csharp/frontend.py
```

`CSharpFrontend` inherits common lowering from `BaseFrontend` via dispatch to shared pure functions: `common_expr.lower_identifier`, `common_expr.lower_const_literal`, `common_expr.lower_canonical_bool`, `common_expr.lower_canonical_none`, `common_expr.lower_paren`, `common_expr.lower_binop`, `common_expr.lower_unop`, `common_expr.lower_update_expr`, `common_cf.lower_while`, `common_cf.lower_c_style_for`, `common_cf.lower_break`, `common_cf.lower_continue`, `common_assign.lower_expression_statement`, `common_assign.lower_return`.

## GrammarConstants (`_build_constants`)

`CSharpFrontend._build_constants()` returns a `GrammarConstants` instance with these fields:

| Field | Value | Purpose |
|---|---|---|
| `attribute_node_type` | `NT.MEMBER_ACCESS_EXPRESSION` | Tree-sitter node type for member access |
| `attr_object_field` | `"expression"` | Tree-sitter field name for the object in `obj.Field` |
| `attr_attribute_field` | `"name"` | Tree-sitter field name for the field in `obj.Field` |
| `comment_types` | `frozenset({NT.COMMENT})` | Node types treated as comments |
| `noise_types` | `frozenset({NT.NEWLINE, NT.USING_DIRECTIVE})` | Noise: newlines and using directives |
| `block_node_types` | `frozenset({NT.BLOCK, NT.COMPILATION_UNIT, NT.DECLARATION_LIST})` | Block node types |

Note: `none_literal`, `true_literal`, `false_literal`, `default_return_value` retain their BaseFrontend defaults (`"None"`, `"True"`, `"False"`, `"None"`).

## Expression Dispatch Table

The full expression dispatch returned by `_build_expr_dispatch()`:

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `real_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `character_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `verbatim_string_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `constant_pattern` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `declaration_pattern` | `csharp_expr.lower_declaration_pattern` | `CONST type` + `STORE_VAR binding` |
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `this_expression` | `common_expr.lower_identifier` | `LOAD_VAR "this"` |
| `this` | `common_expr.lower_identifier` | `LOAD_VAR "this"` |
| `binary_expression` | `common_expr.lower_binop` | `BINOP` |
| `prefix_unary_expression` | `common_expr.lower_unop` | `UNOP` |
| `postfix_unary_expression` | `common_expr.lower_update_expr` | `BINOP` + `STORE_VAR` |
| `parenthesized_expression` | `common_expr.lower_paren` | (unwraps inner expr) |
| `invocation_expression` | `csharp_expr.lower_invocation` | `CALL_FUNCTION`/`CALL_METHOD`/`CALL_UNKNOWN` |
| `object_creation_expression` | `csharp_expr.lower_object_creation` | `CALL_FUNCTION(type_name, ...)` |
| `member_access_expression` | `csharp_expr.lower_member_access` | `LOAD_FIELD` |
| `element_access_expression` | `csharp_expr.lower_element_access` | `LOAD_INDEX` |
| `initializer_expression` | `csharp_expr.lower_initializer_expr` | `NEW_ARRAY("list", size)` + `STORE_INDEX` |
| `assignment_expression` | `csharp_expr.lower_assignment_expr` | `STORE_VAR`/`STORE_FIELD`/`STORE_INDEX` |
| `cast_expression` | `csharp_expr.lower_cast_expr` | (passthrough to inner expr) |
| `conditional_expression` | `csharp_expr.lower_ternary` | `BRANCH_IF` + temp var |
| `interpolated_string_expression` | `csharp_expr.lower_csharp_interpolated_string` | `CONST` + expr + `BINOP "+"` chain |
| `type_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `predefined_type` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `typeof_expression` | `csharp_expr.lower_typeof` | `CALL_FUNCTION("typeof", type_reg)` |
| `is_expression` | `csharp_expr.lower_is_expr` | `CALL_FUNCTION("is_check", obj, type)` |
| `as_expression` | `csharp_expr.lower_as_expr` | (passthrough to left operand) |
| `lambda_expression` | `csharp_expr.lower_lambda` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `array_creation_expression` | `csharp_expr.lower_array_creation` | `NEW_ARRAY` + optional `STORE_INDEX` |
| `implicit_array_creation_expression` | `csharp_expr.lower_array_creation` | `NEW_ARRAY` + `STORE_INDEX` |
| `implicit_object_creation_expression` | `csharp_expr.lower_implicit_object_creation` | `NEW_OBJECT` + `CALL_METHOD "constructor"` |
| `query_expression` | `csharp_expr.lower_query_expression` | `CALL_FUNCTION("linq_query", ...)` |
| `from_clause` | `csharp_expr.lower_linq_clause` | Lowers named children |
| `select_clause` | `csharp_expr.lower_linq_clause` | Lowers named children |
| `where_clause` | `csharp_expr.lower_linq_clause` | Lowers named children |
| `await_expression` | `csharp_expr.lower_await_expr` | `CALL_FUNCTION("await", inner)` |
| `switch_expression` | `csharp_cf.lower_switch_expr` | `BINOP ==` + `BRANCH_IF` chain |
| `conditional_access_expression` | `csharp_expr.lower_conditional_access` | `LOAD_FIELD` (null-safety semantic) |
| `member_binding_expression` | `csharp_expr.lower_member_binding` | `SYMBOLIC("member_binding:{name}")` |
| `tuple_expression` | `csharp_expr.lower_tuple_expr` | `NEW_ARRAY("tuple", size)` + `STORE_INDEX` |
| `is_pattern_expression` | `csharp_expr.lower_is_pattern_expr` | `CALL_FUNCTION("is_check", obj, type)` |

## Statement Dispatch Table

The full statement dispatch returned by `_build_stmt_dispatch()`:

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `common_assign.lower_expression_statement` | (unwraps inner expr) |
| `local_declaration_statement` | `csharp_decl.lower_local_decl_stmt` | `STORE_VAR` per declarator |
| `return_statement` | `common_assign.lower_return` | `RETURN` |
| `if_statement` | `csharp_cf.lower_if` | `BRANCH_IF` + labels |
| `while_statement` | `common_cf.lower_while` | (inherited) `BRANCH_IF` loop |
| `for_statement` | `common_cf.lower_c_style_for` | (inherited) C-style for loop; init vars block-scoped |
| `foreach_statement` | `csharp_cf.lower_foreach` | Index-based loop with `LOAD_INDEX` |
| `method_declaration` | `csharp_decl.lower_method_decl` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `class_declaration` | `csharp_decl.lower_class_def` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `struct_declaration` | `csharp_decl.lower_class_def` | Same as class_declaration |
| `record_declaration` | `csharp_decl.lower_class_def` | Same as class_declaration |
| `record_struct_declaration` | `csharp_decl.lower_class_def` | Same as class_declaration |
| `interface_declaration` | `csharp_decl.lower_interface_decl` | `NEW_OBJECT("interface:{name}")` + `STORE_INDEX` |
| `enum_declaration` | `csharp_decl.lower_enum_decl` | `NEW_OBJECT("enum:{name}")` + `STORE_INDEX` |
| `namespace_declaration` | `csharp_decl.lower_namespace` | (lowers body block) |
| `throw_statement` | `csharp_cf.lower_throw` | `THROW` |
| `block` | `lambda ctx, node: ctx.lower_block(node)` | (inherited block lowering) |
| `global_statement` | `csharp_cf.lower_global_statement` | (unwraps inner statement) |
| `using_directive` | `lambda ctx, node: None` | No-op |
| `do_statement` | `csharp_cf.lower_do_while` | Body-first loop + `BRANCH_IF` |
| `switch_statement` | `csharp_cf.lower_switch` | `BINOP ==` + `BRANCH_IF` chain |
| `try_statement` | `csharp_cf.lower_try` | `LABEL`/`SYMBOLIC`/`BRANCH` (try/catch/finally) |
| `constructor_declaration` | `csharp_decl.lower_constructor_decl` | Function def named `__init__` |
| `field_declaration` | `csharp_decl.lower_field_decl` | `STORE_VAR` per declarator |
| `property_declaration` | `csharp_decl.lower_property_decl` | `STORE_FIELD` on `this` |
| `break_statement` | `common_cf.lower_break` | `BRANCH` to break target |
| `continue_statement` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `lock_statement` | `csharp_cf.lower_lock_stmt` | (lowers lock expr + body block) |
| `using_statement` | `csharp_cf.lower_using_stmt` | (lowers resource decl + body block) |
| `checked_statement` | `csharp_cf.lower_checked_stmt` | (lowers body block) |
| `fixed_statement` | `csharp_cf.lower_fixed_stmt` | (lowers body block) |
| `event_field_declaration` | `csharp_decl.lower_event_field_decl` | `STORE_VAR` via variable_declaration |
| `event_declaration` | `csharp_decl.lower_event_decl` | `CONST("event:{name}")` + `STORE_VAR` |
| `variable_declaration` | `csharp_decl.lower_variable_declaration` | `STORE_VAR` per declarator |
| `delegate_declaration` | `csharp_decl.lower_delegate_declaration` | Function stub |
| `local_function_statement` | `csharp_decl.lower_local_function_stmt` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `yield_statement` | `csharp_cf.lower_yield_stmt` | `CALL_FUNCTION("yield", val)` or `CALL_FUNCTION("yield_break")` |

## Language-Specific Lowering Methods

### `csharp_cf.lower_global_statement(ctx, node)`
Unwraps `global_statement` nodes (top-level C# 9 statements). Iterates named children and dispatches each to `ctx.lower_stmt`.

### `csharp_decl.lower_local_decl_stmt(ctx, node)` / `csharp_decl.lower_variable_declaration(ctx, node)` / `csharp_decl._lower_csharp_declarator(ctx, node, type_hint)`
Three-level chain for local variable declarations:
1. `lower_local_decl_stmt` finds `variable_declaration` children
2. `lower_variable_declaration` finds `variable_declarator` children, extracts type hint
3. `_lower_csharp_declarator` extracts the identifier (first named child before `=`) and the value (first named child after `=`). If no initializer, stores `CONST "None"`. Seeds variable type.

### `csharp_expr.lower_invocation(ctx, node) -> str`
Handles `invocation_expression`. Extracts `function` and `arguments` fields:
- If `function` is a `member_access_expression`: extracts `expression` (object) and `name` fields, emits `CALL_METHOD`
- If `function` is an `identifier`: emits `CALL_FUNCTION`
- Otherwise: emits `CALL_UNKNOWN` with dynamically-lowered target

### `csharp_expr.lower_object_creation(ctx, node) -> str`
Handles `new ClassName(args)`. Extracts `type` and `arguments` fields. Emits `CALL_FUNCTION(type_name, ...args)`. Seeds register type with the type name.

### `csharp_expr.lower_member_access(ctx, node) -> str`
Handles `obj.Field`. Extracts `expression` (object) and `name` fields. Emits `LOAD_FIELD`.

### `csharp_expr.lower_element_access(ctx, node) -> str`
Handles `arr[idx]`. Extracts `expression` (object) and `subscript` (or `bracketed_argument_list` fallback). Delegates index extraction to `_extract_bracket_index`. Emits `LOAD_INDEX`.

### `csharp_expr._extract_bracket_index(ctx, bracket_node) -> str`
Unwraps C#'s `bracketed_argument_list -> argument -> expression` chain to extract the actual index expression. Falls back to `SYMBOLIC("unknown_index")` if no argument found.

### `csharp_expr.lower_initializer_expr(ctx, node) -> str`
Handles `initializer_expression` (`{a, b, c}`). Creates `NEW_ARRAY("list", size)` and populates with `STORE_INDEX` per element.

### `csharp_expr.lower_assignment_expr(ctx, node) -> str`
Handles `assignment_expression`. Lowers RHS, delegates to `lower_csharp_store_target`. Returns value register.

### `csharp_expr.lower_csharp_store_target(ctx, target, val_reg, parent_node)`
C#-specific store target handling:
- `identifier` -> `STORE_VAR`
- `member_access_expression` -> `STORE_FIELD` (extracts `expression` and `name` fields)
- `element_access_expression` -> `STORE_INDEX` (extracts `expression` and `subscript`/`bracketed_argument_list`)
- Fallback -> `STORE_VAR` with raw text

### `csharp_expr.lower_cast_expr(ctx, node) -> str`
Handles `cast_expression` (`(Type)expr`). Tries `value` field first, then falls back to last named child. Passthrough semantics (type info discarded).

### `csharp_expr.lower_ternary(ctx, node) -> str`
Handles `conditional_expression` (`a ? b : c`). Extracts `condition`, `consequence`, `alternative`. Emits `BRANCH_IF` with temp variable `__ternary_{counter}` to merge result.

### `csharp_expr.lower_typeof(ctx, node) -> str`
Handles `typeof(Type)`. Emits `CONST type_name` then `CALL_FUNCTION("typeof", type_reg)`.

### `csharp_expr.lower_is_expr(ctx, node) -> str`
Handles `x is Type`. Emits `CONST type_name` then `CALL_FUNCTION("is_check", obj_reg, type_reg)`.

### `csharp_expr.lower_as_expr(ctx, node) -> str`
Handles `x as Type`. Passthrough: lowers the left operand, ignoring the target type.

### `csharp_expr.lower_declaration_pattern(ctx, node) -> str`
Handles `int i` declaration patterns in switch/is expressions. Emits `CONST type_name` and optionally `STORE_VAR binding_name`.

### `csharp_expr.lower_lambda(ctx, node) -> str`
Handles C# lambdas (`(params) => expr` or `(params) => { body }`). Creates a function body block:
- If body is a `block`: lowers block + implicit return
- If body is an expression: evaluates and emits `RETURN`
Returns a function reference constant `func:{label}`.

### `csharp_expr.lower_array_creation(ctx, node) -> str`
Handles `array_creation_expression` and `implicit_array_creation_expression`.
- **With initializer**: `NEW_ARRAY("array", size)` + `STORE_INDEX` per element
- **Without initializer** (sized): `NEW_ARRAY("array", size_reg)` where size comes from rank specifier

### `csharp_expr.lower_csharp_interpolated_string(ctx, node) -> str`
Handles C# `$"...{expr}..."` interpolated strings. Extracts `string_content` and `interpolation` children, lowering interpolated expressions and building a `BINOP "+"` chain. Falls back to `lower_const_literal` for strings without interpolation.

### `csharp_expr.lower_implicit_object_creation(ctx, node) -> str`
Handles `new()` or `new() { ... }` (C# target-typed new). Emits `NEW_OBJECT "__implicit"` + `CALL_METHOD "constructor"`.

### `csharp_expr.lower_query_expression(ctx, node) -> str`
Handles LINQ `from n in nums where ... select ...`. Lowers all named children and emits `CALL_FUNCTION("linq_query", ...)`.

### `csharp_expr.lower_linq_clause(ctx, node) -> str`
Handles individual LINQ clauses (from/select/where). Lowers named children sequentially.

### `csharp_cf.lower_foreach(ctx, node)`
Handles `foreach (Type var in collection)`. Extracts `left` (variable), `right` (collection), `body`. Desugars to index-based loop: `len()`, `LOAD_INDEX`, increment. Uses block scoping via `ctx.enter_block_scope`/`ctx.exit_block_scope`.

### `csharp_decl.lower_method_decl(ctx, node, inject_this)`
Handles `method_declaration`. Extracts `name`, `parameters`, `body`. Emits function definition pattern with `csharp_expr.lower_csharp_params` for parameters. Optionally injects `SYMBOLIC param:this` + `STORE_VAR this` for instance methods (non-static). Seeds function return type.

### `csharp_expr.lower_csharp_params(ctx, params_node)`
Iterates `parameter` children, extracts `name` field, computes type hint, emits `SYMBOLIC("param:{name}")` + `STORE_VAR`. Seeds register, parameter, and variable types.

### `csharp_decl.lower_constructor_decl(ctx, node)`
Handles `constructor_declaration`. Identical to `lower_method_decl` except the function name is hardcoded to `"__init__"`.

### `csharp_decl.lower_class_def(ctx, node)`
Handles `class_declaration`, `struct_declaration`, `record_declaration`, and `record_struct_declaration`. Uses deferred lowering via `_lower_class_body`:
1. Emits `BRANCH` to skip, `LABEL` for class entry
2. Collects class body children (methods first, then rest)
3. Emits end label and class reference (includes parent info via `make_class_ref`)
4. Lowers deferred children at top level via `_lower_deferred_class_child`
5. Tracks current class name for `this` type seeding

This ordering ensures function references are registered before field initializers that may call them.

### `csharp_decl._lower_class_body(ctx, node) -> list`
Partitions class body children into methods (`method_declaration`, `constructor_declaration`) and rest. Returns methods + rest for deferred lowering. Skips `modifier`, `attribute_list`, `{`, `}`.

### `csharp_decl._lower_deferred_class_child(ctx, child)`
Dispatches deferred class children: `method_declaration` -> `lower_method_decl` (with `this` injection for non-static), `constructor_declaration` -> `lower_constructor_decl`, `field_declaration` -> `lower_field_decl`, `property_declaration` -> `lower_property_decl`, else -> `ctx.lower_stmt`.

### `csharp_decl.lower_field_decl(ctx, node)`
Handles `field_declaration`. Finds `variable_declaration` child and delegates to `lower_variable_declaration`.

### `csharp_decl.lower_property_decl(ctx, node)`
Handles `property_declaration`. Extracts property name, loads `this`, finds initializer (after `=` token). Emits `STORE_FIELD(this_reg, prop_name, val_reg)`. Also lowers accessor bodies (`get { ... }` / `set { ... }`) if present.

### `csharp_decl.lower_interface_decl(ctx, node)`
Handles `interface_declaration`. Creates `NEW_OBJECT("interface:{name}")` and populates with `STORE_INDEX` per named member (member name as key, index as value).

### `csharp_decl.lower_enum_decl(ctx, node)`
Handles `enum_declaration`. Creates `NEW_OBJECT("enum:{name}")` and populates with `STORE_INDEX` per `enum_member_declaration` (member name as key, ordinal as value).

### `csharp_decl.lower_namespace(ctx, node)`
Handles `namespace_declaration`. Simply lowers the `body` field as a block.

### `csharp_cf.lower_if(ctx, node)`
Handles `if_statement`. Extracts `condition` and `consequence` fields. Falls back to first `block` child if `consequence` field is absent. Handles `alternative` by recursively calling `lower_if` for else-if chains, or iterating named children (skipping `else` keyword) for else blocks.

### `csharp_cf.lower_throw(ctx, node)`
Delegates to `lower_raise_or_throw(ctx, node, keyword="throw")`.

### `csharp_cf.lower_do_while(ctx, node)`
Handles `do_statement`. Body-first loop: lowers body with loop context, then condition check with `BRANCH_IF`.

### `csharp_cf.lower_switch(ctx, node)`
Handles `switch_statement`. Extracts `value` (subject) and `body` (switch_body) fields. Iterates `switch_section` children. Each section with `constant_pattern` emits `BINOP ==` + `BRANCH_IF`; sections without pattern (default) emit unconditional `BRANCH`. Pushes `end_label` to `break_target_stack`.

### `csharp_cf.lower_switch_expr(ctx, node) -> str`
Handles C# 8 `switch expression`. Iterates `switch_expression_arm` children. Each arm's pattern is compared with `BINOP ==`; discard pattern (`_`) treated as default. Stores results in temp variable `__switch_expr_{counter}`.

### `csharp_cf.lower_try(ctx, node)`
Handles `try_statement`. Extracts body, iterates children for `catch_clause` (with `catch_declaration` containing type/name identifiers) and `finally_clause`. Delegates to `lower_try_catch`.

### `csharp_expr.lower_await_expr(ctx, node) -> str`
Handles `await_expression`. Lowers inner expression, emits `CALL_FUNCTION("await", inner_reg)`.

### `csharp_cf.lower_yield_stmt(ctx, node)`
Handles `yield_statement`. If `yield break`: emits `CALL_FUNCTION("yield_break")`. If `yield return expr`: emits `CALL_FUNCTION("yield", val_reg)`.

### `csharp_cf.lower_lock_stmt(ctx, node)` / `csharp_cf.lower_using_stmt(ctx, node)` / `csharp_cf.lower_checked_stmt(ctx, node)` / `csharp_cf.lower_fixed_stmt(ctx, node)`
Infrastructure statements. Each lowers the lock expression or resource declaration and then the body block. `checked` and `fixed` simply lower the body block.

### `csharp_decl.lower_event_field_decl(ctx, node)` / `csharp_decl.lower_event_decl(ctx, node)`
Event declarations. `lower_event_field_decl` delegates to `lower_variable_declaration`. `lower_event_decl` emits `CONST("event:{name}")` + `STORE_VAR`.

### `csharp_expr.lower_conditional_access(ctx, node) -> str`
Handles `obj?.Field`. Lowers object, extracts field from `member_binding_expression` child. Emits `LOAD_FIELD`. Null-safety is semantic only.

### `csharp_expr.lower_member_binding(ctx, node) -> str`
Standalone fallback for `.Field` part of conditional access. Emits `SYMBOLIC("member_binding:{name}")`.

### `csharp_decl.lower_local_function_stmt(ctx, node)`
Handles local functions inside method bodies. Same pattern as `lower_method_decl` but searches for `identifier` and `parameter_list` children by type as fallback.

### `csharp_expr.lower_tuple_expr(ctx, node) -> str`
Handles `(a, b, c)` tuples. Iterates `argument` children, unwraps each to inner expression. Creates `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element.

### `csharp_expr.lower_is_pattern_expr(ctx, node) -> str`
Handles `x is int y` pattern matching. Emits `CALL_FUNCTION("is_check", obj_reg, type_reg)`.

### `csharp_decl.lower_delegate_declaration(ctx, node)`
Handles `delegate` declarations. Emits a function stub with no body.

## Canonical Literal Handling

| C# Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based detection) |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |

C#'s `true`/`false` are parsed as `boolean_literal` nodes; `lower_canonical_bool` normalizes via case-insensitive comparison. C#'s `null` is parsed as `null_literal`.

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

1. **Deferred class body lowering**: `lower_class_def` collects class body members and lowers them at top level *after* the class reference is stored. Methods are lowered before fields/properties to ensure function references are available for initializers. The current class name is tracked for `this` type seeding.

2. **`attr_object_field = "expression"`**: C#'s tree-sitter grammar uses `expression` (not `object`) as the field name for the object in `member_access_expression`. This differs from PHP and most other frontends.

3. **Constructors mapped to `__init__`**: C# constructors are lowered as functions named `__init__`, matching Python's convention for interoperability in cross-language analysis.

4. **`using_directive` is noise**: Import directives are filtered as no-ops in both the noise types and the statement dispatch table.

5. **Properties emit `STORE_FIELD` on `this`**: Property declarations generate `LOAD_VAR "this"` followed by `STORE_FIELD`. Auto-properties without initializers get `CONST "None"`. Accessor bodies (`get { ... }` / `set { ... }`) are lowered as statements within the property.

6. **Switch expression vs switch statement**: The frontend supports both C#'s traditional `switch` statement (lowered as if/else chain with break targets) and C# 8's `switch` expression (value-producing, with discard `_` as default pattern).

7. **Structs and records treated as classes**: `struct_declaration`, `record_declaration`, and `record_struct_declaration` all map to the same `lower_class_def` handler as `class_declaration`. No value-type semantics are modeled.

8. **Events as constants**: Event declarations emit `CONST("event:{name}")` + `STORE_VAR`. No delegate/subscription semantics are modeled.

9. **`as` cast is passthrough**: `x as Type` returns the left operand's register directly; the type check is not modeled. For safety-aware analysis, `is` expressions emit proper `CALL_FUNCTION("is_check", ...)`.

10. **Pure function architecture**: All lowering logic is implemented as pure functions taking `(ctx: TreeSitterEmitContext, node)` rather than instance methods. The `CSharpFrontend` class is a thin orchestrator that builds dispatch tables from these functions via `_build_expr_dispatch()` and `_build_stmt_dispatch()`. Node type strings are centralised in `CSharpNodeType` constants.

11. **Instance method `this` injection**: `_lower_deferred_class_child` injects `this` parameter for non-static methods by checking for the `static` modifier and passing `inject_this=True` to `lower_method_decl`.
