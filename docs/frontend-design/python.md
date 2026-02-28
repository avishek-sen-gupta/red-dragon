# Python Frontend

> `interpreter/frontends/python.py` · Extends `BaseFrontend` · ~1139 lines

## Overview

The Python frontend lowers tree-sitter Python ASTs into the RedDragon flattened three-address-code (TAC) IR. It is the most feature-rich frontend in the project, covering Python-specific constructs such as list/dict/set comprehensions, generator expressions, lambda, `with` statements, decorators, match/case, walrus operator (`:=`), slicing, tuple unpacking, f-string interpolation, and `import`/`import from`.

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── PythonFrontend (python.py)   ← this file
```

No other frontend extends `PythonFrontend`.

## Overridden Constants

| Constant | BaseFrontend Default | PythonFrontend Value | Notes |
|---|---|---|---|
| `PAREN_EXPR_TYPE` | `"parenthesized_expression"` | `"parenthesized_expression"` | Same as base (explicit re-declaration) |
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"attribute"` | Same as base |
| `SUBSCRIPT_VALUE_FIELD` | `"value"` | `"value"` | Same as base |
| `SUBSCRIPT_INDEX_FIELD` | `"subscript"` | `"subscript"` | Same as base |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` | Same as base |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"newline", "\n"})` | Same as base |

The Python frontend uses all the base defaults for `NONE_LITERAL` (`"None"`), `TRUE_LITERAL` (`"True"`), `FALSE_LITERAL` (`"False"`), and `DEFAULT_RETURN_VALUE` (`"None"`). These are already Python-canonical, so no override is needed.

Also declares a class-level constant:

| Constant | Value | Usage |
|---|---|---|
| `_WILDCARD_PATTERN` | `"_"` | Used in match/case to detect the default/wildcard arm |

## Expression Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` (base) | `LOAD_VAR` |
| `integer` | `_lower_const_literal` (base) | `CONST` |
| `float` | `_lower_const_literal` (base) | `CONST` |
| `string` | `_lower_const_literal` (base) | `CONST` |
| `concatenated_string` | `_lower_const_literal` (base) | `CONST` |
| `true` | `_lower_canonical_true` (base) | `CONST "True"` |
| `false` | `_lower_canonical_false` (base) | `CONST "False"` |
| `none` | `_lower_canonical_none` (base) | `CONST "None"` |
| `binary_operator` | `_lower_binop` (base) | `BINOP` |
| `boolean_operator` | `_lower_binop` (base) | `BINOP` |
| `comparison_operator` | `_lower_comparison` (base) | `BINOP` |
| `unary_operator` | `_lower_unop` (base) | `UNOP` |
| `not_operator` | `_lower_unop` (base) | `UNOP` |
| `call` | `_lower_call` (override) | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `attribute` | `_lower_attribute` (base) | `LOAD_FIELD` |
| `subscript` | `_lower_subscript` (base) | `LOAD_INDEX` |
| `parenthesized_expression` | `_lower_paren` (base) | (delegates to inner) |
| `list` | `_lower_list_literal` (base) | `NEW_ARRAY` + `STORE_INDEX` per element |
| `dictionary` | `_lower_dict_literal` (base) | `NEW_OBJECT` + `STORE_INDEX` per pair |
| `tuple` | `_lower_tuple_literal` | `NEW_ARRAY("tuple")` + `STORE_INDEX` per element |
| `conditional_expression` | `_lower_conditional_expr` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` (ternary phi) |
| `list_comprehension` | `_lower_list_comprehension` | `NEW_ARRAY` + loop + `STORE_INDEX` |
| `dictionary_comprehension` | `_lower_dict_comprehension` | `NEW_OBJECT` + loop + `STORE_INDEX` |
| `lambda` | `_lower_lambda` | `BRANCH` past body, `LABEL`, params, `RETURN`, `CONST` func ref |
| `generator_expression` | `_lower_generator_expression` | `NEW_ARRAY` + loop + `CALL_FUNCTION("generator", ...)` |
| `set_comprehension` | `_lower_set_comprehension` | `NEW_OBJECT("set")` + loop + `STORE_INDEX` |
| `set` | `_lower_set_literal` | `NEW_OBJECT("set")` + `STORE_INDEX` per element |
| `yield` | `_lower_yield` | `CALL_FUNCTION("yield", ...)` |
| `await` | `_lower_await` | `CALL_FUNCTION("await", ...)` |
| `named_expression` | `_lower_named_expression` | lower value + `STORE_VAR` |
| `slice` | `_lower_slice` | `CALL_FUNCTION("slice", start, stop, step)` |
| `keyword_separator` | `_lower_noop_expr` | `CONST "None"` |
| `positional_separator` | `_lower_noop_expr` | `CONST "None"` |
| `list_pattern` | `_lower_list_pattern` | `NEW_ARRAY("list")` + `STORE_INDEX` per element |
| `case_pattern` | `_lower_case_pattern` | Delegates to inner child |
| `interpolation` | `_lower_interpolation` | Delegates to inner expression child |
| `format_specifier` | `_lower_const_literal` (base) | `CONST` |
| `string_content` | `_lower_const_literal` (base) | `CONST` |
| `string_start` | `_lower_const_literal` (base) | `CONST` |
| `string_end` | `_lower_const_literal` (base) | `CONST` |
| `type_conversion` | `_lower_const_literal` (base) | `CONST` |

## Statement Dispatch Table

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `expression_statement` | `_lower_expression_statement` (base) | Unwraps inner expression |
| `assignment` | `_lower_assignment` (base) | Lower RHS + `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `augmented_assignment` | `_lower_augmented_assignment` (base) | `BINOP` + store |
| `return_statement` | `_lower_return` (base) | `RETURN` (with `CONST "None"` if bare return) |
| `if_statement` | `_lower_if` (base) | `BRANCH_IF` + labels |
| `while_statement` | `_lower_while` (base) | `LABEL` + `BRANCH_IF` loop |
| `for_statement` | `_lower_for` (override) | Index-based iteration loop |
| `function_definition` | `_lower_function_def` (base) | `BRANCH` past body, `LABEL`, params, body, implicit `RETURN`, `STORE_VAR` func ref |
| `class_definition` | `_lower_class_def` (base) | `BRANCH` past body, `LABEL`, body, `STORE_VAR` class ref |
| `raise_statement` | `_lower_raise` | `THROW` |
| `try_statement` | `_lower_try` (override) | `LABEL` blocks for try/except/else/finally |
| `pass_statement` | `lambda _: None` | No-op |
| `break_statement` | `_lower_break` (base) | `BRANCH` to break target |
| `continue_statement` | `_lower_continue` (base) | `BRANCH` to continue label |
| `with_statement` | `_lower_with` | `CALL_METHOD("__enter__")` + body + `CALL_METHOD("__exit__")` |
| `decorated_definition` | `_lower_decorated_def` | Lower inner def, then wrap with `CALL_FUNCTION(decorator, func)` bottom-up |
| `assert_statement` | `_lower_assert` | `CALL_FUNCTION("assert", ...)` |
| `global_statement` | `lambda _: None` | No-op |
| `nonlocal_statement` | `lambda _: None` | No-op |
| `delete_statement` | `_lower_delete` | `CALL_FUNCTION("del", target)` per target |
| `import_statement` | `_lower_import` | `CALL_FUNCTION("import", module)` + `STORE_VAR` |
| `import_from_statement` | `_lower_import_from` | `CALL_FUNCTION("import", "from X import Y")` + `STORE_VAR` per name |
| `match_statement` | `_lower_match` | `BINOP("==")` + `BRANCH_IF` chain (if/elif/else) |
| `type_alias_statement` | `lambda _: None` | No-op |

## Language-Specific Lowering Methods

### `_lower_call(node) -> str`

Overrides the base `_lower_call` to handle a Python-specific edge case: when a generator expression is the sole argument to a function call, tree-sitter makes it the `arguments` node directly (type `generator_expression`) rather than wrapping it in an `argument_list`. The method checks `args_node.type == "generator_expression"` and wraps it in a single-element list before proceeding.

Call dispatch order:
1. If `func_node.type == "attribute"` -- emits `CALL_METHOD`
2. If `func_node.type == "identifier"` -- emits `CALL_FUNCTION`
3. Otherwise -- emits `CALL_UNKNOWN` with a dynamic target register

### `_lower_for(node)`

Lowers Python `for x in iterable:` as an index-based iteration loop:
1. Evaluates iterable, calls `len(iterable)` via `CALL_FUNCTION`
2. Initializes index counter at `0`
3. Loop condition: `BINOP("<", idx, len)`
4. Body: `LOAD_INDEX` from iterable, store to loop variable via `_lower_store_target`
5. Update: increment via `_emit_for_increment`

### `_emit_for_increment(idx_reg, loop_label)`

Helper that emits index increment: `CONST "1"`, `BINOP("+", idx, one)`, `STORE_VAR("__for_idx", new_idx)`, `LOAD_VAR("__for_idx")`, `BRANCH` back to loop condition.

### `_lower_param(child)`

Handles four Python parameter types:
- `identifier` -- bare parameter name
- `default_parameter` -- `x=value`, extracts name from `name` field
- `typed_parameter` -- `x: int`, finds first `identifier` child
- `typed_default_parameter` -- `x: int = value`, extracts name from `name` field

Each emits: `SYMBOLIC("param:<name>")` + `STORE_VAR(<name>, reg)`.

### `_lower_raise(node)`

Delegates to `_lower_raise_or_throw(node, keyword="raise")`, which emits `THROW`.

### `_lower_try(node)`

Parses Python's `try/except/else/finally` structure:
- Iterates children looking for `except_clause`, `finally_clause`, `else_clause`
- For each `except_clause`: extracts exception type and variable from `as_pattern` children
- Delegates to base `_lower_try_catch(node, body, catch_clauses, finally_node, else_node)`

### `_lower_tuple_literal(node) -> str`

Lowers `(a, b, c)` as `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element.

### `_lower_conditional_expr(node) -> str`

Lowers `x if cond else y` (note: Python's ternary has `true_expr if cond else false_expr` order, not C-style). Parses children excluding `if`/`else` keywords, yielding `[true_expr, cond_expr, false_expr]`. Uses `BRANCH_IF` with labels and a temporary `STORE_VAR`/`LOAD_VAR` phi variable (`__ternary_<n>`).

### `_lower_store_target(target, val_reg, parent_node)`

Overrides base to handle tuple unpacking. If `target.type` is `"pattern_list"` or `"tuple_pattern"`, delegates to `_lower_tuple_unpack`. Otherwise calls `super()._lower_store_target()`.

### `_lower_tuple_unpack(target, val_reg, parent_node)`

For `a, b = expr`: iterates children (excluding `,`), emits `CONST(index)` + `LOAD_INDEX` per element, then recursively calls `_lower_store_target` for each (supporting nested unpacking).

### `_lower_list_comprehension(node) -> str`

Desugars `[expr for var in iterable if cond]`:
1. Creates result array: `NEW_ARRAY("list", 0)`
2. Initializes result index at 0
3. Calls `_lower_comprehension_loop` recursively for nested for-clauses

### `_lower_comprehension_loop(...)`

Recursive helper that emits one level of comprehension iteration. At the innermost level, applies if-clause filters via `BRANCH_IF` and stores the body expression result via `STORE_INDEX`. Supports arbitrary nesting of `for_in_clause` nodes.

### `_lower_dict_comprehension(node) -> str`

Desugars `{k: v for var in iterable if cond}`:
1. Creates result object: `NEW_OBJECT("dict")`
2. Emits index-based loop over iterable
3. Applies optional if-clause filter
4. Evaluates key/value from the `pair` node and stores via `STORE_INDEX`

### `_lower_with(node)`

Lowers `with ctx as var:` into `__enter__`/`__exit__` method calls:
1. Finds `with_clause` and its `with_item` children
2. For each item: evaluates context expression, emits `CALL_METHOD("__enter__")`, optionally `STORE_VAR` for the `as` variable
3. Lowers the body block
4. Exits in reverse (LIFO) order via `CALL_METHOD("__exit__")`

Handles `as_pattern` nodes for the `as` target and `as_pattern_target` wrapper nodes.

### `_lower_decorated_def(node)`

Lowers `@decorator\ndef f(): ...`:
1. Finds all `decorator` children and the inner `function_definition` or `class_definition`
2. Lowers the inner definition normally
3. Applies decorators bottom-up (last decorator is applied first): `LOAD_VAR(func)`, lower decorator expression, `CALL_FUNCTION(dec, func)`, `STORE_VAR(func, result)`

### `_lower_lambda(node) -> str`

Lowers `lambda x, y: expr`:
1. `BRANCH` past the lambda body
2. `LABEL(lambda_<n>)`
3. Lower parameters from `lambda_parameters` node
4. Lower body expression and emit `RETURN`
5. `LABEL(lambda_end_<n>)`
6. `CONST("func:<label>")` as the function reference

### `_lower_generator_expression(node) -> str`

Lowers `(expr for var in iterable)` like a list comprehension but wraps the result in `CALL_FUNCTION("generator", result_arr)`.

### `_lower_set_comprehension(node) -> str`

Lowers `{expr for var in iterable}` using `NEW_OBJECT("set")` and the shared comprehension loop infrastructure.

### `_lower_set_literal(node) -> str`

Lowers `{1, 2, 3}` as `NEW_OBJECT("set")` + `STORE_INDEX` per element with integer indices.

### `_lower_yield(node) -> str`

Lowers `yield expr` as `CALL_FUNCTION("yield", expr_regs...)`.

### `_lower_await(node) -> str`

Lowers `await expr` as `CALL_FUNCTION("await", expr_regs...)`.

### `_lower_named_expression(node) -> str`

Lowers `y := expr`: evaluates the value, emits `STORE_VAR(name, val_reg)`, returns the value register (so the expression result is available to the enclosing context).

### `_lower_assert(node)`

Lowers `assert cond, msg` as `CALL_FUNCTION("assert", cond_reg [, msg_reg])`.

### `_lower_delete(node)`

Lowers `del x, y` by iterating targets (unwrapping `expression_list` if present) and emitting `CALL_FUNCTION("del", target_reg)` for each.

### `_lower_import(node)`

Lowers `import os.path`:
1. `CALL_FUNCTION("import", "os.path")`
2. `STORE_VAR("os", import_reg)` -- stores under the top-level module name (splits on `.`)

### `_lower_import_from(node)`

Lowers `from X import Y, Z`:
- For each imported `dotted_name` child: `CALL_FUNCTION("import", "from X import Y")` + `STORE_VAR("Y", reg)`

### `_lower_match(node)`

Lowers `match subject:` as an if/elif chain:
1. Evaluates subject expression
2. For each `case_clause`:
   - If the pattern is `_` (wildcard): unconditionally lower the body
   - Otherwise: `BINOP("==", subject, pattern)` + `BRANCH_IF` to case body or next case
3. End label after all cases

### `_lower_slice(node) -> str`

Lowers `a[1:3:2]` as `CALL_FUNCTION("slice", start, stop, step)`. Missing components get `CONST("None")` placeholders. Parses colon positions in the child list to determine which parts are present.

### `_lower_noop_expr(node) -> str`

Returns `CONST("None")` for syntactic-only nodes like `keyword_separator` (`*`) and `positional_separator` (`/`).

### `_lower_list_pattern(node) -> str`

Lowers `[p1, p2, ...]` patterns in match/case as `NEW_ARRAY("list")` + `STORE_INDEX` per element (same structure as a list literal).

### `_lower_case_pattern(node) -> str`

Wrapper node unwrapper: extracts the first named child and lowers it as an expression.

### `_lower_interpolation(node) -> str`

Lowers `{expr}` inside f-strings by extracting the inner expression (excluding `format_specifier` and `type_conversion` children) and lowering it.

## Canonical Literal Handling

| Python AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |
| `none` | `_lower_canonical_none` | `CONST "None"` |

Since Python is the reference language for the IR, no translation is needed. The base class defaults (`NONE_LITERAL = "None"`, `TRUE_LITERAL = "True"`, `FALSE_LITERAL = "False"`) are already Python-canonical.

## Example

**Source (Python):**
```python
def greet(name):
    if name:
        return f"Hello, {name}!"
    return "Hello, World!"
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
    LOAD_VAR %2 name
    CONST %3 "Hello, "
    BINOP %4 "+" %3 %2
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

1. **For-loop model**: Python's `for x in iterable` is lowered as an index-based loop using `len()` and `LOAD_INDEX`, rather than using an iterator protocol. This simplifies IR analysis at the cost of not modeling lazy iteration.

2. **Comprehension recursion**: List/dict/set comprehensions and generator expressions all share a common recursive `_lower_comprehension_loop` helper, supporting arbitrary nesting of `for_in_clause` nodes.

3. **Generator expressions**: Modeled as eagerly-evaluated arrays wrapped in `CALL_FUNCTION("generator", ...)`, not as true lazy generators. This is a deliberate simplification for static analysis purposes.

4. **Decorator application order**: Decorators are applied bottom-up (innermost first), matching Python's actual execution semantics.

5. **With statement**: Models context managers via explicit `__enter__`/`__exit__` calls, handling multiple context managers in a single `with` statement with LIFO exit ordering.

6. **Match/case simplification**: Match statements are lowered as equality-comparison chains (`==`), not as full pattern matching. Wildcard `_` patterns are detected by text comparison. Structural pattern matching (e.g., class patterns, sequence patterns) is partially supported via `list_pattern` and `case_pattern` handlers.

7. **Import modeling**: Imports are modeled as `CALL_FUNCTION("import", ...)` calls, making them visible as side effects in the IR. `import os.path` stores under the top-level name `os`.

8. **Tuple unpacking**: Handled recursively via `_lower_store_target` override, supporting nested patterns like `(a, (b, c)) = expr`.

9. **No-op statements**: `pass`, `global`, `nonlocal`, and `type_alias_statement` are all treated as no-ops.

10. **F-string interpolation**: The `interpolation` handler extracts the inner expression, while `string_content`, `string_start`, `string_end`, `format_specifier`, and `type_conversion` are all lowered as `CONST` literals.
