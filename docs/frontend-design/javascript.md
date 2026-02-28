# JavaScript Frontend

> `interpreter/frontends/javascript.py` · Extends `BaseFrontend` · ~1007 lines

## Overview

The JavaScript frontend lowers tree-sitter JavaScript ASTs into the RedDragon flattened TAC IR. It handles JavaScript-specific constructs including destructuring assignments (object and array), arrow functions, template strings with substitutions, `new` expressions, `await`/`yield`, spread elements, ternary operator, `for...in`/`for...of` loops, `switch` statements, `do...while` loops, labeled statements, export statements, and class method definitions.

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── JavaScriptFrontend (javascript.py)   ← this file
              └── TypeScriptFrontend (typescript.py)
```

`TypeScriptFrontend` extends this class, inheriting all dispatch tables and methods, then adding TypeScript-specific entries.

## Overridden Constants

| Constant | BaseFrontend Default | JavaScriptFrontend Value | Notes |
|---|---|---|---|
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"member_expression"` | JS uses `member_expression` for property access |
| `ATTR_OBJECT_FIELD` | `"object"` | `"object"` | Same as base |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"property"` | JS tree-sitter uses `property` not `attribute` |
| `SUBSCRIPT_VALUE_FIELD` | `"value"` | `"object"` | JS subscript uses `object` field |
| `SUBSCRIPT_INDEX_FIELD` | `"subscript"` | `"index"` | JS subscript uses `index` field |
| `IF_CONDITION_FIELD` | `"condition"` | `"condition"` | Same as base (explicit re-declaration) |
| `IF_CONSEQUENCE_FIELD` | `"consequence"` | `"consequence"` | Same as base |
| `IF_ALTERNATIVE_FIELD` | `"alternative"` | `"alternative"` | Same as base |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` | Same as base |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` | Drops `"newline"`, keeps only `"\n"` |

The JavaScript frontend inherits base defaults for `NONE_LITERAL` (`"None"`), `TRUE_LITERAL` (`"True"`), `FALSE_LITERAL` (`"False"`), and `DEFAULT_RETURN_VALUE` (`"None"`). Note these are Python-canonical forms, not JavaScript-native. The dispatch table maps JS-native node types (`null`, `undefined`, `true`, `false`) to canonical lowering methods.

## Expression Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` (base) | `LOAD_VAR` |
| `number` | `_lower_const_literal` (base) | `CONST` |
| `string` | `_lower_const_literal` (base) | `CONST` |
| `template_string` | `_lower_template_string` | `CONST` (no subs) or `CONST` + `BINOP("+")` chain |
| `template_substitution` | `_lower_template_substitution` | Delegates to inner expression |
| `true` | `_lower_canonical_true` (base) | `CONST "True"` |
| `false` | `_lower_canonical_false` (base) | `CONST "False"` |
| `null` | `_lower_canonical_none` (base) | `CONST "None"` |
| `undefined` | `_lower_canonical_none` (base) | `CONST "None"` |
| `binary_expression` | `_lower_binop` (base) | `BINOP` |
| `augmented_assignment_expression` | `_lower_binop` (base) | `BINOP` |
| `unary_expression` | `_lower_unop` (base) | `UNOP` |
| `update_expression` | `_lower_update_expr` (base) | `BINOP("+"/"-", operand, 1)` + store |
| `call_expression` | `_lower_call` (override) | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `new_expression` | `_lower_new_expression` | `NEW_OBJECT` + `CALL_METHOD("constructor")` |
| `member_expression` | `_lower_attribute` (override) | `LOAD_FIELD` |
| `subscript_expression` | `_lower_js_subscript` | `LOAD_INDEX` |
| `parenthesized_expression` | `_lower_paren` (base) | Delegates to inner expression |
| `array` | `_lower_list_literal` (base) | `NEW_ARRAY("list")` + `STORE_INDEX` per element |
| `object` | `_lower_js_object_literal` | `NEW_OBJECT("object")` + `STORE_INDEX` per pair |
| `assignment_expression` | `_lower_assignment_expr` | Lower RHS + store to target |
| `arrow_function` | `_lower_arrow_function` | `BRANCH` past body, `LABEL`, params, body/implicit return, `CONST` func ref |
| `ternary_expression` | `_lower_ternary` | `BRANCH_IF` + `STORE_VAR`/`LOAD_VAR` phi |
| `this` | `_lower_identifier` (base) | `LOAD_VAR "this"` |
| `super` | `_lower_identifier` (base) | `LOAD_VAR "super"` |
| `property_identifier` | `_lower_identifier` (base) | `LOAD_VAR` |
| `shorthand_property_identifier` | `_lower_identifier` (base) | `LOAD_VAR` |
| `await_expression` | `_lower_await_expression` | `CALL_FUNCTION("await", expr)` |
| `yield_expression` | `_lower_yield_expression` | `CALL_FUNCTION("yield", expr)` |
| `regex` | `_lower_const_literal` (base) | `CONST` |
| `sequence_expression` | `_lower_sequence_expression` | Evaluates all, returns last register |
| `spread_element` | `_lower_spread_element` | `CALL_FUNCTION("spread", expr)` |
| `function` | `_lower_function_expression` | Anonymous function definition |
| `function_expression` | `_lower_function_expression` | Anonymous function definition |
| `generator_function` | `_lower_function_expression` | Anonymous function definition |
| `generator_function_declaration` | `_lower_function_def` (base) | Named function definition |

## Statement Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `expression_statement` | `_lower_expression_statement` (base) | Unwraps inner expression |
| `lexical_declaration` | `_lower_var_declaration` (override) | `STORE_VAR` per declarator (with destructuring support) |
| `variable_declaration` | `_lower_var_declaration` (override) | `STORE_VAR` per declarator (with destructuring support) |
| `return_statement` | `_lower_return` (base) | `RETURN` |
| `if_statement` | `_lower_if` (base) | `BRANCH_IF` + labels |
| `while_statement` | `_lower_while` (base) | `LABEL` + `BRANCH_IF` loop |
| `for_statement` | `_lower_c_style_for` (base) | C-style for(init; cond; update) loop |
| `for_in_statement` | `_lower_for_in` | for...in / for...of dispatch |
| `function_declaration` | `_lower_function_def` (base) | Named function definition |
| `class_declaration` | `_lower_class_def` (override) | Class with `method_definition` and `class_static_block` handling |
| `throw_statement` | `_lower_throw` | `THROW` |
| `statement_block` | `_lower_block` (base) | Iterate children as statements |
| `empty_statement` | `lambda _: None` | No-op |
| `break_statement` | `_lower_break` (base) | `BRANCH` to break target |
| `continue_statement` | `_lower_continue` (base) | `BRANCH` to continue label |
| `try_statement` | `_lower_try` | Labeled try/catch/finally blocks |
| `switch_statement` | `_lower_switch_statement` | `BINOP("===")` + `BRANCH_IF` chain |
| `do_statement` | `_lower_do_statement` | `do...while` loop structure |
| `labeled_statement` | `_lower_labeled_statement` | `LABEL` + inner statement |
| `import_statement` | `lambda _: None` | No-op (imports ignored) |
| `export_statement` | `_lower_export_statement` | Unwraps and lowers inner declaration |

## Language-Specific Lowering Methods

### `_lower_var_declaration(node)`

Overrides base to handle JavaScript destructuring patterns:
- `object_pattern` (`const { a, b } = obj`): calls `_lower_object_destructure`
- `array_pattern` (`const [a, b] = arr`): calls `_lower_array_destructure`
- Plain name with value: `STORE_VAR(name, val_reg)`
- Plain name without value: `CONST("None")` + `STORE_VAR`

### `_lower_object_destructure(pattern_node, val_reg, parent_node)`

Handles `{ a, b } = obj` and `{ x: localX } = obj`:
- `shorthand_property_identifier_pattern`: `LOAD_FIELD(val_reg, prop_name)` + `STORE_VAR(prop_name, field_reg)`
- `pair_pattern`: `LOAD_FIELD(val_reg, key_name)` + `STORE_VAR(local_name, field_reg)`

### `_lower_array_destructure(pattern_node, val_reg, parent_node)`

Handles `[a, b] = arr`: for each named child at index `i`, emits `CONST(i)` + `LOAD_INDEX(val_reg, idx_reg)` + `STORE_VAR(name, elem_reg)`.

### `_lower_attribute(node) -> str`

Overrides base to use JS field names: reads `object` and `property` fields from `member_expression` nodes. Emits `LOAD_FIELD(obj_reg, field_name)`.

### `_lower_js_subscript(node) -> str`

Handles `subscript_expression` (e.g., `arr[i]`): reads `object` and `index` fields, emits `LOAD_INDEX(obj_reg, idx_reg)`.

### `_lower_call(node) -> str`

Overrides base call handling for JS:
1. If `func_node.type == "member_expression"`: reads `object`/`property` fields, emits `CALL_METHOD`
2. If `func_node.type == "identifier"`: emits `CALL_FUNCTION`
3. Otherwise: lowers func expression, emits `CALL_UNKNOWN`

### `_lower_store_target(target, val_reg, parent_node)`

Overrides base to handle JS node types:
- `identifier`: `STORE_VAR`
- `member_expression`: `STORE_FIELD` (reads `object`/`property` fields)
- `subscript_expression`: `STORE_INDEX` (reads `object`/`index` fields)
- Fallback: `STORE_VAR` with node text

### `_lower_assignment_expr(node) -> str`

Handles JS assignment expressions (which are expressions, not statements): lowers RHS, stores to target via `_lower_store_target`, returns `val_reg`.

### `_lower_js_object_literal(node) -> str`

Lowers JS object literals `{ key: val, shorthand }`:
- `pair` children: `CONST(key)` + lower value + `STORE_INDEX`
- `shorthand_property_identifier`: `CONST(name)` + `LOAD_VAR(name)` + `STORE_INDEX`

Uses `NEW_OBJECT("object")` (compared to Python's `NEW_OBJECT("dict")`).

### `_lower_arrow_function(node) -> str`

Lowers `(x) => expr` or `(x) => { ... }`:
1. Generates synthetic name `__arrow_<n>`
2. `BRANCH` past body, `LABEL(func_<name>_<n>)`
3. If params is a single `identifier`, calls `_lower_param` directly; otherwise `_lower_params`
4. If body is `statement_block`: lowers as block. Otherwise: expression body with implicit `RETURN`
5. Implicit `RETURN "None"` at end
6. Returns `CONST("<function:__arrow_<n>@func_..._<n>>")` as function reference

### `_lower_ternary(node) -> str`

Lowers `cond ? trueExpr : falseExpr`:
1. Evaluates condition
2. `BRANCH_IF(cond, ternary_true, ternary_false)`
3. Each branch evaluates its expression and stores to `__ternary_<n>` via `STORE_VAR`
4. After `BRANCH` to end, `LOAD_VAR` the result from the phi variable

### `_lower_for_in(node)`

Dispatch between `for...in` and `for...of`:
- Checks `operator` field: if text is `"of"`, delegates to `_lower_for_of`
- For `for...in`: calls `keys(obj)` via `CALL_FUNCTION`, then iterates over keys array with index-based loop

### `_lower_for_of(node)`

Lowers `for (const x of iterable)` as index-based iteration:
1. Evaluates iterable, calls `len(iterable)`
2. Index-based loop: `BINOP("<")` + `BRANCH_IF` + `LOAD_INDEX`
3. Update: increment index, `STORE_VAR("__for_idx", new_idx)`

### `_lower_param(child)`

Overrides base to handle JS parameter types:
- `identifier`: bare parameter
- `assignment_pattern`, `object_pattern`, `array_pattern`: uses full node text as parameter name
- Other types: falls back to `_extract_param_name`

### `_lower_try(node)`

Parses JS `try { ... } catch (e) { ... } finally { ... }`:
- `handler` field: extracts `parameter` (catch variable) and `body`
- `finalizer` field: extracts inner `body`
- Delegates to base `_lower_try_catch`

### `_lower_throw(node)`

Delegates to `_lower_raise_or_throw(node, keyword="throw")`, which emits `THROW`.

### `_lower_alternative(alt_node, end_label)`

Overrides base to handle JS `else if` chains:
- `else_clause`: lowers children excluding `else` keyword
- `if_statement`: recurses into `_lower_if` (JS chains `else if` as nested `if_statement`)
- Other: delegates to `_lower_block`

### `_lower_class_def(node)`

Overrides base to handle JS class body members:
- `method_definition` children: delegates to `_lower_method_def`
- `class_static_block` children: delegates to `_lower_class_static_block`
- Other named children: lowered as statements

### `_lower_method_def(node)`

Lowers a method within a class body:
1. Extracts `name`, `parameters`, `body` fields
2. `BRANCH` past body, `LABEL(func_<name>_<n>)`
3. Lower params and body
4. Implicit `RETURN "None"`
5. `CONST` function reference + `STORE_VAR`

### `_lower_new_expression(node) -> str`

Lowers `new Foo(args)`:
1. `NEW_OBJECT(class_name)` -- creates the object
2. `CALL_METHOD(obj_reg, "constructor", ...arg_regs)` -- calls constructor

### `_lower_await_expression(node) -> str`

Lowers `await expr` as `CALL_FUNCTION("await", expr_reg)`.

### `_lower_yield_expression(node) -> str`

Lowers `yield expr` as `CALL_FUNCTION("yield", expr_reg)`. Bare `yield` (no argument) emits `CONST("None")` then `CALL_FUNCTION("yield", none_reg)`.

### `_lower_sequence_expression(node) -> str`

Lowers `(a, b, c)` (JS comma operator): evaluates all expressions left to right, returns the register of the last one.

### `_lower_spread_element(node) -> str`

Lowers `...expr` as `CALL_FUNCTION("spread", expr_reg)`.

### `_lower_function_expression(node) -> str`

Lowers anonymous function expressions (`function() { ... }`, `function* () { ... }`):
- If `name` field exists, uses it; otherwise generates `__anon_<n>`
- Same structure as `_lower_function_def` but returns the function reference register instead of storing to a variable

### `_lower_template_string(node) -> str`

Lowers template strings (`` `Hello ${name}!` ``):
- If no `template_substitution` children: falls back to `_lower_const_literal`
- Otherwise: concatenates fragments and substitution results using `BINOP("+")`
- Skips backtick (`` ` ``) tokens, emits `CONST` for string fragments

### `_lower_template_substitution(node) -> str`

Lowers `${expr}` inside template strings: extracts the first named child and lowers it as an expression.

### `_lower_switch_statement(node)`

Lowers `switch(x) { case a: ... default: ... }` as an if/else chain:
1. Evaluates discriminant (`value` field)
2. Pushes `end_label` onto `_break_target_stack`
3. For each `switch_case`: `BINOP("===")` comparison + `BRANCH_IF`
4. For `switch_default`: unconditionally lower body
5. Pops break target stack

### `_lower_switch_case_body(case_node)`

Helper: lowers all named children of a case/default clause as statements, excluding `switch_case`/`switch_default` type children.

### `_lower_do_statement(node)`

Lowers `do { body } while (cond)`:
1. `LABEL(do_body)` -- body executes first
2. Push loop context (continue targets `cond_label`, break targets `end_label`)
3. Lower body, pop loop context
4. `LABEL(do_cond)`, evaluate condition
5. `BRANCH_IF(cond, do_body, do_end)`

### `_lower_labeled_statement(node)`

Lowers `label: stmt`: emits `LABEL(<fresh_label>)` then lowers the body statement.

### `_lower_export_statement(node)`

Lowers `export ...` by unwrapping: iterates named children (excluding `export` and `default` keyword nodes) and lowers each as a statement.

### `_lower_class_static_block(node)`

Lowers `static { ... }` inside class body: if a `body` field exists, lowers it as a block. Otherwise falls back to lowering all named non-`static` children as statements.

### `_extract_var_name(node) -> str | None`

Helper to extract variable name from:
- `identifier` node: returns text directly
- `lexical_declaration` / `variable_declaration`: finds `variable_declarator` child, extracts `name` field

### `_extract_call_args(args_node) -> list[str]`

Overrides base to use simpler filtering: includes all named children except `(`, `)`, `,`.

## Canonical Literal Handling

| JS AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |
| `null` | `_lower_canonical_none` | `CONST "None"` |
| `undefined` | `_lower_canonical_none` | `CONST "None"` |

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

2. **For...in vs For...of**: Both are dispatched from `_lower_for_in` by checking the `operator` field text. `for...in` calls `keys(obj)` to get an array of keys then iterates. `for...of` iterates directly by index. Both use `STORE_VAR("__for_idx", ...)` for index tracking.

3. **Switch-to-if lowering**: Switch statements are lowered as strict equality (`===`) comparison chains, not as jump tables. The break target stack is used to handle `break` within switch cases.

4. **Arrow functions**: Arrow functions with expression bodies get an implicit `RETURN` for the expression value. Block-body arrows are lowered like regular function bodies. All arrow functions get synthetic names `__arrow_<n>`.

5. **Template string concatenation**: Template strings with substitutions are lowered as `CONST` fragment + `BINOP("+")` chains. Plain template strings (no substitutions) are treated as `CONST` literals.

6. **New expression model**: `new Foo(args)` is modeled as `NEW_OBJECT` + `CALL_METHOD("constructor", ...)`, separating object creation from initialization.

7. **Import/export handling**: Import statements are no-ops. Export statements are unwrapped to lower their inner declarations, discarding the export modifier.

8. **Else-if chaining**: JS `else if` is handled as a nested `if_statement` inside an `else_clause`, which differs from Python's `elif_clause`. The `_lower_alternative` override handles this by recursing into `_lower_if`.

9. **Augmented assignment as expression**: `augmented_assignment_expression` is in the expression dispatch table (mapped to `_lower_binop`), reflecting that `+=` is an expression in JS, not a statement.

10. **Class static blocks**: `static { ... }` blocks inside classes are supported via `_lower_class_static_block`.
