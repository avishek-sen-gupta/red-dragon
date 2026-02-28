# Scala Frontend

> `interpreter/frontends/scala.py` -- Extends BaseFrontend -- ~850 lines

## Overview

The Scala frontend lowers tree-sitter Scala ASTs into flattened TAC IR. Scala is deeply expression-oriented: `if`, `match`, `try`, `throw`, blocks, and `for`-comprehensions all produce values. The frontend reflects this with expression-returning handlers for nearly all constructs. Key Scala-specific features handled include `val`/`var` definitions with pattern extraction, `match` expressions (pattern matching), `for` comprehensions with generators and guards, `object` definitions (singletons), `trait` definitions, case classes, `do-while`, lambda expressions, tuple expressions, and `throw` as an expression.

## Class Hierarchy

```
Frontend (abstract)
  -> BaseFrontend (_base.py)
       -> ScalaFrontend (scala.py)
```

Nothing extends `ScalaFrontend`. It inherits common lowering infrastructure from `BaseFrontend` including register/label allocation, `_emit`, `_lower_block`, `_lower_stmt`, `_lower_expr`, `_lower_binop`, `_lower_unop`, `_lower_paren`, `_lower_call`, `_lower_break`, `_lower_continue`, `_lower_try_catch`, `_lower_expression_statement`, etc.

## Overridden Constants

| Constant | BaseFrontend Default | ScalaFrontend Value |
|---|---|---|
| `DEFAULT_RETURN_VALUE` | `"None"` | `"()"` |
| `CALL_FUNCTION_FIELD` | `"function"` | `"function"` (same) |
| `CALL_ARGUMENTS_FIELD` | `"arguments"` | `"arguments"` (same) |
| `ATTR_OBJECT_FIELD` | `"object"` | `"value"` |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"field"` |
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"field_expression"` |
| `ASSIGN_LEFT_FIELD` | `"left"` | `"left"` (same) |
| `ASSIGN_RIGHT_FIELD` | `"right"` | `"right"` (same) |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment", "block_comment"})` |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` |
| `BLOCK_NODE_TYPES` | `frozenset()` | `frozenset({"block"})` |

The `DEFAULT_RETURN_VALUE` of `"()"` reflects Scala's `Unit` type -- the implicit return value for functions that do not explicitly return.

## Expression Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `floating_point_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `string` | `_lower_const_literal` | `CONST` (raw text) |
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |
| `unit` | `_lower_const_literal` | `CONST "()"` |
| `infix_expression` | `_lower_binop` | `BINOP` |
| `prefix_expression` | `_lower_unop` | `UNOP` |
| `parenthesized_expression` | `_lower_paren` | (unwraps inner expression) |
| `call_expression` | `_lower_call` | `CALL_METHOD`, `CALL_FUNCTION`, or `CALL_UNKNOWN` |
| `field_expression` | `_lower_field_expr` | `LOAD_FIELD` |
| `if_expression` | `_lower_if_expr` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` (value-producing) |
| `match_expression` | `_lower_match_expr` | equality chain + `STORE_VAR` + `LOAD_VAR` |
| `block` | `_lower_block_expr` | lowers stmts, returns last expr's register |
| `assignment_expression` | `_lower_assignment_expr` | `STORE_VAR`/`STORE_FIELD` + returns val_reg |
| `return_expression` | `_lower_return_expr` | `RETURN` + returns val_reg |
| `this` | `_lower_identifier` | `LOAD_VAR "this"` |
| `super` | `_lower_identifier` | `LOAD_VAR "super"` |
| `wildcard` | `_lower_wildcard` | `SYMBOLIC "wildcard:_"` |
| `tuple_expression` | `_lower_tuple_expr` | `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element |
| `string_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `interpolated_string` | `_lower_const_literal` | `CONST` (raw text) |
| `lambda_expression` | `_lower_lambda_expr` | `BRANCH`/`LABEL` func body + `CONST <function:...>` |
| `instance_expression` | `_lower_new_expr` | `CALL_FUNCTION(TypeName)` |
| `generic_type` | `_lower_symbolic_node` | `SYMBOLIC` |
| `type_identifier` | `_lower_identifier` | `LOAD_VAR` |
| `try_expression` | `_lower_try_expr` | try/catch/finally + `CONST "None"` |
| `throw_expression` | `_lower_throw_expr` | `THROW` + returns val_reg |

## Statement Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `val_definition` | `_lower_val_def` | `STORE_VAR` |
| `var_definition` | `_lower_var_def` | `STORE_VAR` |
| `function_definition` | `_lower_function_def` | `BRANCH`/`LABEL` func + params + `RETURN` + `STORE_VAR` |
| `class_definition` | `_lower_class_def` | `BRANCH`/`LABEL` class + hoisted body + `STORE_VAR` |
| `object_definition` | `_lower_object_def` | `BRANCH`/`LABEL` class + hoisted body + `STORE_VAR` |
| `if_expression` | `_lower_if_stmt` | (delegates to `_lower_if_expr`, discards result) |
| `while_expression` | `_lower_while` | `BRANCH_IF` loop |
| `match_expression` | `_lower_match_stmt` | (delegates to `_lower_match_expr`, discards result) |
| `expression_statement` | `_lower_expression_statement` | (unwraps inner expression) |
| `block` | `_lower_block` | (iterates children) |
| `template_body` | `_lower_block` | (iterates children) |
| `compilation_unit` | `_lower_block` | (iterates children) |
| `import_declaration` | `lambda _: None` | (skipped) |
| `package_clause` | `lambda _: None` | (skipped) |
| `break_expression` | `_lower_break` | `BRANCH` to break target |
| `continue_expression` | `_lower_continue` | `BRANCH` to continue label |
| `try_expression` | `_lower_try_stmt` | `LABEL`/`BRANCH` try/catch/finally blocks |
| `for_expression` | `_lower_for_expr` | generator loop with guards |
| `trait_definition` | `_lower_trait_def` | `BRANCH`/`LABEL` class-like + `STORE_VAR` |
| `case_class_definition` | `_lower_class_def` | same as `class_definition` |
| `lazy_val_definition` | `_lower_val_def` | same as `val_definition` |
| `do_while_expression` | `_lower_do_while` | body-first loop with `BRANCH_IF` at end |
| `type_definition` | `lambda _: None` | (skipped) |

## Language-Specific Lowering Methods

### `_lower_val_def(node)`
Handles `val x = expr` and `lazy val x = expr`. Extracts variable name from the `pattern` field via `_extract_pattern_name`, lowers the `value` field. Without initializer, stores `CONST "None"`. Emits `STORE_VAR(var_name, val_reg)`.

### `_lower_var_def(node)`
Identical structure to `_lower_val_def`. Handles `var x = expr`.

### `_extract_pattern_name(pattern_node) -> str`
Returns `"__unknown"` for `None`. If the pattern is an `identifier`, returns its text. Otherwise searches for an `identifier` child (handles `typed_pattern` wrappers like `x: Int`). Falls back to full node text.

### `_lower_assignment_expr(node) -> str`
Handles `x = expr` in expression context. Lowers right side, stores via `_lower_store_target`, returns the value register.

### `_lower_field_expr(node) -> str`
Lowers `obj.field` using Scala-specific field names (`value`/`field`). Emits `LOAD_FIELD(obj_reg, field_name)`. Falls back to `_lower_const_literal` if either child is missing.

### `_lower_if_expr(node) -> str`
Value-producing `if`. Uses `condition`/`consequence`/`alternative` fields. Creates synthetic `__if_result_N` variable. True branch stored via `_lower_body_as_expr`, false branch likewise. Returns `LOAD_VAR` of result at end label. Without alternative, branches to end label from condition.

### `_lower_if_stmt(node)`
Statement wrapper -- calls `_lower_if_expr`, discards register.

### `_lower_body_as_expr(body_node) -> str`
Returns `CONST "None"` for `None`. If body is a `block`, delegates to `_lower_block_expr`. Otherwise lowers as expression.

### `_lower_while(node)`
Custom override (not the base `_lower_while`). Uses `condition`/`body` fields. Handles `None` condition gracefully. Does **not** push loop context (no break/continue support via stacks in this override).

### `_lower_match_expr(node) -> str`
Value-producing `match`. Extracts `value` (subject) and `body` (case clauses) fields. For each `case_clause`: extracts `pattern` and `body` fields. Wildcard patterns (`_`) branch unconditionally; others use `BINOP("==")` + `BRANCH_IF`. Each arm stores to `__match_result_N`. Returns `LOAD_VAR` of result at end.

### `_lower_match_stmt(node)`
Statement wrapper -- calls `_lower_match_expr`, discards register.

### `_lower_block_expr(node) -> str`
Lowers a `{ ... }` block as an expression. Filters out braces, semicolons, comments, noise. All but last child lowered as statements, last child lowered as expression (its register returned). Empty blocks return `CONST "None"`.

### `_lower_function_def(node)`
Uses `name`/`parameters`/`body` fields. Creates function label, lowers parameters via `_lower_scala_params`, lowers body, emits implicit return of `DEFAULT_RETURN_VALUE` (`"()"`), registers function reference.

### `_lower_scala_params(params_node)`
Walks `parameter` children. For each, extracts `name` field and emits `SYMBOLIC("param:name")` + `STORE_VAR`.

### `_lower_class_def(node)`
Uses `name`/`body` fields. Emits class label structure (notably **without** lowering body between labels -- the labels are placed consecutively). Then registers class reference via `STORE_VAR`. If body exists, hoists it via `_lower_class_body_hoisted`.

### `_lower_object_def(node)`
Identical structure to `_lower_class_def` for Scala singleton `object` definitions. Uses `CLASS_LABEL_PREFIX`/`CLASS_REF_TEMPLATE` same as classes.

### `_lower_class_body_hoisted(node)`
Hoists class body children to top level. Emits function definitions first (types in `_CLASS_BODY_FUNC_TYPES = frozenset({"function_definition"})`), then field initializers and other statements. This ensures function references are registered before code that may call them.

### `_lower_return_expr(node) -> str`
Lowers `return expr` as both a `RETURN` instruction and an expression (returns the value register). Without a return value, uses `DEFAULT_RETURN_VALUE` (`"()"`).

### `_lower_wildcard(node) -> str`
Emits `SYMBOLIC("wildcard:_")`. Used in match patterns and other contexts.

### `_lower_tuple_expr(node) -> str`
Lowers `(a, b, c)` as `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element. Filters out parentheses and commas.

### `_lower_lambda_expr(node) -> str`
Creates function body with label `func___lambda_N`. All named non-comment children are lowered as statements. Emits implicit return of `"()"`, returns function reference constant.

### `_lower_new_expr(node) -> str`
Lowers `new Type(...)` (via `instance_expression`). Extracts type name from first named child, emits `CALL_FUNCTION(TypeName)`. Defaults to `"Object"` if no children.

### `_lower_for_expr(node)`
Lowers for-comprehensions: `for (generators) body` or `for (generators) yield body`. Extracts `enumerators` child, then generators (`enumerator` children) and guards (`guard` children). For each generator: extracts binding (first named child) and iterable (last named child), calls `iter()` on iterable. Creates loop label. Each iteration calls `next()` and stores to binding variable. Guards are lowered as `BRANCH_IF` that skip back to loop start on failure. Then lowers body. Loops back unconditionally.

### `_lower_trait_def(node)`
Lowers `trait` definitions identically to class definitions, using `CLASS_LABEL_PREFIX`/`CLASS_REF_TEMPLATE`. Body is lowered between labels (unlike `_lower_class_def` which hoists body outside).

### `_lower_do_while(node)`
Lowers `do { body } while (condition)`. Body-first execution: `LABEL body` -> body -> condition -> `BRANCH_IF(cond, body, end)` -> `LABEL end`. Without condition, branches unconditionally back to body (infinite loop). Does **not** push loop context.

### `_lower_store_target(target, val_reg, parent_node)`
Overrides base with Scala-specific target types:
- `identifier` -> `STORE_VAR`
- `field_expression` -> `STORE_FIELD` (using `value`/`field` children)
- else -> `STORE_VAR` fallback (no subscript/index support in this override)

### `_extract_try_parts(node)`
Extracts try body (via `body` field), catch clauses from `catch_clause` children. Each catch clause has a `body` containing `case_clause` entries. Each case's pattern is inspected for `identifier` (variable name) and `type_identifier` (exception type). Also extracts `finally_clause` body.

### `_lower_try_stmt(node)`
Delegates to `_extract_try_parts` then `BaseFrontend._lower_try_catch`.

### `_lower_try_expr(node) -> str`
Expression-context wrapper: calls `_lower_try_stmt`, returns `CONST "None"`.

### `_lower_throw_expr(node) -> str`
Lowers `throw expr` as a `THROW` instruction. Unlike Java's statement-only throw, this returns the value register since Scala `throw` is an expression. Without an expression, throws `DEFAULT_RETURN_VALUE` (`"()"`).

### `_lower_symbolic_node(node) -> str`
Fallback for `generic_type`. Emits `SYMBOLIC("node_type:text[:60]")`.

## Canonical Literal Handling

| Scala AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based dispatch) |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |

Like Kotlin, Scala uses a single `boolean_literal` node type, dispatched through `_lower_canonical_bool` which inspects the lowercase text.

The `unit` literal (`()`) is dispatched to `_lower_const_literal` and emitted as raw `CONST "()"` (not canonicalized -- it represents Scala's Unit value).

## Example

**Scala source:**
```scala
def factorial(n: Int): Int = n match {
  case 0 => 1
  case _ => n * factorial(n - 1)
}
```

**Emitted IR (simplified):**
```
LABEL entry
BRANCH end_factorial_1
LABEL func_factorial_0
SYMBOLIC %0 "param:n"
STORE_VAR n, %0
LOAD_VAR %1, n
CONST %2, 0
BINOP %3, "==", %1, %2
BRANCH_IF %3, case_arm_2, case_next_3
LABEL case_arm_2
CONST %4, 1
STORE_VAR __match_result_4, %4
BRANCH match_end_4
LABEL case_next_3
SYMBOLIC %5 "wildcard:_"
BRANCH case_arm_5
LABEL case_arm_5
LOAD_VAR %6, n
LOAD_VAR %7, n
CONST %8, 1
BINOP %9, "-", %7, %8
CALL_FUNCTION %10, factorial, %9
BINOP %11, "*", %6, %10
STORE_VAR __match_result_4, %11
BRANCH match_end_4
LABEL case_next_6
LABEL match_end_4
LOAD_VAR %12, __match_result_4
CONST %13, "()"
RETURN %13
LABEL end_factorial_1
CONST %14, "<function:factorial@func_factorial_0>"
STORE_VAR factorial, %14
```

## Design Notes

- **`DEFAULT_RETURN_VALUE = "()"` (Unit)**: Scala functions that do not explicitly return produce `()` (Unit), not `None`. This is the only frontend that changes the default return value from `"None"`.
- **Class body hoisting**: `_lower_class_def` and `_lower_object_def` place both class labels consecutively (empty class body in the label structure), then hoist body members via `_lower_class_body_hoisted`. This differs from Java which lowers body between labels. The hoisting partitions functions first, then rest.
- **`_CLASS_BODY_FUNC_TYPES = frozenset({"function_definition"})`**: Only `function_definition` is hoisted first; Scala does not have separate constructor declarations like Java.
- **Trait as class**: `_lower_trait_def` uses the same label/reference pattern as classes but **does** lower body between labels (unlike `_lower_class_def`). This is a subtle structural difference.
- **`case_class_definition` and `lazy_val_definition`**: Both reuse existing handlers -- `_lower_class_def` and `_lower_val_def` respectively.
- **`match` as equality chain**: Like Kotlin's `when`, Scala `match` is lowered as linear `BINOP("==")` comparisons. Wildcard (`_`) patterns branch unconditionally. Complex pattern matching (guards, extractors, nested patterns) is not fully modeled -- only simple value equality.
- **For-comprehension**: The `_lower_for_expr` generates a loop that calls `iter()` on iterables and `next()` each iteration. Guards are lowered as conditional branches back to the loop start. This is a simplified model that does not capture Scala's full flatMap/map desugaring.
- **`throw` as expression**: Scala's `throw` is an expression that returns a register (of type `Nothing`). The frontend preserves this by having `_lower_throw_expr` return the value register.
- **No loop stack usage in `_lower_while` and `_lower_do_while`**: The Scala-specific while and do-while overrides do not call `_push_loop`/`_pop_loop`, meaning `break`/`continue` may not correctly target these loops. However, `break_expression` and `continue_expression` are still in the statement dispatch table.
- **`block` in `BLOCK_NODE_TYPES`**: Setting `BLOCK_NODE_TYPES = frozenset({"block"})` may affect how the base `_lower_block` handles block nodes, though this constant is not directly referenced in the base class code.
- **Scala's `field_expression`**: Uses `value`/`field` field names instead of `object`/`attribute`, requiring both constant overrides and a custom `_lower_field_expr` method.
- **`instance_expression` for `new`**: Scala's `new Type(...)` is tree-sitter node type `instance_expression`, lowered as a simple `CALL_FUNCTION(TypeName)` without arguments (arguments are not extracted in the current implementation).
- **`template_body` and `compilation_unit`**: Both are mapped to `_lower_block`, serving as top-level and class-body containers respectively.
