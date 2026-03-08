# Java Frontend

> `interpreter/frontends/java/` -- Extends BaseFrontend

```
interpreter/frontends/java/
  ├── frontend.py       # JavaFrontend orchestrator (dispatch tables + constants)
  ├── node_types.py     # JavaNodeType constants for tree-sitter node type strings
  ├── expressions.py    # Java-specific expression lowerers (pure functions)
  ├── control_flow.py   # Java-specific control flow lowerers (pure functions)
  └── declarations.py   # Java-specific declaration lowerers (pure functions)
```

## Overview

The Java frontend lowers tree-sitter Java ASTs into flattened three-address-code (TAC) IR. It handles the full breadth of Java's statement and expression grammar including classes, interfaces, enums, annotations, records, try/catch/finally, switch statements, enhanced for-loops, lambda expressions, method references, and ternary expressions. Java constructors are lowered with the canonical name `__init__`.

## Class Hierarchy

```
Frontend (abstract)
  -> BaseFrontend (_base.py)
       -> JavaFrontend (java/frontend.py)
```

Nothing extends `JavaFrontend`. It inherits all common lowering infrastructure from `BaseFrontend` (register/label allocation, `_emit`, `_lower_block`, `_lower_stmt`, `_lower_expr`) and delegates language-specific lowering to pure functions in the `expressions`, `control_flow`, and `declarations` modules, plus shared functions from `common.expressions`, `common.control_flow`, `common.assignments`, and `common.exceptions`.

## Grammar Constants (`_build_constants()`)

| Field | BaseFrontend Default | Java Value |
|---|---|---|
| `attribute_node_type` | `"attribute"` | `JavaNodeType.FIELD_ACCESS` (`"field_access"`) |
| `attr_object_field` | `"object"` | `"object"` (same) |
| `attr_attribute_field` | `"attribute"` | `"field"` |
| `comment_types` | `frozenset({"comment"})` | `frozenset({"comment", "line_comment", "block_comment"})` |
| `noise_types` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` |
| `block_node_types` | `frozenset()` | `frozenset({"block", "program"})` |
| `for_initializer_field` | `"initializer"` | `"init"` (Java tree-sitter uses `init` for for-loop initializer) |

All other constants (`none_literal`, `true_literal`, `false_literal`, `default_return_value`, `paren_expr_type`, field names for if/while/call/class/assign/subscript) retain their `GrammarConstants` defaults.

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `decimal_integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `hex_integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `octal_integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `binary_integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `decimal_floating_point_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `character_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `this` | `common_expr.lower_identifier` | `LOAD_VAR "this"` |
| `binary_expression` | `common_expr.lower_binop` | `BINOP` |
| `unary_expression` | `common_expr.lower_unop` | `UNOP` |
| `update_expression` | `common_expr.lower_update_expr` | `BINOP(+/-) + STORE_VAR/STORE_FIELD` |
| `parenthesized_expression` | `common_expr.lower_paren` | (unwraps inner expression) |
| `method_invocation` | `java_expr.lower_method_invocation` | `CALL_METHOD` or `CALL_FUNCTION` |
| `object_creation_expression` | `java_expr.lower_object_creation` | `CALL_FUNCTION(TypeName, args...)` |
| `field_access` | `java_expr.lower_field_access` | `LOAD_FIELD` |
| `array_access` | `java_expr.lower_array_access` | `LOAD_INDEX` |
| `array_creation_expression` | `java_expr.lower_array_creation` | `NEW_ARRAY` + `STORE_INDEX` per element |
| `array_initializer` | `java_expr.lower_array_creation` | `NEW_ARRAY` + `STORE_INDEX` per element |
| `assignment_expression` | `java_expr.lower_assignment_expr` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `cast_expression` | `java_expr.lower_cast_expr` | (transparent -- lowers the value child) |
| `instanceof_expression` | `java_expr.lower_instanceof` | `CALL_FUNCTION("instanceof", obj, type)` |
| `ternary_expression` | `java_expr.lower_ternary` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` |
| `type_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `method_reference` | `java_expr.lower_method_reference` | `LOAD_FIELD(obj, method_name)` |
| `lambda_expression` | `java_expr.lower_lambda` | `BRANCH`/`LABEL` func body + `CONST <function:...>` |
| `class_literal` | `java_expr.lower_class_literal` | `LOAD_FIELD(type_reg, "class")` |
| `super` | `common_expr.lower_identifier` | `LOAD_VAR "super"` |
| `scoped_identifier` | `java_expr.lower_scoped_identifier` | `LOAD_VAR "java.lang.System"` (full dotted text) |
| `switch_expression` | `java_cf.lower_java_switch_expr` | if/else chain returning last arm value |
| `expression_statement` | `java_expr.lower_expr_stmt_as_expr` | (unwraps inner expression in expr context) |
| `throw_statement` | `java_expr.lower_throw_as_expr` | `THROW` + returns val_reg |

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `common_assign.lower_expression_statement` | (unwraps inner expression) |
| `local_variable_declaration` | `java_decl.lower_local_var_decl` | `STORE_VAR` per declarator |
| `return_statement` | `common_assign.lower_return` | `RETURN` |
| `if_statement` | `java_cf.lower_if` | `BRANCH_IF` / `LABEL` / `BRANCH` |
| `while_statement` | `common_cf.lower_while` | `BRANCH_IF` loop |
| `for_statement` | `common_cf.lower_c_style_for` | init + `BRANCH_IF` loop + update; init vars block-scoped (`for_initializer_field="init"`) |
| `enhanced_for_statement` | `java_cf.lower_enhanced_for` | index-based iteration loop |
| `method_declaration` | `java_decl.lower_method_decl_stmt` | `BRANCH`/`LABEL` func + params + `RETURN` + `STORE_VAR` |
| `class_declaration` | `java_decl.lower_class_def` | `BRANCH`/`LABEL` class + deferred body + `STORE_VAR` |
| `interface_declaration` | `java_decl.lower_interface_decl` | `NEW_OBJECT("interface:Name")` + `STORE_INDEX` per member |
| `enum_declaration` | `java_decl.lower_enum_decl` | `NEW_OBJECT("enum:Name")` + `STORE_INDEX` per constant |
| `throw_statement` | `java_cf.lower_throw` | `THROW` |
| `import_declaration` | `lambda ctx, node: None` | (skipped) |
| `package_declaration` | `lambda ctx, node: None` | (skipped) |
| `break_statement` | `common_cf.lower_break` | `BRANCH` to break target |
| `continue_statement` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `switch_expression` | `java_cf.lower_java_switch` | if/else chain with `BINOP("==")` + `BRANCH_IF` |
| `try_statement` | `java_cf.lower_try` | `LABEL`/`BRANCH` try/catch/finally blocks |
| `try_with_resources_statement` | `java_cf.lower_try` | same as `try_statement` |
| `do_statement` | `java_cf.lower_do_statement` | body-first loop with `BRANCH_IF` at end |
| `assert_statement` | `java_cf.lower_assert_statement` | `CALL_FUNCTION("assert", cond, [msg])` |
| `labeled_statement` | `java_cf.lower_labeled_statement` | (unwraps, lowers inner statement) |
| `synchronized_statement` | `java_cf.lower_synchronized_statement` | lowers lock expr + body |
| `explicit_constructor_invocation` | `java_cf.lower_explicit_constructor_invocation` | `CALL_FUNCTION("super"/"this", args...)` |
| `annotation_type_declaration` | `java_decl.lower_annotation_type_decl` | `NEW_OBJECT("annotation:Name")` + `STORE_INDEX` per member |
| `record_declaration` | `java_decl.lower_record_decl` | same structure as `class_declaration` |

## Language-Specific Lowering Methods

### `java_expr.lower_method_invocation(ctx, node) -> str`
Handles Java's `method_invocation` node which uses `name`, `object`, and `arguments` fields. If `object` is present, emits `CALL_METHOD(obj_reg, method_name, args...)`; otherwise emits `CALL_FUNCTION(func_name, args...)`. Uses `common_expr.extract_call_args_unwrap` to handle `argument` wrapper nodes.

### `java_expr.lower_object_creation(ctx, node) -> str`
Lowers `new ClassName(args...)` by extracting the `type` field name and emitting `CALL_FUNCTION(TypeName, args...)`. Seeds the register type with the class name.

### `java_expr.lower_field_access(ctx, node) -> str`
Uses Java-specific field names (`object`/`field`) to emit `LOAD_FIELD(obj_reg, field_name)`.

### `java_expr.lower_method_reference(ctx, node) -> str`
Lowers `Type::method` or `obj::method` using positional children (first child is object, last is method). Emits `LOAD_FIELD(obj_reg, method_name)`.

### `java_expr.lower_scoped_identifier(ctx, node) -> str`
Handles `java.lang.System`-style dotted identifiers. Uses full node text as the variable name in `LOAD_VAR`.

### `java_expr.lower_class_literal(ctx, node) -> str`
Lowers `Type.class` as `LOAD_FIELD(type_reg, "class")` using positional children.

### `java_expr.lower_lambda(ctx, node) -> str`
Creates a function body with label `func___lambda_N`, lowers parameters via `_lower_lambda_params`, and returns a `CONST "<function:__lambda@...>"` reference. Handles both block and expression bodies.

### `java_expr._lower_lambda_params(ctx, params_node)`
Dispatches between `formal_parameters` (typed, uses `lower_java_params`) and inferred parameters (untyped, walks identifier children directly).

### `java_expr.lower_array_access(ctx, node) -> str`
Uses `array`/`index` field names to emit `LOAD_INDEX(arr_reg, idx_reg)`.

### `java_expr.lower_array_creation(ctx, node) -> str`
Three cases: (1) standalone `array_initializer` `{1, 2, 3}`, (2) `new int[]{1,2,3}` with initializer child, (3) `new int[5]` with `dimensions_expr`. All emit `NEW_ARRAY` + optional `STORE_INDEX` per element.

### `java_expr.lower_assignment_expr(ctx, node) -> str`
Expression-context assignment. Returns the value register after storing via `lower_java_store_target`.

### `java_expr.lower_java_store_target(ctx, target, val_reg, parent_node)`
Handles Java-specific target types: `identifier` -> `STORE_VAR`, `field_access` -> `STORE_FIELD`, `array_access` -> `STORE_INDEX`, else fallback `STORE_VAR`.

### `java_expr.lower_cast_expr(ctx, node) -> str`
Transparent cast: lowers the `value` field child (or last named child), discarding the type. The IR has no explicit cast opcode.

### `java_expr.lower_instanceof(ctx, node) -> str`
Lowers `expr instanceof Type` as `CALL_FUNCTION("instanceof", obj_reg, type_reg)` where `type_reg` is a `CONST` holding the type name string.

### `java_expr.lower_ternary(ctx, node) -> str`
Lowers `cond ? a : b` using `BRANCH_IF` to branch between true/false labels. Both branches write to a synthetic `__ternary_N` variable, which is loaded at the end label. Uses `condition`/`consequence`/`alternative` fields.

### `java_expr.lower_expr_stmt_as_expr(ctx, node) -> str`
Lowers `expression_statement` in expression context (e.g., inside switch expression). Unwraps to the inner named child.

### `java_expr.lower_throw_as_expr(ctx, node) -> str`
Lowers `throw_statement` in expression context (e.g., switch expression arm). Emits `THROW` and returns the value register.

### `java_expr.lower_java_params(ctx, params_node)`
Walks `formal_parameter` and `spread_parameter` children. For each, extracts the `name` field and emits `SYMBOLIC("param:name")` + `STORE_VAR`. Extracts and seeds type hints.

### `java_cf.lower_if(ctx, node)`
Java if with else-if handled as nested `if_statement`. Uses `condition`/`consequence`/`alternative` fields. Recursively calls itself for `else if` chains.

### `java_cf.lower_enhanced_for(ctx, node)`
Lowers `for (Type var : iterable) { body }` as an index-based while loop: initializes `idx=0`, computes `len=len(iterable)`, and loops while `idx < len`. Each iteration loads `iterable[idx]` into the loop variable. Continue target is the update label that increments the index.

### `java_cf.lower_java_switch(ctx, node)`
Lowers `switch(expr) { case ... }` as a linear if/else chain. Pushes the `end_label` onto `break_target_stack` so `break` branches correctly. Each `switch_block_statement_group` is compared with `BINOP("==")` + `BRANCH_IF`. Default cases branch unconditionally.

### `java_cf.lower_java_switch_expr(ctx, node) -> str`
Lowers switch expression as if/else chain, returning last arm value via a synthetic `__switch_result_N` variable. Handles both `switch_block_statement_group` and `switch_rule` entries.

### `java_cf.lower_do_statement(ctx, node)`
Lowers `do { body } while (cond)` with body-first execution: `LABEL body` -> body -> `LABEL cond` -> `BRANCH_IF(cond, body, end)` -> `LABEL end`. Pushes loop context with `continue_label=cond_label`.

### `java_cf.lower_assert_statement(ctx, node)`
Lowers `assert cond` or `assert cond : msg` as `CALL_FUNCTION("assert", cond_reg, [msg_reg])`.

### `java_cf.lower_labeled_statement(ctx, node)`
Discards the label, lowers only the inner statement (last named child).

### `java_cf.lower_synchronized_statement(ctx, node)`
Lowers the lock expression (parenthesized) and the body block sequentially.

### `java_cf.lower_throw(ctx, node)`
Delegates to `common.exceptions.lower_raise_or_throw(ctx, node, keyword="throw")`.

### `java_cf.lower_try(ctx, node)`
Extracts body, catch clauses (from `catch_clause` -> `catch_formal_parameter` -> name/type), and finally block. Delegates to `common.exceptions.lower_try_catch`.

### `java_cf.lower_explicit_constructor_invocation(ctx, node)`
Handles `super(...)` and `this(...)` calls. Determines target name from the first `super`/`this` child node, then emits `CALL_FUNCTION(target_name, args...)`.

### `java_decl.lower_local_var_decl(ctx, node)`
Walks `variable_declarator` children. With initializer: lowers value, emits `STORE_VAR`. Without initializer: emits `CONST "None"` + `STORE_VAR`. Extracts and seeds type hints.

### `java_decl.lower_method_decl(ctx, node, inject_this=False)`
Lowers method declarations with `BRANCH` around the body, `LABEL` for the function, parameters via `lower_java_params`, block body, implicit return, and `STORE_VAR` binding the function reference. Optionally injects `this` parameter for instance methods.

### `java_decl.lower_method_decl_stmt(ctx, node)`
Statement-dispatch wrapper: calls `lower_method_decl(ctx, node)`.

### `java_decl.lower_class_def(ctx, node)`
Emits class label structure, then calls `_lower_class_body` which partitions children into methods (including `constructor_declaration`) first and rest second. Returns deferred children that are lowered at top level via `_lower_deferred_class_child`. Extracts parent classes and interfaces, seeds interface implementations.

### `java_decl._lower_class_body(ctx, node) -> list`
Collects class-body children, skipping `modifiers`, `marker_annotation`, `annotation`. Partitions into `_CLASS_BODY_METHOD_TYPES = {"method_declaration", "constructor_declaration"}` and rest. Returns `methods + rest` for ordered top-level lowering.

### `java_decl._lower_deferred_class_child(ctx, child)`
Dispatches by type: `method_declaration` -> `lower_method_decl` (with `inject_this` if non-static), `constructor_declaration` -> `_lower_constructor_decl`, `field_declaration` -> `_lower_field_decl`, `static_initializer` -> `_lower_static_initializer`, else `ctx.lower_stmt`.

### `java_decl._lower_constructor_decl(ctx, node)`
Lowers constructor as a function named `__init__`. Uses `lower_java_params` for parameters.

### `java_decl._lower_field_decl(ctx, node)`
Walks `variable_declarator` children. For those with both `name` and `value`, lowers value and emits `STORE_VAR`. Seeds type hints.

### `java_decl.lower_interface_decl(ctx, node)`
Emits `NEW_OBJECT("interface:Name")`, then for each named member in the body emits `STORE_INDEX(obj, member_name, ordinal)`. Finally `STORE_VAR(iface_name, obj_reg)`.

### `java_decl.lower_enum_decl(ctx, node)`
Emits `NEW_OBJECT("enum:Name")`, then for each `enum_constant` child emits `STORE_INDEX(obj, member_name, ordinal)`. Finally `STORE_VAR(enum_name, obj_reg)`.

### `java_decl.lower_annotation_type_decl(ctx, node)`
Lowers `@interface Name { ... }` as `NEW_OBJECT("annotation:Name")` + `STORE_INDEX` per member, identical structure to interface declarations.

### `java_decl.lower_record_decl(ctx, node)`
Lowers `record Name(...)` identically to `class_declaration` using the same `_lower_class_body` + deferred child pattern.

### `java_decl._lower_static_initializer(ctx, node)`
Finds the `block` child inside `static { ... }` and lowers it.

## Canonical Literal Handling

| Java AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `null_literal` | `common_expr.lower_canonical_none` | `CONST "None"` |

Java's `true`/`false` are dispatched to individual canonical handlers (not `lower_canonical_bool`) since the tree-sitter grammar produces separate node types for each.

## Example

**Java source:**
```java
public int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
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
CONST %2, 1
BINOP %3, "<=", %1, %2
BRANCH_IF %3, if_true_2, if_end_4
LABEL if_true_2
CONST %4, 1
RETURN %4
BRANCH if_end_4
LABEL if_end_4
LOAD_VAR %5, n
LOAD_VAR %6, n
CONST %7, 1
BINOP %8, "-", %6, %7
CALL_FUNCTION %9, factorial, %8
BINOP %10, "*", %5, %9
RETURN %10
CONST %11, "None"
RETURN %11
LABEL end_factorial_1
CONST %12, "<function:factorial@func_factorial_0>"
STORE_VAR factorial, %12
```

## Design Notes

- **Constructors as `__init__`**: Java constructors are uniformly lowered with the function name `__init__`, making them recognizable across languages in the IR.
- **Cast transparency**: `cast_expression` is a no-op in the IR -- the value is passed through without any type-conversion opcode. This is intentional since the IR is untyped.
- **Switch as if-chain**: Java `switch` is lowered as a linear equality-check chain rather than a jump table. The `break_target_stack` is used so that `break` inside switch cases branches to the correct end label. Switch expressions produce a value via a synthetic `__switch_result_N` variable.
- **Class body hoisting**: Class body members are partitioned -- methods/constructors first, then fields/initializers -- to ensure function references are registered before field initializers that may call them.
- **Enhanced for as index loop**: Rather than emitting iterator protocol calls, enhanced for-each is lowered as `for (idx=0; idx<len(iterable); idx++) { var = iterable[idx]; body }`.
- **`lower_if` override**: The Java frontend overrides the base `lower_if` to handle `else` alternatives by directly iterating named children of the alternative node, and recursively calling itself for nested `if_statement` else-if chains.
- **try-with-resources**: Uses the same `lower_try` handler as regular try statements -- resource cleanup semantics are not modeled in the IR.
- **`_CLASS_BODY_SKIP_TYPES`**: `frozenset({"modifiers", "marker_annotation", "annotation"})` -- these node types are silently skipped during class body lowering.
- **`_CLASS_BODY_METHOD_TYPES`**: `frozenset({"method_declaration", "constructor_declaration"})` -- used to partition class body for ordered hoisting.
- **Pure function architecture**: All lowering logic lives in pure functions taking `(ctx: TreeSitterEmitContext, node)` instead of instance methods. The `JavaFrontend` class is a thin orchestrator that builds dispatch tables and constants.
- **Instance method `this` injection**: `lower_method_decl` accepts an `inject_this` parameter; class body methods get `this` injected unless they have a `static` modifier.
