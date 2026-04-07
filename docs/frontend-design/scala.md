# Scala Frontend

> `interpreter/frontends/scala/` -- Extends BaseFrontend

```
interpreter/frontends/scala/
  ├── frontend.py       # ScalaFrontend orchestrator (dispatch tables + constants)
  ├── node_types.py     # ScalaNodeType constants for tree-sitter node type strings
  ├── expressions.py    # Scala-specific expression lowerers (pure functions)
  ├── control_flow.py   # Scala-specific control flow lowerers (pure functions)
  └── declarations.py   # Scala-specific declaration lowerers (pure functions)
```

## Overview

The Scala frontend lowers tree-sitter Scala ASTs into flattened TAC IR. Scala is deeply expression-oriented: `if`, `match`, `try`, `throw`, blocks, and `for`-comprehensions all produce values. The frontend reflects this with expression-returning handlers for nearly all constructs. Key Scala-specific features handled include `val`/`var` definitions with pattern extraction (including tuple destructuring), `match` expressions (pattern matching with case class patterns, typed patterns, tuple patterns, infix patterns, and guards), `for` comprehensions with generators and guards, `object` definitions (singletons), `trait` definitions, case classes, `do-while`, lambda expressions, tuple expressions, `throw` as an expression, string interpolation, abstract function declarations, and loop/break/continue as expressions.

## Class Hierarchy

```
Frontend (abstract)
  -> BaseFrontend (_base.py)
       -> ScalaFrontend (scala/frontend.py)
```

Nothing extends `ScalaFrontend`. It inherits common lowering infrastructure from `BaseFrontend` and delegates language-specific lowering to pure functions in the `expressions`, `control_flow`, and `declarations` modules, plus shared functions from `common.expressions`, `common.control_flow`, `common.assignments`, and `common.exceptions`.

## Grammar Constants (`_build_constants()`)

| Field | BaseFrontend Default | Scala Value |
|---|---|---|
| `default_return_value` | `"None"` | `"()"` |
| `call_function_field` | `"function"` | `"function"` (same) |
| `call_arguments_field` | `"arguments"` | `"arguments"` (same) |
| `attr_object_field` | `"object"` | `"value"` |
| `attr_attribute_field` | `"attribute"` | `"field"` |
| `attribute_node_type` | `"attribute"` | `ScalaNodeType.FIELD_EXPRESSION` (`"field_expression"`) |
| `assign_left_field` | `"left"` | `"left"` (same) |
| `assign_right_field` | `"right"` | `"right"` (same) |
| `comment_types` | `frozenset({"comment"})` | `frozenset({"comment", "block_comment"})` |
| `noise_types` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` |
| `block_node_types` | `frozenset()` | `frozenset({"block", "template_body", "compilation_unit"})` |

The `default_return_value` of `"()"` reflects Scala's `Unit` type -- the implicit return value for functions that do not explicitly return.

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `floating_point_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `string` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `unit` | `common_expr.lower_const_literal` | `CONST "()"` |
| `infix_expression` | `common_expr.lower_binop` | `BINOP` |
| `prefix_expression` | `common_expr.lower_unop` | `UNOP` |
| `parenthesized_expression` | `common_expr.lower_paren` | (unwraps inner expression) |
| `call_expression` | `common_expr.lower_call` | `CALL_METHOD`, `CALL_FUNCTION`, or `CALL_UNKNOWN` |
| `field_expression` | `scala_expr.lower_field_expr` | `LOAD_FIELD` |
| `if_expression` | `scala_expr.lower_if_expr` | `BRANCH_IF` + `DECL_VAR` + `LOAD_VAR` (value-producing) |
| `match_expression` | `scala_expr.lower_match_expr` | equality chain + `DECL_VAR` + `LOAD_VAR` |
| `block` | `scala_expr.lower_block_expr` | lowers stmts, returns last expr's register |
| `assignment_expression` | `scala_expr.lower_assignment_expr` | `STORE_VAR`/`STORE_FIELD` + returns val_reg |
| `return_expression` | `scala_expr.lower_return_expr` | `RETURN` + returns val_reg |
| `this` | `common_expr.lower_identifier` | `LOAD_VAR "this"` |
| `super` | `common_expr.lower_identifier` | `LOAD_VAR "super"` |
| `wildcard` | `scala_expr.lower_wildcard` | `SYMBOLIC "wildcard:_"` |
| `tuple_expression` | `scala_expr.lower_tuple_expr` | `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element |
| `string_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `interpolated_string_expression` | `scala_expr.lower_scala_interpolated_string` | String interpolation via parts |
| `interpolated_string` | `scala_expr.lower_scala_interpolated_string_body` | String interpolation body |
| `lambda_expression` | `scala_expr.lower_lambda_expr` | `BRANCH`/`LABEL` func body + `CONST <function:...>` |
| `instance_expression` | `scala_expr.lower_new_expr` | `CALL_CTOR(TypeName, ...args)` |
| `generic_type` | `scala_expr.lower_symbolic_node` | `SYMBOLIC` |
| `type_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `try_expression` | `scala_expr.lower_try_expr` | try/catch/finally + `CONST "None"` |
| `throw_expression` | `scala_expr.lower_throw_expr` | `THROW` + returns val_reg |
| `while_expression` | `scala_expr.lower_loop_as_expr` | (lowers as stmt, returns `CONST "None"`) |
| `for_expression` | `scala_expr.lower_loop_as_expr` | (lowers as stmt, returns `CONST "None"`) |
| `do_while_expression` | `scala_expr.lower_loop_as_expr` | (lowers as stmt, returns `CONST "None"`) |
| `break_expression` | `scala_expr.lower_break_as_expr` | `BRANCH` to break target + `CONST "None"` |
| `continue_expression` | `scala_expr.lower_continue_as_expr` | `BRANCH` to continue label + `CONST "None"` |
| `operator_identifier` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `arguments` | `common_expr.lower_paren` | (unwraps inner expression) |
| `case_class_pattern` | `scala_expr.lower_case_class_pattern` | `NEW_OBJECT("pattern:ClassName")` + `STORE_INDEX` per binding |
| `typed_pattern` | `scala_expr.lower_typed_pattern` | Lowers the identifier, ignores type |
| `guard` | `scala_expr.lower_guard` | Lowers the condition expression |
| `tuple_pattern` | `scala_expr.lower_tuple_pattern_expr` | `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element |
| `case_block` | `scala_expr.lower_block_expr` | lowers stmts, returns last expr's register |
| `infix_pattern` | `scala_expr.lower_infix_pattern` | `BINOP(op, left, right)` |
| `case_clause` | `scala_expr.lower_case_clause_expr` | Lowers the case body as expression |

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `val_definition` | `scala_decl.lower_val_def` | `STORE_VAR` |
| `var_definition` | `scala_decl.lower_var_def` | `STORE_VAR` |
| `function_definition` | `scala_decl.lower_function_def_stmt` | `BRANCH`/`LABEL` func + params + `RETURN` + `DECL_VAR` |
| `class_definition` | `scala_decl.lower_class_def` | `BRANCH`/`LABEL` class + hoisted body + `DECL_VAR` |
| `object_definition` | `scala_decl.lower_object_def` | `BRANCH`/`LABEL` class + hoisted body + `DECL_VAR` |
| `if_expression` | `scala_cf.lower_if_stmt` | (delegates to `scala_expr.lower_if_expr`, discards result) |
| `while_expression` | `scala_cf.lower_while` | `BRANCH_IF` loop |
| `match_expression` | `scala_cf.lower_match_stmt` | (delegates to `scala_expr.lower_match_expr`, discards result) |
| `expression_statement` | `common_assign.lower_expression_statement` | (unwraps inner expression) |
| `block` | `lambda ctx, node: ctx.lower_block(node)` | (iterates children) |
| `template_body` | `lambda ctx, node: ctx.lower_block(node)` | (iterates children) |
| `compilation_unit` | `lambda ctx, node: ctx.lower_block(node)` | (iterates children) |
| `import_declaration` | `lambda ctx, node: None` | (skipped) |
| `package_clause` | `lambda ctx, node: None` | (skipped) |
| `break_expression` | `common_cf.lower_break` | `BRANCH` to break target |
| `continue_expression` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `try_expression` | `scala_cf.lower_try_stmt` | `LABEL`/`BRANCH` try/catch/finally blocks |
| `for_expression` | `scala_cf.lower_for_expr` | generator loop with guards |
| `trait_definition` | `scala_decl.lower_trait_def` | `BRANCH`/`LABEL` class-like + `DECL_VAR` |
| `case_class_definition` | `scala_decl.lower_class_def` | same as `class_definition` |
| `lazy_val_definition` | `scala_decl.lower_val_def` | same as `val_definition` |
| `do_while_expression` | `scala_cf.lower_do_while` | body-first loop with `BRANCH_IF` at end |
| `type_definition` | `lambda ctx, node: None` | (skipped) |
| `function_declaration` | `scala_decl.lower_function_declaration` | Abstract function stub |

## Language-Specific Lowering Methods

### `scala_decl.lower_val_def(ctx, node)` / `scala_decl.lower_var_def(ctx, node)`
Handles `val x = expr`, `lazy val x = expr`, and `var x = expr`. Extracts variable name from the `pattern` field via `_extract_pattern_name`, lowers the `value` field. Supports tuple destructuring via `tuple_pattern` (lowers as `LOAD_INDEX` per element). Without initializer, stores `CONST "None"`. Emits `STORE_VAR(var_name, val_reg)`. Seeds type hints.

### `scala_decl._extract_pattern_name(ctx, pattern_node) -> str`
Returns `"__unknown"` for `None`. If the pattern is an `identifier`, returns its text. Otherwise searches for an `identifier` child (handles `typed_pattern` wrappers like `x: Int`). Falls back to full node text.

### `scala_expr.lower_assignment_expr(ctx, node) -> str`
Handles `x = expr` in expression context. Lowers right side, stores via `scala_expr.lower_scala_store_target`, returns the value register.

### `scala_expr.lower_field_expr(ctx, node) -> str`
Lowers `obj.field` using Scala-specific field names (`value`/`field`). Emits `LOAD_FIELD(obj_reg, field_name)`. Falls back to `lower_const_literal` if either child is missing.

### `scala_expr.lower_if_expr(ctx, node) -> str`
Value-producing `if`. Uses `condition`/`consequence`/`alternative` fields. Creates synthetic `__if_result_N` variable. True branch stored via `_lower_body_as_expr`, false branch likewise. Returns `LOAD_VAR` of result at end label. Without alternative, branches to end label from condition.

### `scala_cf.lower_if_stmt(ctx, node)`
Statement wrapper -- calls `scala_expr.lower_if_expr`, discards register.

### `scala_expr._lower_body_as_expr(ctx, body_node) -> str`
Returns `CONST "None"` for `None`. If body is a `block`, delegates to `scala_expr.lower_block_expr`. Otherwise lowers as expression.

### `scala_cf.lower_while(ctx, node)`
Custom override. Uses `condition`/`body` fields. Handles `None` condition gracefully. Does **not** push loop context (no break/continue support via stacks in this override).

### `scala_expr.lower_match_expr(ctx, node) -> str`
Value-producing `match`. Extracts `value` (subject) and `body` (case clauses) fields. For each `case_clause`: extracts `pattern` and `body` fields. Wildcard patterns (`_`) branch unconditionally; others use `BINOP("==")` + `BRANCH_IF`. Each arm stores to `__match_result_N`. Returns `LOAD_VAR` of result at end.

### `scala_cf.lower_match_stmt(ctx, node)`
Statement wrapper -- calls `scala_expr.lower_match_expr`, discards register.

### `scala_expr.lower_block_expr(ctx, node) -> str`
Lowers a `{ ... }` block as an expression. Filters out braces, semicolons, comments, noise. All but last child lowered as statements, last child lowered as expression (its register returned). Empty blocks return `CONST "None"`.

### `scala_decl.lower_function_def(ctx, node, inject_this=False)`
Uses `name`/`parameters`/`body` fields. Creates function label, lowers parameters via `scala_decl.lower_scala_params`, lowers body. Expression-bodied functions (`def f = 42`) return the expression directly; block-bodied functions get an implicit return of `DEFAULT_RETURN_VALUE` (`"()"`). Registers function reference. Optionally injects `this` parameter for instance methods.

### `scala_decl.lower_function_def_stmt(ctx, node)`
Statement-dispatch wrapper: calls `lower_function_def(ctx, node)`.

### `scala_decl.lower_function_declaration(ctx, node)`
Lowers abstract function declarations (no body) as function stubs with immediate return of `default_return_value`.

### `scala_decl.lower_scala_params(ctx, params_node)`
Walks `parameter` children. For each, extracts `name` field and emits `SYMBOLIC("param:name")` + `DECL_VAR`. Extracts and seeds type hints.

### `scala_decl.lower_class_def(ctx, node)`
Uses `name`/`body` fields. Emits class label structure (notably **without** lowering body between labels -- the labels are placed consecutively). Then registers class reference via `DECL_VAR`. If body exists, hoists it via `_lower_class_body_hoisted` with `inject_this=True`. Extracts parent classes/traits from `extends_clause`.

### `scala_decl.lower_object_def(ctx, node)`
Identical structure to `lower_class_def` for Scala singleton `object` definitions. Uses `CLASS_LABEL_PREFIX`/`CLASS_REF_TEMPLATE` same as classes. Hoists body without `inject_this`.

### `scala_decl._lower_class_body_hoisted(ctx, node, inject_this=False)`
Hoists class body children to top level. Emits function definitions first (types in `_CLASS_BODY_FUNC_TYPES = frozenset({"function_definition"})`), then field initializers and other statements. Functions get `inject_this` forwarded. This ensures function references are registered before code that may call them.

### `scala_expr.lower_return_expr(ctx, node) -> str`
Lowers `return expr` as both a `RETURN` instruction and an expression (returns the value register). Without a return value, uses `DEFAULT_RETURN_VALUE` (`"()"`).

### `scala_expr.lower_wildcard(ctx, node) -> str`
Emits `SYMBOLIC("wildcard:_")`. Used in match patterns and other contexts.

### `scala_expr.lower_tuple_expr(ctx, node) -> str`
Lowers `(a, b, c)` as `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element. Filters out parentheses and commas.

### `scala_expr.lower_lambda_expr(ctx, node) -> str`
Creates function body with label `func___lambda_N`. Extracts lambda parameters from `bindings` -> `binding` -> `identifier`. All named non-comment children (except bindings) are lowered; last expression is implicitly returned. Emits implicit return of `"()"`, returns function reference constant.

### `scala_expr.lower_new_expr(ctx, node) -> str`
Lowers `new Type(...)` (via `instance_expression`). Extracts type name from first named child, emits `CALL_CTOR(TypeName, ...args)`. Defaults to `"Object"` if no children. Seeds register type.

### `scala_expr.lower_scala_interpolated_string(ctx, node) -> str`
Lowers `interpolated_string_expression` (s"...", f"...", raw"..."). Delegates to `lower_scala_interpolated_string_body` for the inner `interpolated_string` child.

### `scala_expr.lower_scala_interpolated_string_body(ctx, node) -> str`
Extracts literal gaps between `interpolation` children from raw source bytes, lowers each interpolation expression, then concatenates via `common_expr.lower_interpolated_string_parts`.

### `scala_expr.lower_loop_as_expr(ctx, node) -> str`
Lowers while/for/do-while in expression position: lowers as statement, then returns `CONST "None"`.

### `scala_expr.lower_break_as_expr(ctx, node) -> str` / `scala_expr.lower_continue_as_expr(ctx, node) -> str`
Lower break/continue in expression position: perform the control flow action, then return `CONST "None"`.

### `scala_cf.lower_for_expr(ctx, node)`
Lowers for-comprehensions: `for (generators) body` or `for (generators) yield body`. Extracts `enumerators` child, then generators (`enumerator` children) and guards (`guard` children). For each generator: extracts binding (first named child) and iterable (last named child), calls `iter()` on iterable. Creates loop label. Each iteration calls `next()` and stores to binding variable. Guards are lowered as `BRANCH_IF` that skip back to loop start on failure. Then lowers body. Loops back unconditionally.

### `scala_decl.lower_trait_def(ctx, node)`
Lowers `trait` definitions identically to class definitions, but **does** lower body between labels (unlike `lower_class_def` which hoists body outside). Extracts parent traits from `extends_clause`.

### `scala_cf.lower_do_while(ctx, node)`
Lowers `do { body } while (condition)`. Body-first execution: `LABEL body` -> body -> condition -> `BRANCH_IF(cond, body, end)` -> `LABEL end`. Without condition, branches unconditionally back to body (infinite loop). Does **not** push loop context.

### `scala_expr.lower_scala_store_target(ctx, target, val_reg, parent_node)`
Handles Scala-specific target types:
- `identifier` -> `STORE_VAR`
- `field_expression` -> `STORE_FIELD` (using `value`/`field` children)
- else -> `STORE_VAR` fallback (no subscript/index support in this override)

### `scala_cf._extract_try_parts(ctx, node)`
Extracts try body (via `body` field), catch clauses from `catch_clause` children. Each catch clause has a `case_block` containing `case_clause` entries. Each case's pattern is inspected for `identifier` (variable name) and `type_identifier` (exception type). Also extracts `finally_clause` body.

### `scala_cf.lower_try_stmt(ctx, node)`
Delegates to `_extract_try_parts` then `common.exceptions.lower_try_catch`.

### `scala_expr.lower_try_expr(ctx, node) -> str`
Expression-context wrapper: calls `scala_cf.lower_try_stmt`, returns `CONST "None"`.

### `scala_expr.lower_throw_expr(ctx, node) -> str`
Lowers `throw expr` as a `THROW` instruction. Unlike Java's statement-only throw, this returns the value register since Scala `throw` is an expression. Without an expression, throws `DEFAULT_RETURN_VALUE` (`"()"`).

### `scala_expr.lower_symbolic_node(ctx, node) -> str`
Fallback for `generic_type`. Emits `SYMBOLIC("node_type:text[:60]")`.

### `scala_expr.lower_case_class_pattern(ctx, node) -> str`
Lowers case class patterns like `Circle(r)` in match arms as `NEW_OBJECT("pattern:ClassName")` + `STORE_INDEX` per inner binding.

### `scala_expr.lower_typed_pattern(ctx, node) -> str`
Lowers typed pattern `i: Int` by lowering the identifier and ignoring the type.

### `scala_expr.lower_guard(ctx, node) -> str`
Lowers guard clause `if condition` in match by lowering the condition expression.

### `scala_expr.lower_tuple_pattern_expr(ctx, node) -> str`
Lowers `(a, b)` pattern in match as `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element.

### `scala_expr.lower_infix_pattern(ctx, node) -> str`
Lowers `head :: tail` infix pattern as `BINOP(op, left, right)` where `op` comes from the `operator_identifier` child.

### `scala_expr.lower_case_clause_expr(ctx, node) -> str`
Lowers `case_clause` in expression context by lowering the body via `_lower_body_as_expr`.

## Canonical Literal Handling

| Scala AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` (text-based dispatch) |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |

Like Kotlin, Scala uses a single `boolean_literal` node type, dispatched through `lower_canonical_bool` which inspects the lowercase text.

The `unit` literal (`()`) is dispatched to `common_expr.lower_const_literal` and emitted as raw `CONST "()"` (not canonicalized -- it represents Scala's Unit value).

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

- **`default_return_value = "()"` (Unit)**: Scala functions that do not explicitly return produce `()` (Unit), not `None`. This is the only frontend that changes the default return value from `"None"`.
- **Class body hoisting**: `lower_class_def` and `lower_object_def` place both class labels consecutively (empty class body in the label structure), then hoist body members via `_lower_class_body_hoisted`. This differs from Java which lowers body between labels. The hoisting partitions functions first, then rest.
- **`_CLASS_BODY_FUNC_TYPES = frozenset({"function_definition"})`**: Only `function_definition` is hoisted first; Scala does not have separate constructor declarations like Java.
- **Trait as class**: `lower_trait_def` uses the same label/reference pattern as classes but **does** lower body between labels (unlike `lower_class_def` which hoists body outside). This is a subtle structural difference.
- **`case_class_definition` and `lazy_val_definition`**: Both reuse existing handlers -- `lower_class_def` and `lower_val_def` respectively.
- **`function_declaration` (abstract)**: Lowered as a function stub with immediate return of `default_return_value`, creating a function reference but no meaningful body.
- **`match` as equality chain**: Like Kotlin's `when`, Scala `match` is lowered as linear `BINOP("==")` comparisons. Wildcard (`_`) patterns branch unconditionally. Advanced patterns are supported: case class patterns (`Circle(r)`) as `NEW_OBJECT("pattern:...")` + `STORE_INDEX`, typed patterns (`i: Int`) lower the identifier ignoring the type, tuple patterns as `NEW_ARRAY("tuple", ...)`, infix patterns (`head :: tail`) as `BINOP`, and guards as conditional branches.
- **For-comprehension**: The `lower_for_expr` generates a loop that calls `iter()` on iterables and `next()` each iteration. Guards are lowered as conditional branches back to the loop start. This is a simplified model that does not capture Scala's full flatMap/map desugaring.
- **`throw` as expression**: Scala's `throw` is an expression that returns a register (of type `Nothing`). The frontend preserves this by having `lower_throw_expr` return the value register.
- **Loop/break/continue as expressions**: `while_expression`, `for_expression`, `do_while_expression`, `break_expression`, and `continue_expression` all appear in the expression dispatch table. They are lowered as statements and return `CONST "None"`.
- **No loop stack usage in `lower_while` and `lower_do_while`**: The Scala-specific while and do-while overrides do not call `push_loop`/`pop_loop`, meaning `break`/`continue` may not correctly target these loops. However, `break_expression` and `continue_expression` are still in the statement dispatch table via `common_cf.lower_break`/`common_cf.lower_continue`.
- **`block` in `block_node_types`**: Setting `block_node_types = frozenset({"block", "template_body", "compilation_unit"})` enables block-level dispatch for these container node types.
- **Scala's `field_expression`**: Uses `value`/`field` field names instead of `object`/`attribute`, requiring both constant overrides and a custom `lower_field_expr` method.
- **`instance_expression` for `new`**: Scala's `new Type(...)` is tree-sitter node type `instance_expression`, lowered as `CALL_CTOR(TypeName, ...args)` with constructor arguments extracted from `arguments`. Register type is seeded.
- **`template_body` and `compilation_unit`**: Both are mapped to `ctx.lower_block`, serving as top-level and class-body containers respectively.
- **String interpolation**: `s"Hello, $name"` is decomposed by extracting literal gaps between `interpolation` children from raw source bytes, then concatenating via `lower_interpolated_string_parts`.
- **Tuple destructuring**: `val (a, b) = expr` is supported via `tuple_pattern` detection in `_lower_val_or_var_def`, emitting `LOAD_INDEX` per element.
- **Pure function architecture**: All lowering logic lives in pure functions taking `(ctx: TreeSitterEmitContext, node)` instead of instance methods. The `ScalaFrontend` class is a thin orchestrator that builds dispatch tables and constants.
- **Instance method `this` injection**: `lower_function_def` accepts an `inject_this` parameter; class body methods get `this` injected via `_lower_class_body_hoisted`.
- **Scoping model** -- Uses `BLOCK_SCOPED = True` (LLVM-style name mangling). Shadowed variables in nested blocks, for-comprehension variables, and catch clause variables are renamed (`x` → `x$1`) to disambiguate. See [base-frontend.md](base-frontend.md#block-scopes) for the general mechanism.
