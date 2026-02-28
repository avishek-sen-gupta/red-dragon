# Kotlin Frontend

> `interpreter/frontends/kotlin.py` -- Extends BaseFrontend -- ~1116 lines

## Overview

The Kotlin frontend lowers tree-sitter Kotlin ASTs into flattened TAC IR. Kotlin's grammar is expression-oriented -- `if`, `when`, and `try` are all value-producing expressions. The frontend handles this duality by providing both expression-returning handlers (for `_EXPR_DISPATCH`) and statement-discarding wrappers (for `_STMT_DISPATCH`). It also handles Kotlin-specific features: navigation expressions (`obj.field`), elvis operator (`?:`), not-null assertions (`!!`), `when` expressions, companion objects, object declarations (singletons), enum classes, infix functions, `is`/`as` type operations, and lambda literals.

## Class Hierarchy

```
Frontend (abstract)
  -> BaseFrontend (_base.py)
       -> KotlinFrontend (kotlin.py)
```

Nothing extends `KotlinFrontend`. It inherits common lowering infrastructure from `BaseFrontend` including register/label allocation, `_emit`, `_lower_block`, `_lower_stmt`, `_lower_expr`, `_lower_binop`, `_lower_unop`, `_lower_paren`, `_lower_update_expr`, `_lower_break`, `_lower_continue`, `_lower_try_catch`, `_lower_raise_or_throw`, `_lower_list_literal`, etc.

## Overridden Constants

| Constant | BaseFrontend Default | KotlinFrontend Value |
|---|---|---|
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment", "multiline_comment"})` |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` |

All other constants retain `BaseFrontend` defaults. Notably, Kotlin does **not** override `ATTRIBUTE_NODE_TYPE`, `ATTR_OBJECT_FIELD`, `ATTR_ATTRIBUTE_FIELD`, `DEFAULT_RETURN_VALUE`, or any field-name constants -- instead it handles member access through its own `_lower_navigation_expr` and `_lower_store_target` override.

## Expression Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `simple_identifier` | `_lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `long_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `real_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |
| `additive_expression` | `_lower_binop` | `BINOP` |
| `multiplicative_expression` | `_lower_binop` | `BINOP` |
| `comparison_expression` | `_lower_binop` | `BINOP` |
| `equality_expression` | `_lower_binop` | `BINOP` |
| `conjunction_expression` | `_lower_binop` | `BINOP` |
| `disjunction_expression` | `_lower_binop` | `BINOP` |
| `prefix_expression` | `_lower_unop` | `UNOP` |
| `postfix_expression` | `_lower_postfix_expr` | `BINOP(+/-) + STORE` or `UNOP("!!")` |
| `parenthesized_expression` | `_lower_paren` | (unwraps inner expression) |
| `call_expression` | `_lower_kotlin_call` | `CALL_METHOD`, `CALL_FUNCTION`, or `CALL_UNKNOWN` |
| `navigation_expression` | `_lower_navigation_expr` | `LOAD_FIELD` |
| `if_expression` | `_lower_if_expr` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` (value-producing) |
| `when_expression` | `_lower_when_expr` | equality chain + `STORE_VAR` + `LOAD_VAR` |
| `collection_literal` | `_lower_list_literal` | `NEW_ARRAY` + `STORE_INDEX` per element |
| `this_expression` | `_lower_identifier` | `LOAD_VAR` |
| `super_expression` | `_lower_identifier` | `LOAD_VAR` |
| `lambda_literal` | `_lower_lambda_literal` | `BRANCH`/`LABEL` func body + `CONST <function:...>` |
| `object_literal` | `_lower_symbolic_node` | `SYMBOLIC` |
| `range_expression` | `_lower_symbolic_node` | `SYMBOLIC` |
| `statements` | `_lower_statements_expr` | (lowers all but last as stmts, last as expr) |
| `jump_expression` | `_lower_jump_as_expr` | `RETURN`/`THROW`/`BRANCH` + `CONST "None"` |
| `assignment` | `_lower_kotlin_assignment_expr` | `STORE_VAR`/`STORE_FIELD` + `CONST "None"` |
| `check_expression` | `_lower_check_expr` | `CALL_FUNCTION("is", expr, type_name)` |
| `try_expression` | `_lower_try_expr` | try/catch/finally + `CONST "None"` |
| `hex_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `elvis_expression` | `_lower_elvis_expr` | `BINOP("?:", left, right)` |
| `infix_expression` | `_lower_infix_expr` | `CALL_FUNCTION(infix_name, left, right)` |
| `indexing_expression` | `_lower_indexing_expr` | `LOAD_INDEX` |
| `as_expression` | `_lower_as_expr` | `CALL_FUNCTION("as", expr, type_name)` |

## Statement Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `property_declaration` | `_lower_property_decl` | `STORE_VAR` |
| `assignment` | `_lower_kotlin_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `function_declaration` | `_lower_function_decl` | `BRANCH`/`LABEL` func + params + `RETURN` + `STORE_VAR` |
| `class_declaration` | `_lower_class_decl` | `BRANCH`/`LABEL` class + body + `STORE_VAR` |
| `if_expression` | `_lower_if_stmt` | (delegates to `_lower_if_expr`, discards result) |
| `while_statement` | `_lower_while_stmt` | `BRANCH_IF` loop |
| `for_statement` | `_lower_for_stmt` | index-based iteration loop |
| `jump_expression` | `_lower_jump_expr` | `RETURN` / `THROW` / `BRANCH` (break/continue) |
| `source_file` | `_lower_block` | (iterates children) |
| `statements` | `_lower_block` | (iterates children) |
| `import_list` | `lambda _: None` | (skipped) |
| `import_header` | `lambda _: None` | (skipped) |
| `package_header` | `lambda _: None` | (skipped) |
| `do_while_statement` | `_lower_do_while_stmt` | body-first loop with `BRANCH_IF` at end |
| `object_declaration` | `_lower_object_decl` | `NEW_OBJECT` + `STORE_VAR` |
| `try_expression` | `_lower_try_stmt` | `LABEL`/`BRANCH` try/catch/finally blocks |
| `type_alias` | `lambda _: None` | (skipped) |

## Language-Specific Lowering Methods

### `_lower_property_decl(node)`
Handles Kotlin's `val`/`var` declarations. Finds the `variable_declaration` child, extracts the name via `_extract_property_name` (looks for `simple_identifier`), and finds the value via `_find_property_value` (scans children after `=`). Emits `STORE_VAR`. Without an initializer, stores `CONST "None"`.

### `_extract_property_name(var_decl_node) -> str`
Finds `simple_identifier` child in a `variable_declaration` node. Returns `"__unknown"` if none found.

### `_find_property_value(node)`
Scans children of a `property_declaration` for `=`, then returns the first named child after it.

### `_lower_kotlin_assignment(node)`
Handles Kotlin assignment which uses `directly_assignable_expression` and `expression` field names. Falls back to positional children if field lookup fails. Delegates to `_lower_store_target`.

### `_lower_kotlin_assignment_expr(node) -> str`
Expression-context wrapper for assignment. Calls `_lower_kotlin_assignment` then returns a `CONST "None"` register (Kotlin assignments are not value-producing in the language, but the IR needs a register).

### `_lower_function_decl(node)`
Locates `simple_identifier` (name), `function_value_parameters`, and `function_body` children by type (not field name). Creates function label, lowers params via `_lower_kotlin_params`, lowers body via `_lower_function_body`, emits implicit return, and registers function reference.

### `_lower_kotlin_params(params_node)`
Walks `parameter` children. For each, finds `simple_identifier` child and emits `SYMBOLIC("param:name")` + `STORE_VAR`.

### `_lower_function_body(body_node)`
Unwraps the `function_body` node which wraps the actual block or expression. Skips `{`, `}`, `=` tokens, lowers remaining named children as statements.

### `_lower_class_decl(node)`
Finds `type_identifier` (name) and `class_body`/`enum_class_body` by type. Emits class label structure. Dispatches body to either `_lower_enum_class_body` or `_lower_class_body_with_companions`.

### `_lower_class_body_with_companions(node)`
Iterates class body children. `companion_object` children are lowered via `_lower_companion_object`; all others go through `_lower_stmt`.

### `_lower_companion_object(node)`
Finds the `class_body` child inside a companion object and lowers it as a block.

### `_lower_kotlin_call(node) -> str`
Handles Kotlin's `call_expression` which has a callee (first named child) and a `call_suffix` containing `value_arguments`. Three paths: (1) callee is `navigation_expression` -> `CALL_METHOD`; (2) callee is `simple_identifier` -> `CALL_FUNCTION`; (3) dynamic target -> `CALL_UNKNOWN`.

### `_extract_kotlin_args(args_node) -> list[str]`
Walks `value_argument` children, unwrapping each to its inner named child. Also handles bare named children that are not wrapped.

### `_lower_navigation_expr(node) -> str`
Handles `obj.field` member access. Lowers first named child as object, uses last named child text as field name, emits `LOAD_FIELD`.

### `_lower_if_expr(node) -> str`
Value-producing `if`. Uses positional named children: `children[0]` is condition, `children[1]` is consequence, `children[2]` (optional) is alternative. Branches to true/false labels, stores results in synthetic `__if_result_N` variable, loads at end. Uses `_lower_control_body` for each branch.

### `_lower_if_stmt(node)`
Thin wrapper -- calls `_lower_if_expr` and discards the return register.

### `_lower_statements_expr(node) -> str`
Lowers a `statements` node in expression context: all children except the last are lowered as statements, the last is lowered as an expression and its register is returned. Empty nodes return `CONST "None"`.

### `_lower_control_body(body_node) -> str`
Lowers a `control_structure_body` or block, returning the register of the last expression. Filters out braces, semicolons, comments, noise. All but last child lowered as statements, last as expression. Returns `CONST "None"` for empty bodies.

### `_lower_while_stmt(node)`
Finds condition (first named child) and body (`control_structure_body` type). Standard while-loop IR with `BRANCH_IF`. Pushes loop context for break/continue.

### `_lower_for_stmt(node)`
Finds loop variable (`variable_declaration` or `simple_identifier`), iterable (expression after `in` keyword via `_find_for_iterable`), and body (`control_structure_body`). Lowers as index-based loop: `idx=0`, `len=len(iterable)`, `while idx < len { var = iterable[idx]; body; idx++ }`.

### `_find_for_iterable(node)`
Scans children for the `in` keyword text, then returns the next named child that is not `control_structure_body`.

### `_extract_for_var_name(var_node) -> str`
Returns text for `simple_identifier`, or finds `simple_identifier` child for other node types.

### `_lower_when_expr(node) -> str`
Lowers Kotlin `when` (pattern matching). Extracts subject from `when_subject` child. For each `when_entry`: extracts `when_condition` (compared with `BINOP("==")` + `BRANCH_IF`), and body from `control_structure_body` or direct children. Each arm stores result in `__when_result_N`. Entries without conditions are `else` branches (unconditional `BRANCH`). Returns `LOAD_VAR` of result at end label.

### `_lower_jump_expr(node)`
Dispatches based on text prefix: `return` -> `RETURN`, `throw` -> `THROW` (via `_lower_raise_or_throw`), `break` -> `_lower_break`, `continue` -> `_lower_continue`. Logs warning for unrecognized jump expressions.

### `_lower_jump_as_expr(node) -> str`
Expression-context wrapper for jump: calls `_lower_jump_expr` then returns `CONST "None"`.

### `_lower_postfix_expr(node) -> str`
Dispatches by text content: `++`/`--` -> `_lower_update_expr`, `!!` suffix -> `_lower_not_null_assertion`, else -> `_lower_const_literal` fallback.

### `_lower_not_null_assertion(node) -> str`
Lowers `expr!!` as `UNOP("!!", expr_reg)`.

### `_lower_lambda_literal(node) -> str`
Creates function body with label `func___lambda_N`. Body children are filtered (skip braces, `->`, comments), lowered as statements. Emits implicit return, returns function reference constant.

### `_lower_store_target(target, val_reg, parent_node)`
Overrides base with Kotlin-specific target types:
- `simple_identifier` -> `STORE_VAR`
- `navigation_expression` -> `STORE_FIELD` (extracts object + field from named children)
- `indexing_expression` -> `STORE_INDEX` (extracts object + index from `indexing_suffix`)
- `directly_assignable_expression` -> checks for `indexing_suffix` child (-> `STORE_INDEX`) or unwraps inner named child recursively
- else -> `STORE_VAR` fallback

### `_extract_try_parts(node)`
Extracts try body (`statements` or `control_structure_body`), catch clauses from `catch_block` children (two `simple_identifier` children: first is type, second is variable name; body is `statements`/`control_structure_body`), and finally from `finally_block`. Returns `(body_node, catch_clauses, finally_node)`.

### `_lower_try_stmt(node)`
Delegates to `_extract_try_parts` then `BaseFrontend._lower_try_catch`.

### `_lower_try_expr(node) -> str`
Expression-context wrapper: calls `_lower_try_stmt`, returns `CONST "None"`.

### `_lower_check_expr(node) -> str`
Lowers `is`/`!is` type checks as `CALL_FUNCTION("is", expr_reg, type_text)`. Uses first and last named children.

### `_lower_do_while_stmt(node)`
Lowers `do { body } while (cond)`. Body is `control_structure_body`; condition is the first named child that is not the body. Pushes loop context with `continue_label=cond_label` so `continue` jumps to condition evaluation.

### `_lower_object_decl(node)`
Lowers Kotlin singleton `object Name { ... }`. Finds `type_identifier` (name) and `class_body`. Emits class-style label structure, lowers body, then emits `NEW_OBJECT(obj_name)` + `STORE_VAR` (unlike classes which use `CLASS_REF_TEMPLATE`).

### `_lower_enum_class_body(node)`
Iterates children: `enum_entry` -> `_lower_enum_entry`; other named non-punctuation -> `_lower_stmt`.

### `_lower_enum_entry(node)`
Emits `NEW_OBJECT("enum:EntryName")` + `STORE_VAR(entry_name, reg)` for each enum constant.

### `_lower_elvis_expr(node) -> str`
Lowers `x ?: default` as `BINOP("?:", left_reg, right_reg)`.

### `_lower_infix_expr(node) -> str`
Lowers `a to b`, `x until y` etc. Expects 3 named children: left, infix function name, right. Emits `CALL_FUNCTION(infix_name, left_reg, right_reg)`.

### `_lower_indexing_expr(node) -> str`
Lowers `collection[index]`. First named child is the collection; index is inside `indexing_suffix` child. Emits `LOAD_INDEX(obj_reg, idx_reg)`.

### `_lower_as_expr(node) -> str`
Lowers `expr as Type` or `expr as? Type` as `CALL_FUNCTION("as", expr_reg, type_name)`.

### `_lower_symbolic_node(node) -> str`
Fallback for `object_literal` and `range_expression`. Emits `SYMBOLIC("node_type:text[:60]")`.

## Canonical Literal Handling

| Kotlin AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based dispatch) |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |

Kotlin uses a single `boolean_literal` node type for both `true` and `false`, so it uses `_lower_canonical_bool` which inspects the node text to determine which canonical value to emit.

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

- **Expression-oriented duality**: Many Kotlin constructs (`if`, `when`, `try`) appear in both `_EXPR_DISPATCH` and `_STMT_DISPATCH`. The statement handlers are thin wrappers that call the expression handler and discard the register.
- **No `ATTRIBUTE_NODE_TYPE` override**: Unlike Java/Scala which override attribute constants, Kotlin handles member access entirely through `_lower_navigation_expr` and the `_lower_store_target` override. The base `_lower_attribute` is never invoked.
- **Property declarations**: Kotlin `val`/`var` use a different structure from Java local variable declarations. The value is found by scanning for `=` rather than using a field name, because tree-sitter Kotlin does not expose a `value` field on `property_declaration`.
- **Jump expression polymorphism**: Kotlin unifies `return`, `throw`, `break`, and `continue` under a single `jump_expression` node type. The frontend dispatches by inspecting the text prefix.
- **`when` as equality chain**: Similar to Java switch lowering, `when` is lowered as a linear chain of `BINOP("==")` comparisons. Entries without conditions become unconditional branches (the `else` arm).
- **Object declarations**: Kotlin singletons are lowered differently from classes -- they use `NEW_OBJECT` instead of `CLASS_REF_TEMPLATE` since they represent instances, not class references.
- **Companion objects**: Lowered by simply lowering the companion's `class_body` as a block, effectively hoisting its members to the enclosing scope.
- **Enum entries as objects**: Each enum entry is lowered as `NEW_OBJECT("enum:EntryName")` + `STORE_VAR`, giving each entry its own object identity.
- **For-each as index loop**: Like Java, for-each is lowered as an index-based while loop with `len()` and `LOAD_INDEX`. The index variable is stored as `__for_idx`.
- **Elvis operator**: `?:` is emitted as a `BINOP` rather than being desugared into branches, since the VM handles it directly.
- **Infix functions**: `a to b` is lowered as `CALL_FUNCTION("to", a, b)` -- the infix function name is the middle named child.
- **`as` expression**: Type casts are lowered as `CALL_FUNCTION("as", expr, type_name)` rather than being transparent like Java casts.
- **Catch blocks**: Kotlin tree-sitter produces `catch_block` with two `simple_identifier` children -- first is the exception type, second is the variable name. This is extracted positionally.
- **`directly_assignable_expression`**: Kotlin wraps assignment targets in this node type. The `_lower_store_target` override unwraps it, checking for `indexing_suffix` (array assignment) or recursing on the inner node.
