# Java Frontend

> `interpreter/frontends/java.py` -- Extends BaseFrontend -- ~1110 lines

## Overview

The Java frontend lowers tree-sitter Java ASTs into flattened three-address-code (TAC) IR. It handles the full breadth of Java's statement and expression grammar including classes, interfaces, enums, annotations, records, try/catch/finally, switch statements, enhanced for-loops, lambda expressions, method references, and ternary expressions. Java constructors are lowered with the canonical name `__init__`.

## Class Hierarchy

```
Frontend (abstract)
  -> BaseFrontend (_base.py)
       -> JavaFrontend (java.py)
```

Nothing extends `JavaFrontend`. It inherits all common lowering infrastructure from `BaseFrontend` (register/label allocation, `_emit`, `_lower_block`, `_lower_stmt`, `_lower_expr`, `_lower_while`, `_lower_c_style_for`, `_lower_try_catch`, `_lower_raise_or_throw`, `_lower_update_expr`, `_lower_break`, `_lower_continue`, etc.).

## Overridden Constants

| Constant | BaseFrontend Default | JavaFrontend Value |
|---|---|---|
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"field_access"` |
| `ATTR_OBJECT_FIELD` | `"object"` | `"object"` (same) |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"field"` |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment", "line_comment", "block_comment"})` |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` |

All other constants (`NONE_LITERAL`, `TRUE_LITERAL`, `FALSE_LITERAL`, `DEFAULT_RETURN_VALUE`, `PAREN_EXPR_TYPE`, field names for if/while/call/class/assign/subscript) retain their `BaseFrontend` defaults.

## Expression Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` | `LOAD_VAR` |
| `decimal_integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `hex_integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `octal_integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `binary_integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `decimal_floating_point_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `character_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |
| `this` | `_lower_identifier` | `LOAD_VAR "this"` |
| `binary_expression` | `_lower_binop` | `BINOP` |
| `unary_expression` | `_lower_unop` | `UNOP` |
| `update_expression` | `_lower_update_expr` | `BINOP(+/-) + STORE_VAR/STORE_FIELD` |
| `parenthesized_expression` | `_lower_paren` | (unwraps inner expression) |
| `method_invocation` | `_lower_method_invocation` | `CALL_METHOD` or `CALL_FUNCTION` |
| `object_creation_expression` | `_lower_object_creation` | `CALL_FUNCTION(TypeName, args...)` |
| `field_access` | `_lower_field_access` | `LOAD_FIELD` |
| `array_access` | `_lower_array_access` | `LOAD_INDEX` |
| `array_creation_expression` | `_lower_array_creation` | `NEW_ARRAY` + `STORE_INDEX` per element |
| `array_initializer` | `_lower_array_creation` | `NEW_ARRAY` + `STORE_INDEX` per element |
| `assignment_expression` | `_lower_assignment_expr` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `cast_expression` | `_lower_cast_expr` | (transparent -- lowers the value child) |
| `instanceof_expression` | `_lower_instanceof` | `CALL_FUNCTION("instanceof", obj, type)` |
| `ternary_expression` | `_lower_ternary` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` |
| `type_identifier` | `_lower_identifier` | `LOAD_VAR` |
| `method_reference` | `_lower_method_reference` | `LOAD_FIELD(obj, method_name)` |
| `lambda_expression` | `_lower_lambda` | `BRANCH`/`LABEL` func body + `CONST <function:...>` |
| `class_literal` | `_lower_class_literal` | `LOAD_FIELD(type_reg, "class")` |
| `super` | `_lower_identifier` | `LOAD_VAR "super"` |
| `scoped_identifier` | `_lower_scoped_identifier` | `LOAD_VAR "java.lang.System"` (full dotted text) |

## Statement Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `_lower_expression_statement` | (unwraps inner expression) |
| `local_variable_declaration` | `_lower_local_var_decl` | `STORE_VAR` per declarator |
| `return_statement` | `_lower_return` | `RETURN` |
| `if_statement` | `_lower_if` | `BRANCH_IF` / `LABEL` / `BRANCH` |
| `while_statement` | `_lower_while` | `BRANCH_IF` loop |
| `for_statement` | `_lower_c_style_for` | init + `BRANCH_IF` loop + update |
| `enhanced_for_statement` | `_lower_enhanced_for` | index-based iteration loop |
| `method_declaration` | `_lower_method_decl` | `BRANCH`/`LABEL` func + params + `RETURN` + `STORE_VAR` |
| `class_declaration` | `_lower_class_def` | `BRANCH`/`LABEL` class + deferred body + `STORE_VAR` |
| `interface_declaration` | `_lower_interface_decl` | `NEW_OBJECT("interface:Name")` + `STORE_INDEX` per member |
| `enum_declaration` | `_lower_enum_decl` | `NEW_OBJECT("enum:Name")` + `STORE_INDEX` per constant |
| `throw_statement` | `_lower_throw` | `THROW` |
| `block` | `_lower_block` | (iterates children) |
| `import_declaration` | `lambda _: None` | (skipped) |
| `package_declaration` | `lambda _: None` | (skipped) |
| `program` | `_lower_block` | (iterates children) |
| `break_statement` | `_lower_break` | `BRANCH` to break target |
| `continue_statement` | `_lower_continue` | `BRANCH` to continue label |
| `switch_expression` | `_lower_java_switch` | if/else chain with `BINOP("==")` + `BRANCH_IF` |
| `try_statement` | `_lower_try` | `LABEL`/`BRANCH` try/catch/finally blocks |
| `try_with_resources_statement` | `_lower_try` | same as `try_statement` |
| `do_statement` | `_lower_do_statement` | body-first loop with `BRANCH_IF` at end |
| `assert_statement` | `_lower_assert_statement` | `CALL_FUNCTION("assert", cond, [msg])` |
| `labeled_statement` | `_lower_labeled_statement` | (unwraps, lowers inner statement) |
| `synchronized_statement` | `_lower_synchronized_statement` | lowers lock expr + body |
| `explicit_constructor_invocation` | `_lower_explicit_constructor_invocation` | `CALL_FUNCTION("super"/"this", args...)` |
| `annotation_type_declaration` | `_lower_annotation_type_decl` | `NEW_OBJECT("annotation:Name")` + `STORE_INDEX` per member |
| `record_declaration` | `_lower_record_decl` | same structure as `class_declaration` |

## Language-Specific Lowering Methods

### `_lower_method_invocation(node) -> str`
Handles Java's `method_invocation` node which uses `name`, `object`, and `arguments` fields. If `object` is present, emits `CALL_METHOD(obj_reg, method_name, args...)`; otherwise emits `CALL_FUNCTION(func_name, args...)`. Uses `_extract_call_args_unwrap` to handle `argument` wrapper nodes.

### `_lower_object_creation(node) -> str`
Lowers `new ClassName(args...)` by extracting the `type` field name and emitting `CALL_FUNCTION(TypeName, args...)`.

### `_lower_field_access(node) -> str`
Uses Java-specific field names (`object`/`field`) to emit `LOAD_FIELD(obj_reg, field_name)`.

### `_lower_method_reference(node) -> str`
Lowers `Type::method` or `obj::method` using positional children (first child is object, last is method). Emits `LOAD_FIELD(obj_reg, method_name)`.

### `_lower_scoped_identifier(node) -> str`
Handles `java.lang.System`-style dotted identifiers. Uses full node text as the variable name in `LOAD_VAR`.

### `_lower_class_literal(node) -> str`
Lowers `Type.class` as `LOAD_FIELD(type_reg, "class")` using positional children.

### `_lower_lambda(node) -> str`
Creates a function body with label `func___lambda_N`, lowers parameters via `_lower_lambda_params`, and returns a `CONST "<function:__lambda@...>"` reference. Handles both block and expression bodies.

### `_lower_lambda_params(params_node)`
Dispatches between `formal_parameters` (typed, uses `_lower_java_params`) and inferred parameters (untyped, walks identifier children directly).

### `_lower_array_access(node) -> str`
Uses `array`/`index` field names to emit `LOAD_INDEX(arr_reg, idx_reg)`.

### `_lower_array_creation(node) -> str`
Three cases: (1) standalone `array_initializer` `{1, 2, 3}`, (2) `new int[]{1,2,3}` with initializer child, (3) `new int[5]` with `dimensions_expr`. All emit `NEW_ARRAY` + optional `STORE_INDEX` per element.

### `_lower_assignment_expr(node) -> str`
Expression-context assignment. Returns the value register after storing.

### `_lower_store_target(target, val_reg, parent_node)`
Overrides base to handle Java-specific target types: `identifier` -> `STORE_VAR`, `field_access` -> `STORE_FIELD`, `array_access` -> `STORE_INDEX`, else fallback `STORE_VAR`.

### `_lower_cast_expr(node) -> str`
Transparent cast: lowers the `value` field child (or last named child), discarding the type. The IR has no explicit cast opcode.

### `_lower_instanceof(node) -> str`
Lowers `expr instanceof Type` as `CALL_FUNCTION("instanceof", obj_reg, type_reg)` where `type_reg` is a `CONST` holding the type name string.

### `_lower_ternary(node) -> str`
Lowers `cond ? a : b` using `BRANCH_IF` to branch between true/false labels. Both branches write to a synthetic `__ternary_N` variable, which is loaded at the end label. Uses `condition`/`consequence`/`alternative` fields.

### `_lower_enhanced_for(node)`
Lowers `for (Type var : iterable) { body }` as an index-based while loop: initializes `idx=0`, computes `len=len(iterable)`, and loops while `idx < len`. Each iteration loads `iterable[idx]` into the loop variable. Continue target is the update label that increments the index.

### `_lower_java_switch(node)`
Lowers `switch(expr) { case ... }` as a linear if/else chain. Pushes the `end_label` onto `_break_target_stack` so `break` branches correctly. Each `switch_block_statement_group` is compared with `BINOP("==")` + `BRANCH_IF`. Default cases branch unconditionally.

### `_lower_method_decl(node)`
Lowers method declarations with `BRANCH` around the body, `LABEL` for the function, parameters via `_lower_java_params`, block body, implicit return, and `STORE_VAR` binding the function reference.

### `_lower_java_params(params_node)`
Walks `formal_parameter` and `spread_parameter` children. For each, extracts the `name` field and emits `SYMBOLIC("param:name")` + `STORE_VAR`.

### `_lower_class_def(node)`
Emits class label structure, then calls `_lower_class_body` which partitions children into methods (including `constructor_declaration`) first and rest second. Returns deferred children that are lowered at top level via `_lower_deferred_class_child`.

### `_lower_class_body(node) -> list`
Collects class body children, skipping `modifiers`, `marker_annotation`, `annotation`. Partitions into `_CLASS_BODY_METHOD_TYPES = {"method_declaration", "constructor_declaration"}` and rest. Returns `methods + rest` for ordered top-level lowering.

### `_lower_deferred_class_child(child)`
Dispatches by type: `method_declaration` -> `_lower_method_decl`, `constructor_declaration` -> `_lower_constructor_decl`, `field_declaration` -> `_lower_field_decl`, `static_initializer` -> `_lower_static_initializer`, else `_lower_stmt`.

### `_lower_constructor_decl(node)`
Lowers constructor as a function named `__init__`. Uses `_lower_java_params` for parameters.

### `_lower_field_decl(node)`
Walks `variable_declarator` children. For those with both `name` and `value`, lowers value and emits `STORE_VAR`.

### `_lower_interface_decl(node)`
Emits `NEW_OBJECT("interface:Name")`, then for each named member in the body emits `STORE_INDEX(obj, member_name, ordinal)`. Finally `STORE_VAR(iface_name, obj_reg)`.

### `_lower_enum_decl(node)`
Emits `NEW_OBJECT("enum:Name")`, then for each `enum_constant` child emits `STORE_INDEX(obj, member_name, ordinal)`. Finally `STORE_VAR(enum_name, obj_reg)`.

### `_lower_try(node)`
Extracts body, catch clauses (from `catch_clause` -> `catch_formal_parameter` -> name/type), and finally block. Delegates to `BaseFrontend._lower_try_catch`. Handles both `try_statement` and `try_with_resources_statement`.

### `_lower_throw(node)`
Delegates to `_lower_raise_or_throw(node, keyword="throw")`.

### `_lower_do_statement(node)`
Lowers `do { body } while (cond)` with body-first execution: `LABEL body` -> body -> `LABEL cond` -> `BRANCH_IF(cond, body, end)` -> `LABEL end`. Pushes loop context with `continue_label=cond_label`.

### `_lower_assert_statement(node)`
Lowers `assert cond` or `assert cond : msg` as `CALL_FUNCTION("assert", cond_reg, [msg_reg])`.

### `_lower_labeled_statement(node)`
Discards the label, lowers only the inner statement (last named child).

### `_lower_synchronized_statement(node)`
Lowers the lock expression (parenthesized) and the body block sequentially.

### `_lower_static_initializer(node)`
Finds the `block` child inside `static { ... }` and lowers it.

### `_lower_explicit_constructor_invocation(node)`
Handles `super(...)` and `this(...)` calls. Determines target name from the first `super`/`this` child node, then emits `CALL_FUNCTION(target_name, args...)`.

### `_lower_annotation_type_decl(node)`
Lowers `@interface Name { ... }` as `NEW_OBJECT("annotation:Name")` + `STORE_INDEX` per member, identical structure to interface declarations.

### `_lower_record_decl(node)`
Lowers `record Name(...)` identically to `class_declaration` using the same `_lower_class_body` + deferred child pattern.

### `_lower_if(node)`
Overrides `BaseFrontend._lower_if` to handle Java's `else` alternative by iterating the alternative node's named children (skipping `"else"` type nodes), rather than using the base class `_lower_alternative` dispatch.

### `_lower_local_var_decl(node)`
Walks `variable_declarator` children. With initializer: lowers value, emits `STORE_VAR`. Without initializer: emits `CONST "None"` + `STORE_VAR`.

## Canonical Literal Handling

| Java AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |
| `null_literal` | `_lower_canonical_none` | `CONST "None"` |

Java's `true`/`false` are dispatched to individual canonical handlers (not `_lower_canonical_bool`) since the tree-sitter grammar produces separate node types for each.

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
- **Switch as if-chain**: Java `switch` is lowered as a linear equality-check chain rather than a jump table. The `break_target_stack` is used so that `break` inside switch cases branches to the correct end label.
- **Class body hoisting**: Class body members are partitioned -- methods/constructors first, then fields/initializers -- to ensure function references are registered before field initializers that may call them.
- **Enhanced for as index loop**: Rather than emitting iterator protocol calls, enhanced for-each is lowered as `for (idx=0; idx<len(iterable); idx++) { var = iterable[idx]; body }`.
- **`_lower_if` override**: The Java frontend overrides the base `_lower_if` to handle `else` alternatives by directly iterating named children of the alternative node, bypassing the base class `_lower_alternative` dispatch which expects `elif_clause`/`else_clause` node types that Java does not have.
- **try-with-resources**: Uses the same `_lower_try` handler as regular try statements -- resource cleanup semantics are not modeled in the IR.
- **`_CLASS_BODY_SKIP_TYPES`**: `frozenset({"modifiers", "marker_annotation", "annotation"})` -- these node types are silently skipped during class body lowering.
- **`_CLASS_BODY_METHOD_TYPES`**: `frozenset({"method_declaration", "constructor_declaration"})` -- used to partition class body for ordered hoisting.
