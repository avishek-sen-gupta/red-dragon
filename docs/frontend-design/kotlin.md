# Kotlin Frontend

> `interpreter/frontends/kotlin/` -- Extends BaseFrontend

```
interpreter/frontends/kotlin/
  ├── frontend.py       # KotlinFrontend orchestrator (dispatch tables + constants)
  ├── node_types.py     # KotlinNodeType constants for tree-sitter node type strings
  ├── expressions.py    # Kotlin-specific expression lowerers (pure functions)
  ├── control_flow.py   # Kotlin-specific control flow lowerers (pure functions)
  └── declarations.py   # Kotlin-specific declaration lowerers (pure functions)
```

## Overview

The Kotlin frontend lowers tree-sitter Kotlin ASTs into flattened TAC IR. Kotlin's grammar is expression-oriented -- `if`, `when`, and `try` are all value-producing expressions. The frontend handles this duality by providing both expression-returning handlers (for `_build_expr_dispatch()`) and statement-discarding wrappers (for `_build_stmt_dispatch()`). It also handles Kotlin-specific features: navigation expressions (`obj.field`), elvis operator (`?:`), not-null assertions (`!!`), `when` expressions, companion objects, object declarations (singletons), enum classes, infix functions, `is`/`as` type operations, lambda literals, string interpolation, destructuring declarations, and loop-as-expression.

## Class Hierarchy

```
Frontend (abstract)
  -> BaseFrontend (_base.py)
       -> KotlinFrontend (kotlin/frontend.py)
```

Nothing extends `KotlinFrontend`. It inherits common lowering infrastructure from `BaseFrontend` and delegates language-specific lowering to pure functions in the `expressions`, `control_flow`, and `declarations` modules, plus shared functions from `common.expressions`, `common.control_flow`, and `common.exceptions`.

## Grammar Constants (`_build_constants()`)

| Field | BaseFrontend Default | Kotlin Value |
|---|---|---|
| `comment_types` | `frozenset({"comment"})` | `frozenset({"comment", "multiline_comment", "line_comment"})` |
| `noise_types` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` |
| `block_node_types` | `frozenset()` | `frozenset({"source_file", "statements"})` |

All other constants retain `GrammarConstants` defaults. Notably, Kotlin does **not** override `attribute_node_type`, `attr_object_field`, `attr_attribute_field`, `default_return_value`, or any field-name constants -- instead it handles member access through its own `kotlin_expr.lower_navigation_expr` and `kotlin_expr.lower_kotlin_store_target`.

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `simple_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `long_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `real_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `character_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `kotlin_expr.lower_kotlin_string_literal` | `CONST` (raw or interpolated) |
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `additive_expression` | `common_expr.lower_binop` | `BINOP` |
| `multiplicative_expression` | `common_expr.lower_binop` | `BINOP` |
| `comparison_expression` | `common_expr.lower_binop` | `BINOP` |
| `equality_expression` | `common_expr.lower_binop` | `BINOP` |
| `conjunction_expression` | `common_expr.lower_binop` | `BINOP` |
| `disjunction_expression` | `common_expr.lower_binop` | `BINOP` |
| `prefix_expression` | `common_expr.lower_unop` | `UNOP` |
| `postfix_expression` | `kotlin_expr.lower_postfix_expr` | `BINOP(+/-) + STORE` or `UNOP("!!")` |
| `parenthesized_expression` | `common_expr.lower_paren` | (unwraps inner expression) |
| `call_expression` | `kotlin_expr.lower_kotlin_call` | `CALL_METHOD`, `CALL_FUNCTION`, or `CALL_UNKNOWN` |
| `navigation_expression` | `kotlin_expr.lower_navigation_expr` | `LOAD_FIELD` |
| `if_expression` | `kotlin_expr.lower_if_expr` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` (value-producing) |
| `when_expression` | `kotlin_expr.lower_when_expr` | equality chain + `STORE_VAR` + `LOAD_VAR` |
| `collection_literal` | `common_expr.lower_list_literal` | `NEW_ARRAY` + `STORE_INDEX` per element |
| `this_expression` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `super_expression` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `lambda_literal` | `kotlin_expr.lower_lambda_literal` | `BRANCH`/`LABEL` func body + `CONST <function:...>` |
| `object_literal` | `kotlin_expr.lower_object_literal` | `NEW_OBJECT` with class-style labels |
| `range_expression` | `kotlin_expr.lower_range_expr` | `CALL_FUNCTION("range", start, end)` |
| `statements` | `kotlin_expr.lower_statements_expr` | (lowers all but last as stmts, last as expr) |
| `jump_expression` | `kotlin_expr.lower_jump_as_expr` | `RETURN`/`THROW`/`BRANCH` + `CONST "None"` |
| `assignment` | `kotlin_expr.lower_kotlin_assignment_expr` | `STORE_VAR`/`STORE_FIELD` + `CONST "None"` |
| `check_expression` | `kotlin_expr.lower_check_expr` | `CALL_FUNCTION("is", expr, type_name)` |
| `try_expression` | `kotlin_expr.lower_try_expr` | try/catch/finally + `CONST "None"` |
| `hex_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `elvis_expression` | `kotlin_expr.lower_elvis_expr` | `BINOP("?:", left, right)` |
| `infix_expression` | `kotlin_expr.lower_infix_expr` | `CALL_FUNCTION(infix_name, left, right)` |
| `indexing_expression` | `kotlin_expr.lower_indexing_expr` | `LOAD_INDEX` |
| `as_expression` | `kotlin_expr.lower_as_expr` | `CALL_FUNCTION("as", expr, type_name)` |
| `while_statement` | `kotlin_expr.lower_loop_as_expr` | (lowers as stmt, returns `CONST "None"`) |
| `for_statement` | `kotlin_expr.lower_loop_as_expr` | (lowers as stmt, returns `CONST "None"`) |
| `do_while_statement` | `kotlin_expr.lower_loop_as_expr` | (lowers as stmt, returns `CONST "None"`) |
| `type_test` | `kotlin_expr.lower_type_test` | `CONST "is:TypeName"` |
| `label` | `common_expr.lower_const_literal` | `CONST` (raw text) |

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `property_declaration` | `kotlin_decl.lower_property_decl` | `STORE_VAR` |
| `assignment` | `kotlin_cf.lower_kotlin_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `function_declaration` | `kotlin_decl.lower_function_decl` | `BRANCH`/`LABEL` func + params + `RETURN` + `STORE_VAR` |
| `class_declaration` | `kotlin_decl.lower_class_decl` | `BRANCH`/`LABEL` class + body + `STORE_VAR` |
| `if_expression` | `kotlin_cf.lower_if_stmt` | (delegates to `kotlin_expr.lower_if_expr`, discards result) |
| `while_statement` | `kotlin_cf.lower_while_stmt` | `BRANCH_IF` loop |
| `for_statement` | `kotlin_cf.lower_for_stmt` | index-based iteration loop |
| `jump_expression` | `kotlin_cf.lower_jump_expr` | `RETURN` / `THROW` / `BRANCH` (break/continue) |
| `source_file` | `lambda ctx, node: ctx.lower_block(node)` | (iterates children) |
| `statements` | `lambda ctx, node: ctx.lower_block(node)` | (iterates children) |
| `import_list` | `lambda ctx, node: None` | (skipped) |
| `import_header` | `lambda ctx, node: None` | (skipped) |
| `package_header` | `lambda ctx, node: None` | (skipped) |
| `do_while_statement` | `kotlin_cf.lower_do_while_stmt` | body-first loop with `BRANCH_IF` at end |
| `object_declaration` | `kotlin_decl.lower_object_decl` | `NEW_OBJECT` + `STORE_VAR` |
| `try_expression` | `kotlin_cf.lower_try_stmt` | `LABEL`/`BRANCH` try/catch/finally blocks |
| `type_alias` | `lambda ctx, node: None` | (skipped) |

## Language-Specific Lowering Methods

### `kotlin_expr.lower_kotlin_string_literal(ctx, node) -> str`
Lowers Kotlin string literals with `$var` / `${expr}` interpolation. Decomposes `interpolated_identifier` and `interpolated_expression` children into parts, then uses `common_expr.lower_interpolated_string_parts` to concatenate. Falls back to `lower_const_literal` for non-interpolated strings.

### `kotlin_decl.lower_property_decl(ctx, node)`
Handles Kotlin's `val`/`var` declarations. Supports destructuring via `multi_variable_declaration` (lowers as `LOAD_INDEX` per element). For simple declarations: finds the `variable_declaration` child, extracts the name via `_extract_property_name` (looks for `simple_identifier`), and finds the value via `_find_property_value` (scans children after `=`). Emits `STORE_VAR`. Without an initializer, stores `CONST "None"`. Extracts and seeds type hints.

### `kotlin_decl._extract_property_name(ctx, var_decl_node) -> str`
Finds `simple_identifier` child in a `variable_declaration` node. Returns `"__unknown"` if none found.

### `kotlin_decl._find_property_value(ctx, node)`
Scans children of a `property_declaration` for `=`, then returns the first named child after it.

### `kotlin_cf.lower_kotlin_assignment(ctx, node)`
Handles Kotlin assignment which uses `directly_assignable_expression` and `expression` field names. Falls back to positional children if field lookup fails. Delegates to `kotlin_expr.lower_kotlin_store_target`.

### `kotlin_expr.lower_kotlin_assignment_expr(ctx, node) -> str`
Expression-context wrapper for assignment. Calls `kotlin_cf.lower_kotlin_assignment` then returns a `CONST "None"` register (Kotlin assignments are not value-producing in the language, but the IR needs a register).

### `kotlin_decl.lower_function_decl(ctx, node, inject_this=False)`
Locates `simple_identifier` (name), `function_value_parameters`, and `function_body` children by type (not field name). Creates function label, lowers params via `_lower_kotlin_params`, lowers body via `_lower_function_body`, emits implicit return, and registers function reference. Expression-bodied functions (`fun f() = 42`) return the expression directly. Optionally injects `this` parameter for instance methods.

### `kotlin_decl._lower_kotlin_params(ctx, params_node)`
Walks `parameter` children. For each, finds `simple_identifier` child and emits `SYMBOLIC("param:name")` + `STORE_VAR`. Extracts and seeds type hints.

### `kotlin_decl._lower_function_body(ctx, body_node) -> str`
Unwraps the `function_body` node which wraps the actual block or expression. Skips `{`, `}`, `=` tokens, lowers remaining named children. Returns the last expression's register for expression-bodied functions, otherwise returns empty string.

### `kotlin_decl.lower_class_decl(ctx, node)`
Finds `type_identifier` (name) and `class_body`/`enum_class_body` by type. Emits class label structure. Dispatches body to either `_lower_enum_class_body` or `_lower_class_body_with_companions`. Extracts parent classes/interfaces from `delegation_specifier` nodes.

### `kotlin_decl._lower_class_body_with_companions(ctx, node)`
Iterates class body children. `companion_object` children are lowered via `_lower_companion_object`; `function_declaration` children get `inject_this=True`; all others go through `ctx.lower_stmt`.

### `kotlin_decl._lower_companion_object(ctx, node)`
Finds the `class_body` child inside a companion object and lowers it as a block.

### `kotlin_expr.lower_kotlin_call(ctx, node) -> str`
Handles Kotlin's `call_expression` which has a callee (first named child) and a `call_suffix` containing `value_arguments`. Three paths: (1) callee is `navigation_expression` -> `CALL_METHOD`; (2) callee is `simple_identifier` -> `CALL_FUNCTION`; (3) dynamic target -> `CALL_UNKNOWN`.

### `kotlin_expr._extract_kotlin_args(ctx, args_node) -> list[str]`
Walks `value_argument` children, unwrapping each to its inner named child. Also handles bare named children that are not wrapped.

### `kotlin_expr.lower_navigation_expr(ctx, node) -> str`
Handles `obj.field` member access. Lowers first named child as object, uses last named child text as field name (unwrapping `navigation_suffix`), emits `LOAD_FIELD`.

### `kotlin_expr.lower_if_expr(ctx, node) -> str`
Value-producing `if`. Uses positional named children: `children[0]` is condition, `children[1]` is consequence, `children[2]` (optional) is alternative. Branches to true/false labels, stores results in synthetic `__if_result_N` variable, loads at end. Uses `_lower_control_body` for each branch.

### `kotlin_cf.lower_if_stmt(ctx, node)`
Thin wrapper -- calls `kotlin_expr.lower_if_expr` and discards the return register.

### `kotlin_expr.lower_statements_expr(ctx, node) -> str`
Lowers a `statements` node in expression context: all children except the last are lowered as statements, the last is lowered as an expression and its register is returned. Empty nodes return `CONST "None"`.

### `kotlin_expr.lower_loop_as_expr(ctx, node) -> str`
Lowers while/for/do-while in expression position: lowers as statement, then returns `CONST "None"`.

### `kotlin_expr._lower_control_body(ctx, body_node) -> str`
Lowers a `control_structure_body` or block, returning the register of the last expression. Filters out braces, semicolons, comments, noise. If the sole child is a block node (e.g. `statements`), unwraps it. All but last child lowered as statements, last as expression. Returns `CONST "None"` for empty bodies.

### `kotlin_cf.lower_while_stmt(ctx, node)`
Finds condition (first named child) and body (`control_structure_body` type). Standard while-loop IR with `BRANCH_IF`. Pushes loop context for break/continue.

### `kotlin_cf.lower_for_stmt(ctx, node)`
Finds loop variable (`variable_declaration` or `simple_identifier`), iterable (expression after `in` keyword via `_find_for_iterable`), and body (`control_structure_body`). Lowers as index-based loop: `idx=0`, `len=len(iterable)`, `while idx < len { var = iterable[idx]; body; idx++ }`.

### `kotlin_cf._find_for_iterable(ctx, node)`
Scans children for the `in` keyword text, then returns the next named child that is not `control_structure_body`.

### `kotlin_cf._extract_for_var_name(ctx, var_node) -> str`
Returns text for `simple_identifier`, or finds `simple_identifier` child for other node types.

### `kotlin_expr.lower_when_expr(ctx, node) -> str`
Lowers Kotlin `when` (pattern matching). Extracts subject from `when_subject` child. For each `when_entry`: extracts `when_condition` (compared with `BINOP("==")` + `BRANCH_IF`), and body from `control_structure_body` or direct children. Each arm stores result in `__when_result_N`. Entries without conditions are `else` branches (unconditional `BRANCH`). Returns `LOAD_VAR` of result at end label.

### `kotlin_cf.lower_jump_expr(ctx, node)`
Dispatches based on text prefix: `return` -> `RETURN`, `throw` -> `THROW` (via `common.exceptions.lower_raise_or_throw`), `break` -> `common_cf.lower_break`, `continue` -> `common_cf.lower_continue`. Logs warning for unrecognized jump expressions.

### `kotlin_expr.lower_jump_as_expr(ctx, node) -> str`
Expression-context wrapper for jump: calls `kotlin_cf.lower_jump_expr` then returns `CONST "None"`.

### `kotlin_expr.lower_postfix_expr(ctx, node) -> str`
Dispatches by text content: `++`/`--` -> `common_expr.lower_update_expr`, `!!` suffix -> `_lower_not_null_assertion`, else -> `lower_const_literal` fallback.

### `kotlin_expr._lower_not_null_assertion(ctx, node) -> str`
Lowers `expr!!` as `UNOP("!!", expr_reg)`.

### `kotlin_expr.lower_lambda_literal(ctx, node) -> str`
Creates function body with label `func___lambda_N`. Extracts `lambda_parameters` -> `variable_declaration` -> `simple_identifier` for parameter names. Body children are filtered (skip braces, `->`, comments). For `statements` body nodes, lowers all but last as statements, last as expression with implicit return. Emits implicit return, returns function reference constant.

### `kotlin_expr.lower_object_literal(ctx, node) -> str`
Lowers `object : Type { ... }` as class-style label structure + `NEW_OBJECT`. Extracts type from `delegation_specifier` child.

### `kotlin_expr.lower_range_expr(ctx, node) -> str`
Lowers `1..10` as `CALL_FUNCTION("range", start, end)`.

### `kotlin_expr.lower_kotlin_store_target(ctx, target, val_reg, parent_node)`
Handles Kotlin-specific target types:
- `simple_identifier` -> `STORE_VAR`
- `navigation_expression` -> `STORE_FIELD` (extracts object + field from named children)
- `indexing_expression` -> `STORE_INDEX` (extracts object + index from `indexing_suffix`)
- `directly_assignable_expression` -> checks for `indexing_suffix` child (-> `STORE_INDEX`), `navigation_suffix` (-> `STORE_FIELD`), or unwraps inner named child recursively
- else -> `STORE_VAR` fallback

### `kotlin_cf._extract_try_parts(ctx, node)`
Extracts try body (`statements` or `control_structure_body`), catch clauses from `catch_block` children (`simple_identifier` for variable, `user_type` for exception type; body is `statements`/`control_structure_body`), and finally from `finally_block`. Returns `(body_node, catch_clauses, finally_node)`.

### `kotlin_cf.lower_try_stmt(ctx, node)`
Delegates to `_extract_try_parts` then `common.exceptions.lower_try_catch`.

### `kotlin_expr.lower_try_expr(ctx, node) -> str`
Expression-context wrapper: calls `kotlin_cf.lower_try_stmt`, returns `CONST "None"`.

### `kotlin_expr.lower_check_expr(ctx, node) -> str`
Lowers `is`/`!is` type checks as `CALL_FUNCTION("is", expr_reg, type_text)`. Uses first and last named children.

### `kotlin_expr.lower_type_test(ctx, node) -> str`
Lowers `is Type` in pattern matching contexts (e.g., `when` arms) as `CONST "is:TypeName"`.

### `kotlin_cf.lower_do_while_stmt(ctx, node)`
Lowers `do { body } while (cond)`. Body is `control_structure_body`; condition is the first named child that is not the body. Pushes loop context with `continue_label=cond_label` so `continue` jumps to condition evaluation.

### `kotlin_decl.lower_object_decl(ctx, node)`
Lowers Kotlin singleton `object Name { ... }`. Finds `type_identifier` (name) and `class_body`. Emits class-style label structure, lowers body, then emits `NEW_OBJECT(obj_name)` + `STORE_VAR` (unlike classes which use `CLASS_REF_TEMPLATE`).

### `kotlin_decl._lower_enum_class_body(ctx, node)`
Iterates children: `enum_entry` -> `_lower_enum_entry`; other named non-punctuation -> `ctx.lower_stmt`.

### `kotlin_decl._lower_enum_entry(ctx, node)`
Emits `NEW_OBJECT("enum:EntryName")` + `STORE_VAR(entry_name, reg)` for each enum constant.

### `kotlin_expr.lower_elvis_expr(ctx, node) -> str`
Lowers `x ?: default` as `BINOP("?:", left_reg, right_reg)`.

### `kotlin_expr.lower_infix_expr(ctx, node) -> str`
Lowers `a to b`, `x until y` etc. Expects 3 named children: left, infix function name, right. Emits `CALL_FUNCTION(infix_name, left_reg, right_reg)`.

### `kotlin_expr.lower_indexing_expr(ctx, node) -> str`
Lowers `collection[index]`. First named child is the collection; index is inside `indexing_suffix` child. Emits `LOAD_INDEX(obj_reg, idx_reg)`.

### `kotlin_expr.lower_as_expr(ctx, node) -> str`
Lowers `expr as Type` or `expr as? Type` as `CALL_FUNCTION("as", expr_reg, type_name)`.

## Canonical Literal Handling

| Kotlin AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based dispatch) |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |

Kotlin uses a single `boolean_literal` node type for both `true` and `false`, so it uses `lower_canonical_bool` which inspects the node text to determine which canonical value to emit.

## Example

**Kotlin source:**
```kotlin
fun greet(name: String): String {
    val greeting = if (name == "World") "Hello" else "Hi"
    return "$greeting, $name!"
}
```

**Emitted IR (simplified):**
```
LABEL entry
BRANCH end_greet_1
LABEL func_greet_0
SYMBOLIC %0 "param:name"
STORE_VAR name, %0
LOAD_VAR %1, name
CONST %2, "World"
BINOP %3, "==", %1, %2
BRANCH_IF %3, if_true_2, if_false_3
LABEL if_true_2
CONST %4, "Hello"
STORE_VAR __if_result_4, %4
BRANCH if_end_4
LABEL if_false_3
CONST %5, "Hi"
STORE_VAR __if_result_4, %5
BRANCH if_end_4
LABEL if_end_4
LOAD_VAR %6, __if_result_4
STORE_VAR greeting, %6
LOAD_VAR %7, greeting
RETURN %7
CONST %8, "None"
RETURN %8
LABEL end_greet_1
CONST %9, "<function:greet@func_greet_0>"
STORE_VAR greet, %9
```

## Design Notes

- **Expression-oriented duality**: Many Kotlin constructs (`if`, `when`, `try`, `assignment`, `jump`, loops) appear in both `_build_expr_dispatch()` and `_build_stmt_dispatch()`. The statement handlers are thin wrappers that call the expression handler and discard the register. Loop-as-expression returns `CONST "None"`.
- **No `attribute_node_type` override**: Unlike Java/Scala which override attribute constants, Kotlin handles member access entirely through `kotlin_expr.lower_navigation_expr` and `kotlin_expr.lower_kotlin_store_target`. The base attribute lowering is never invoked.
- **Property declarations**: Kotlin `val`/`var` use a different structure from Java local variable declarations. The value is found by scanning for `=` rather than using a field name, because tree-sitter Kotlin does not expose a `value` field on `property_declaration`.
- **Destructuring declarations**: `val (a, b) = expr` is handled via `multi_variable_declaration` detection, emitting `LOAD_INDEX` per element.
- **Jump expression polymorphism**: Kotlin unifies `return`, `throw`, `break`, and `continue` under a single `jump_expression` node type. The frontend dispatches by inspecting the text prefix.
- **`when` as equality chain**: Similar to Java switch lowering, `when` is lowered as a linear chain of `BINOP("==")` comparisons. Entries without conditions become unconditional branches (the `else` arm).
- **Object declarations**: Kotlin singletons are lowered differently from classes -- they use `NEW_OBJECT` instead of `CLASS_REF_TEMPLATE` since they represent instances, not class references.
- **Object literals**: Anonymous `object : Type { ... }` expressions are lowered with class-style label structure + `NEW_OBJECT`.
- **Companion objects**: Lowered by simply lowering the companion's `class_body` as a block, effectively hoisting its members to the enclosing scope.
- **Enum entries as objects**: Each enum entry is lowered as `NEW_OBJECT("enum:EntryName")` + `STORE_VAR`, giving each entry its own object identity.
- **For-each as index loop**: Like Java, for-each is lowered as an index-based while loop with `len()` and `LOAD_INDEX`. The index variable is stored as `__for_idx`.
- **Elvis operator**: `?:` is emitted as a `BINOP` rather than being desugared into branches, since the VM handles it directly.
- **Infix functions**: `a to b` is lowered as `CALL_FUNCTION("to", a, b)` -- the infix function name is the middle named child.
- **Range expressions**: `1..10` is lowered as `CALL_FUNCTION("range", start, end)`.
- **`as` expression**: Type casts are lowered as `CALL_FUNCTION("as", expr, type_name)` rather than being transparent like Java casts.
- **String interpolation**: `$var` and `${expr}` are decomposed into parts and concatenated via `lower_interpolated_string_parts`.
- **Catch blocks**: Kotlin tree-sitter produces `catch_block` with `simple_identifier` for the variable name and `user_type` for the exception type. These are extracted positionally.
- **`directly_assignable_expression`**: Kotlin wraps assignment targets in this node type. The `lower_kotlin_store_target` function unwraps it, checking for `indexing_suffix` (array assignment), `navigation_suffix` (field assignment), or recursing on the inner node.
- **Pure function architecture**: All lowering logic lives in pure functions taking `(ctx: TreeSitterEmitContext, node)` instead of instance methods. The `KotlinFrontend` class is a thin orchestrator that builds dispatch tables and constants.
- **Instance method `this` injection**: `lower_function_decl` accepts an `inject_this` parameter; class body function declarations get `this` injected via `_lower_class_body_with_companions`.
