# JavaScript Frontend

> `interpreter/frontends/javascript/` · Extends `BaseFrontend` · Per-language directory architecture

## Overview

The JavaScript frontend lowers tree-sitter JavaScript ASTs into the RedDragon flattened TAC IR. It handles JavaScript-specific constructs including destructuring assignments (object and array), arrow functions, template strings with substitutions, `new` expressions, `await`/`yield`, spread elements, ternary operator, `for...in`/`for...of` loops, `switch` statements, `do...while` loops, labeled statements, export statements, and class method definitions.

## Directory Structure

```
interpreter/frontends/javascript/
├── frontend.py        # JavaScriptFrontend class (thin orchestrator)
├── node_types.py      # JavaScriptNodeType constants class
├── expressions.py     # Expression lowerers (pure functions)
├── control_flow.py    # Control flow lowerers (pure functions)
└── declarations.py    # Declaration lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── JavaScriptFrontend (javascript/frontend.py)   ← this frontend
              └── TypeScriptFrontend (typescript.py)
```

`TypeScriptFrontend` extends this class, inheriting all dispatch tables and methods, then adding TypeScript-specific entries.

## GrammarConstants (from `_build_constants()`)

| Field | Value | Notes |
|---|---|---|
| `attr_object_field` | `"object"` | Same as base |
| `attr_attribute_field` | `"property"` | JS tree-sitter uses `property` not `attribute` |
| `attribute_node_type` | `"member_expression"` | JS uses `member_expression` for property access |
| `subscript_value_field` | `"object"` | JS subscript uses `object` field |
| `subscript_index_field` | `"index"` | JS subscript uses `index` field |
| `comment_types` | `frozenset({"comment"})` | Via `JSN.COMMENT` |
| `noise_types` | `frozenset({"\n"})` | Via `JSN.NEWLINE` (only newline char) |
| `block_node_types` | `frozenset({"statement_block", "program", "module"})` | Via `JSN.STATEMENT_BLOCK`, `.PROGRAM`, `.MODULE` |

The JavaScript frontend inherits base defaults for `none_literal` (`"None"`), `true_literal` (`"True"`), `false_literal` (`"False"`), and `default_return_value` (`"None"`). Note these are Python-canonical forms, not JavaScript-native. The dispatch table maps JS-native node types (`null`, `undefined`, `true`, `false`) to canonical lowering methods.

## Expression Dispatch Table (from `_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `number` | `common_expr.lower_const_literal` | `CONST` |
| `string` | `common_expr.lower_const_literal` | `CONST` |
| `template_string` | `js_expr.lower_template_string` | `CONST` (no subs) or `CONST` + `BINOP("+")` chain |
| `template_substitution` | `js_expr.lower_template_substitution` | Delegates to inner expression |
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `null` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `undefined` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `binary_expression` | `common_expr.lower_binop` | `BINOP` |
| `augmented_assignment_expression` | `common_expr.lower_binop` | `BINOP` |
| `unary_expression` | `common_expr.lower_unop` | `UNOP` |
| `update_expression` | `common_expr.lower_update_expr` | `BINOP("+"/"-", operand, 1)` + store |
| `call_expression` | `js_expr.lower_js_call` | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `new_expression` | `js_expr.lower_new_expression` | `NEW_OBJECT` + `CALL_METHOD("constructor")` |
| `member_expression` | `js_expr.lower_js_attribute` | `LOAD_FIELD` |
| `subscript_expression` | `js_expr.lower_js_subscript` | `LOAD_INDEX` |
| `parenthesized_expression` | `common_expr.lower_paren` | Delegates to inner expression |
| `array` | `common_expr.lower_list_literal` | `NEW_ARRAY("list")` + `STORE_INDEX` per element |
| `object` | `js_expr.lower_js_object_literal` | `NEW_OBJECT("object")` + `STORE_INDEX` per pair |
| `assignment_expression` | `js_expr.lower_assignment_expr` | Lower RHS + store to target |
| `arrow_function` | `js_expr.lower_arrow_function` | `BRANCH` past body, `LABEL`, params, body/implicit return, `CONST` func ref |
| `ternary_expression` | `js_expr.lower_ternary` | `BRANCH_IF` + `STORE_VAR`/`LOAD_VAR` phi |
| `this` | `common_expr.lower_identifier` | `LOAD_VAR "this"` |
| `super` | `common_expr.lower_identifier` | `LOAD_VAR "super"` |
| `property_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `shorthand_property_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `await_expression` | `js_expr.lower_await_expression` | `CALL_FUNCTION("await", expr)` |
| `yield_expression` | `js_expr.lower_yield_expression` | `CALL_FUNCTION("yield", expr)` |
| `regex` | `common_expr.lower_const_literal` | `CONST` |
| `sequence_expression` | `js_expr.lower_sequence_expression` | Evaluates all, returns last register |
| `spread_element` | `js_expr.lower_spread_element` | `CALL_FUNCTION("spread", expr)` |
| `function` | `js_expr.lower_function_expression` | Anonymous function definition |
| `function_expression` | `js_expr.lower_function_expression` | Anonymous function definition |
| `generator_function` | `js_expr.lower_function_expression` | Anonymous function definition |
| `generator_function_declaration` | `js_decl.lower_js_function_def` | Named function definition |
| `string_fragment` | `common_expr.lower_const_literal` | `CONST` |
| `field_definition` | `js_expr.lower_js_field_definition` | `STORE_VAR(field_name, val)` |
| `export_clause` | `js_expr.lower_export_clause` | Lower inner export_specifiers |
| `export_specifier` | `common_expr.lower_paren` | Delegates to inner |

## Statement Dispatch Table (from `_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `common_assign.lower_expression_statement` | Unwraps inner expression |
| `lexical_declaration` | `js_decl.lower_js_var_declaration` | `STORE_VAR` per declarator (with destructuring support) |
| `variable_declaration` | `js_decl.lower_js_var_declaration` | `STORE_VAR` per declarator (with destructuring support) |
| `return_statement` | `common_assign.lower_return` | `RETURN` |
| `if_statement` | `js_cf.lower_js_if` | `BRANCH_IF` + labels |
| `while_statement` | `common_cf.lower_while` | `LABEL` + `BRANCH_IF` loop |
| `for_statement` | `common_cf.lower_c_style_for` | C-style for(init; cond; update) loop |
| `for_in_statement` | `js_cf.lower_for_in` | for...in / for...of dispatch |
| `function_declaration` | `js_decl.lower_js_function_def` | Named function definition |
| `class_declaration` | `js_decl.lower_js_class_def` | Class with `method_definition` and `class_static_block` handling |
| `throw_statement` | `js_cf.lower_js_throw` | `THROW` |
| `statement_block` | `lambda ctx, node: ctx.lower_block(node)` | Iterate children as statements |
| `empty_statement` | `lambda ctx, node: None` | No-op |
| `break_statement` | `common_cf.lower_break` | `BRANCH` to break target |
| `continue_statement` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `try_statement` | `js_cf.lower_js_try` | Labeled try/catch/finally blocks |
| `switch_statement` | `js_cf.lower_switch_statement` | `BINOP("===")` + `BRANCH_IF` chain |
| `do_statement` | `js_cf.lower_do_statement` | `do...while` loop structure |
| `labeled_statement` | `js_cf.lower_labeled_statement` | `LABEL` + inner statement |
| `import_statement` | `lambda ctx, node: None` | No-op (imports ignored) |
| `export_statement` | `js_decl.lower_export_statement` | Unwraps and lowers inner declaration |
| `with_statement` | `js_cf.lower_with_statement` | Lower object then body |

## Language-Specific Lowering Methods

### `js_decl.lower_js_var_declaration(ctx, node)`

Handles JavaScript destructuring patterns in variable declarations:
- `object_pattern` (`const { a, b } = obj`): calls `_lower_object_destructure`
- `array_pattern` (`const [a, b] = arr`): calls `_lower_array_destructure`
- Plain name with value: `STORE_VAR(name, val_reg)`
- Plain name without value: `CONST("None")` + `STORE_VAR`

### `js_decl._lower_object_destructure(ctx, pattern_node, val_reg, parent_node)`

Handles `{ a, b } = obj` and `{ x: localX } = obj`:
- `shorthand_property_identifier_pattern`: `LOAD_FIELD(val_reg, prop_name)` + `STORE_VAR(prop_name, field_reg)`
- `pair_pattern`: `LOAD_FIELD(val_reg, key_name)` + `STORE_VAR(local_name, field_reg)`

### `js_decl._lower_array_destructure(ctx, pattern_node, val_reg, parent_node)`

Handles `[a, b] = arr`: for each named child at index `i`, emits `CONST(i)` + `LOAD_INDEX(val_reg, idx_reg)` + `STORE_VAR(name, elem_reg)`.

### `js_expr.lower_js_attribute(ctx, node) -> str`

Handles JS member expressions: reads `object` and `property` fields from `member_expression` nodes. Emits `LOAD_FIELD(obj_reg, field_name)`.

### `js_expr.lower_js_subscript(ctx, node) -> str`

Handles `subscript_expression` (e.g., `arr[i]`): reads `object` and `index` fields, emits `LOAD_INDEX(obj_reg, idx_reg)`.

### `js_expr.lower_js_call(ctx, node) -> str`

Handles JS call expressions:
1. If `func_node.type == "member_expression"`: reads `object`/`property` fields, emits `CALL_METHOD`
2. If `func_node.type == "identifier"`: emits `CALL_FUNCTION`
3. Otherwise: lowers func expression, emits `CALL_UNKNOWN`

### `js_expr.lower_js_store_target(ctx, target, val_reg, parent_node)`

Handles JS node types for store targets:
- `identifier`: `STORE_VAR`
- `member_expression`: `STORE_FIELD` (reads `object`/`property` fields)
- `subscript_expression`: `STORE_INDEX` (reads `object`/`index` fields)
- Fallback: `STORE_VAR` with node text

### `js_expr.lower_assignment_expr(ctx, node) -> str`

Handles JS assignment expressions (which are expressions, not statements): lowers RHS, stores to target via `lower_js_store_target`, returns `val_reg`.

### `js_expr.lower_js_object_literal(ctx, node) -> str`

Lowers JS object literals `{ key: val, shorthand }`:
- `pair` children: `CONST(key)` + lower value + `STORE_INDEX`
- `shorthand_property_identifier`: `CONST(name)` + `LOAD_VAR(name)` + `STORE_INDEX`

Uses `NEW_OBJECT("object")` (compared to Python's `NEW_OBJECT("dict")`).

### `js_expr.lower_arrow_function(ctx, node) -> str`

Lowers `(x) => expr` or `(x) => { ... }`:
1. Generates synthetic name `__arrow_<n>`
2. `BRANCH` past body, `LABEL(func_<name>_<n>)`
3. If params is a single `identifier`, calls `lower_js_param` directly; otherwise `lower_js_params`
4. If body is `statement_block`: lowers as block. Otherwise: expression body with implicit `RETURN`
5. Implicit `RETURN "None"` at end
6. Returns `CONST("<function:__arrow_<n>@func_..._<n>>")` as function reference

### `js_expr.lower_ternary(ctx, node) -> str`

Lowers `cond ? trueExpr : falseExpr`:
1. Evaluates condition
2. `BRANCH_IF(cond, ternary_true, ternary_false)`
3. Each branch evaluates its expression and stores to `__ternary_<n>` via `STORE_VAR`
4. After `BRANCH` to end, `LOAD_VAR` the result from the phi variable

### `js_cf.lower_for_in(ctx, node)`

Dispatch between `for...in` and `for...of`:
- Checks `operator` field: if text is `"of"`, delegates to `js_cf.lower_for_of`
- For `for...in`: calls `keys(obj)` via `CALL_FUNCTION`, then iterates over keys array with index-based loop

### `js_cf.lower_for_of(ctx, node)`

Lowers `for (const x of iterable)` as index-based iteration:
1. Evaluates iterable, calls `len(iterable)`
2. Index-based loop: `BINOP("<")` + `BRANCH_IF` + `LOAD_INDEX`
3. Update: increment index, `STORE_VAR("__for_idx", new_idx)`

### `js_expr.lower_js_param(ctx, child)`

Handles JS parameter types:
- `identifier`: bare parameter
- `assignment_pattern`, `object_pattern`, `array_pattern`: uses full node text as parameter name
- Other types: falls back to `extract_param_name`

### `js_expr.lower_js_params(ctx, params_node)`

Iterates children of a params node and calls `lower_js_param` for each.

### `js_cf.lower_js_try(ctx, node)`

Parses JS `try { ... } catch (e) { ... } finally { ... }`:
- `handler` field: extracts `parameter` (catch variable) and `body`
- `finalizer` field: extracts inner `body`
- Delegates to `lower_try_catch`

### `js_cf.lower_js_throw(ctx, node)`

Delegates to `lower_raise_or_throw(ctx, node, keyword="throw")`, which emits `THROW`.

### `js_cf.lower_js_alternative(ctx, alt_node, end_label)`

Handles JS `else if` chains:
- `else_clause`: lowers children excluding `else` keyword
- `if_statement`: recurses into `lower_js_if` (JS chains `else if` as nested `if_statement`)
- Other: delegates to `lower_block`

### `js_cf.lower_js_if(ctx, node)`

Lowers JS if/else statements with support for chained else-if via `lower_js_alternative`.

### `js_decl.lower_js_class_def(ctx, node)`

Handles JS class body members:
- `method_definition` children: delegates to `_lower_method_def`
- `class_static_block` children: delegates to `lower_class_static_block`
- `field_definition` children: delegates to `js_expr.lower_js_field_definition`
- Other named children: lowered as statements
- Extracts parent class from `class_heritage` for inheritance

### `js_decl._lower_method_def(ctx, node)`

Lowers a method within a class body:
1. Extracts `name`, `parameters`, `body` fields
2. `BRANCH` past body, `LABEL(func_<name>_<n>)`
3. Emits `this` param for instance methods (skipped for static)
4. Lower params and body
5. Implicit `RETURN "None"`
6. `CONST` function reference + `STORE_VAR`

### `js_expr.lower_new_expression(ctx, node) -> str`

Lowers `new Foo(args)`:
1. `NEW_OBJECT(class_name)` -- creates the object
2. `CALL_METHOD(obj_reg, "constructor", ...arg_regs)` -- calls constructor

### `js_expr.lower_await_expression(ctx, node) -> str`

Lowers `await expr` as `CALL_FUNCTION("await", expr_reg)`.

### `js_expr.lower_yield_expression(ctx, node) -> str`

Lowers `yield expr` as `CALL_FUNCTION("yield", expr_reg)`. Bare `yield` (no argument) emits `CONST("None")` then `CALL_FUNCTION("yield", none_reg)`.

### `js_expr.lower_sequence_expression(ctx, node) -> str`

Lowers `(a, b, c)` (JS comma operator): evaluates all expressions left to right, returns the register of the last one.

### `js_expr.lower_spread_element(ctx, node) -> str`

Lowers `...expr` as `CALL_FUNCTION("spread", expr_reg)`.

### `js_expr.lower_function_expression(ctx, node) -> str`

Lowers anonymous function expressions (`function() { ... }`, `function* () { ... }`):
- If `name` field exists, uses it; otherwise generates `__anon_<n>`
- Same structure as `lower_js_function_def` but returns the function reference register instead of storing to a variable

### `js_expr.lower_template_string(ctx, node) -> str`

Lowers template strings (`` `Hello ${name}!` ``):
- If no `template_substitution` children: falls back to `lower_const_literal`
- Otherwise: concatenates fragments and substitution results using `BINOP("+")`
- Skips backtick (`` ` ``) tokens, emits `CONST` for string fragments

### `js_expr.lower_template_substitution(ctx, node) -> str`

Lowers `${expr}` inside template strings: extracts the first named child and lowers it as an expression.

### `js_expr.lower_js_field_definition(ctx, node) -> str`

Lowers class field definitions (`#privateField = 0` or `name = expr`): extracts property name and value, emits `STORE_VAR(field_name, val_reg)`.

### `js_expr.lower_export_clause(ctx, node) -> str`

Lowers `{ a, b }` export clause by lowering inner `export_specifier` children.

### `js_cf.lower_switch_statement(ctx, node)`

Lowers `switch(x) { case a: ... default: ... }` as an if/else chain:
1. Evaluates discriminant (`value` field)
2. Pushes `end_label` onto `break_target_stack`
3. For each `switch_case`: `BINOP("===")` comparison + `BRANCH_IF`
4. For `switch_default`: unconditionally lower body
5. Pops break target stack

### `js_cf.lower_do_statement(ctx, node)`

Lowers `do { body } while (cond)`:
1. `LABEL(do_body)` -- body executes first
2. Push loop context (continue targets `cond_label`, break targets `end_label`)
3. Lower body, pop loop context
4. `LABEL(do_cond)`, evaluate condition
5. `BRANCH_IF(cond, do_body, do_end)`

### `js_cf.lower_labeled_statement(ctx, node)`

Lowers `label: stmt`: emits `LABEL(<fresh_label>)` then lowers the body statement.

### `js_decl.lower_export_statement(ctx, node)`

Lowers `export ...` by unwrapping: iterates named children (excluding `export` and `default` keyword nodes) and lowers each as a statement.

### `js_decl.lower_class_static_block(ctx, node)`

Lowers `static { ... }` inside class body: if a `body` field exists, lowers it as a block. Otherwise falls back to lowering all named non-`static` children as statements.

### `js_decl.lower_js_function_def(ctx, node)`

Lowers function declarations using JS-specific param handling via `lower_js_params`. Extracts return type annotations if present.

### `js_cf.lower_with_statement(ctx, node)`

Lowers `with (obj) { body }` by lowering the object expression then the body block.

### `js_cf._extract_var_name(ctx, node) -> str | None`

Helper to extract variable name from:
- `identifier` node: returns text directly
- `lexical_declaration` / `variable_declaration`: finds `variable_declarator` child, extracts `name` field

## Canonical Literal Handling

| JS AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `null` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `undefined` | `common_expr.lower_canonical_none` | `CONST "None"` |

Both `null` and `undefined` are canonicalized to `"None"`. JavaScript's `true`/`false` (lowercase) are canonicalized to Python-form `"True"`/`"False"`.

## Example

**Source (JavaScript):**
```javascript
function greet(name) {
    if (name) {
        return `Hello, ${name}!`;
    }
    return "Hello, World!";
}
```

**IR Output (representative):**
```
LABEL entry
BRANCH end_greet_1
LABEL func_greet_0
  SYMBOLIC %0 "param:name"
  STORE_VAR name %0
  LOAD_VAR %1 name
  BRANCH_IF %1 if_true_2,if_end_4
  LABEL if_true_2
    CONST %2 "Hello, "
    LOAD_VAR %3 name
    BINOP %4 "+" %2 %3
    CONST %5 "!"
    BINOP %6 "+" %4 %5
    RETURN %6
  BRANCH if_end_4
  LABEL if_end_4
  CONST %7 "Hello, World!"
  RETURN %7
  CONST %8 "None"
  RETURN %8
LABEL end_greet_1
CONST %9 "<function:greet@func_greet_0>"
STORE_VAR greet %9
```

## Design Notes

1. **Destructuring**: Object and array destructuring in variable declarations is fully supported. Object destructuring handles both shorthand (`{ a, b }`) and renamed (`{ x: localX }`) patterns. Destructuring in other positions (e.g., function parameters, assignment targets) uses the full node text as parameter name rather than decomposing.

2. **For...in vs For...of**: Both are dispatched from `js_cf.lower_for_in` by checking the `operator` field text. `for...in` calls `keys(obj)` to get an array of keys then iterates. `for...of` iterates directly by index. Both use `STORE_VAR("__for_idx", ...)` for index tracking.

3. **Switch-to-if lowering**: Switch statements are lowered as strict equality (`===`) comparison chains, not as jump tables. The break target stack is used to handle `break` within switch cases.

4. **Arrow functions**: Arrow functions with expression bodies get an implicit `RETURN` for the expression value. Block-body arrows are lowered like regular function bodies. All arrow functions get synthetic names `__arrow_<n>`.

5. **Template string concatenation**: Template strings with substitutions are lowered as `CONST` fragment + `BINOP("+")` chains. Plain template strings (no substitutions) are treated as `CONST` literals.

6. **New expression model**: `new Foo(args)` is modeled as `NEW_OBJECT` + `CALL_METHOD("constructor", ...)`, separating object creation from initialization.

7. **Import/export handling**: Import statements are no-ops. Export statements are unwrapped to lower their inner declarations, discarding the export modifier.

8. **Else-if chaining**: JS `else if` is handled as a nested `if_statement` inside an `else_clause`, which differs from Python's `elif_clause`. The `js_cf.lower_js_alternative` function handles this by recursing into `lower_js_if`.

9. **Augmented assignment as expression**: `augmented_assignment_expression` is in the expression dispatch table (mapped to `common_expr.lower_binop`), reflecting that `+=` is an expression in JS, not a statement.

10. **Class static blocks**: `static { ... }` blocks inside classes are supported via `js_decl.lower_class_static_block`.

11. **Pure function architecture**: All lowering methods are pure functions taking `(ctx: TreeSitterEmitContext, node)` as arguments. The `JavaScriptFrontend` class in `frontend.py` is a thin orchestrator that builds dispatch tables from these functions via `_build_expr_dispatch()` and `_build_stmt_dispatch()`.
