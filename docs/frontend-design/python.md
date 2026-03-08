# Python Frontend

> `interpreter/frontends/python/` · Extends `BaseFrontend` · Per-language directory architecture

## Overview

The Python frontend lowers tree-sitter Python ASTs into the RedDragon flattened three-address-code (TAC) IR. It is the most feature-rich frontend in the project, covering Python-specific constructs such as list/dict/set comprehensions, generator expressions, lambda, `with` statements, decorators, match/case, walrus operator (`:=`), slicing, tuple unpacking, f-string interpolation, and `import`/`import from`.

## Directory Structure

```
interpreter/frontends/python/
├── frontend.py        # PythonFrontend class (thin orchestrator)
├── node_types.py      # PythonNodeType constants class
├── expressions.py     # Expression lowerers (pure functions)
├── control_flow.py    # Control flow lowerers (pure functions)
├── declarations.py    # Declaration lowerers (pure functions)
└── assignments.py     # Assignment lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── PythonFrontend (python/frontend.py)   ← this frontend
```

No other frontend extends `PythonFrontend`.

## GrammarConstants (from `_build_constants()`)

| Field | Value | Notes |
|---|---|---|
| `attr_object_field` | `"object"` | Same as base |
| `attr_attribute_field` | `"attribute"` | Same as base |
| `attribute_node_type` | `"attribute"` | Same as base |
| `subscript_value_field` | `"value"` | Same as base |
| `subscript_index_field` | `"subscript"` | Same as base |
| `comment_types` | `frozenset({"comment"})` | Via `PythonNodeType.COMMENT` |
| `noise_types` | `frozenset({"newline", "\n"})` | Via `PythonNodeType.NEWLINE`, `.NEWLINE_CHAR` |
| `block_node_types` | `frozenset({"block", "module"})` | Via `PythonNodeType.BLOCK`, `.MODULE` |
| `paren_expr_type` | `"parenthesized_expression"` | Via `PythonNodeType.PARENTHESIZED_EXPRESSION` |

The Python frontend uses all the base defaults for `none_literal` (`"None"`), `true_literal` (`"True"`), `false_literal` (`"False"`), and `default_return_value` (`"None"`). These are already Python-canonical, so no override is needed.

## Expression Dispatch Table (from `_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `integer` | `common_expr.lower_const_literal` | `CONST` |
| `float` | `common_expr.lower_const_literal` | `CONST` |
| `string` | `py_expr.lower_python_string` | `CONST` (plain) or `CONST` + `BINOP("+")` chain (f-string) |
| `concatenated_string` | `common_expr.lower_const_literal` | `CONST` |
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `none` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `binary_operator` | `common_expr.lower_binop` | `BINOP` |
| `boolean_operator` | `common_expr.lower_binop` | `BINOP` |
| `comparison_operator` | `common_expr.lower_comparison` | `BINOP` |
| `unary_operator` | `common_expr.lower_unop` | `UNOP` |
| `not_operator` | `common_expr.lower_unop` | `UNOP` |
| `call` | `py_expr.lower_call` | `CALL_METHOD` / `CALL_FUNCTION` / `CALL_UNKNOWN` |
| `attribute` | `common_expr.lower_attribute` | `LOAD_FIELD` |
| `subscript` | `common_expr.lower_subscript` | `LOAD_INDEX` |
| `parenthesized_expression` | `common_expr.lower_paren` | (delegates to inner) |
| `list` | `common_expr.lower_list_literal` | `NEW_ARRAY` + `STORE_INDEX` per element |
| `dictionary` | `common_expr.lower_dict_literal` | `NEW_OBJECT` + `STORE_INDEX` per pair |
| `tuple` | `py_expr.lower_tuple_literal` | `NEW_ARRAY("tuple")` + `STORE_INDEX` per element |
| `conditional_expression` | `py_expr.lower_conditional_expr` | `BRANCH_IF` + `STORE_VAR` + `LOAD_VAR` (ternary phi) |
| `list_comprehension` | `py_expr.lower_list_comprehension` | `NEW_ARRAY` + loop + `STORE_INDEX` |
| `dictionary_comprehension` | `py_expr.lower_dict_comprehension` | `NEW_OBJECT` + loop + `STORE_INDEX` |
| `lambda` | `py_expr.lower_lambda` | `BRANCH` past body, `LABEL`, params, `RETURN`, `CONST` func ref |
| `generator_expression` | `py_expr.lower_generator_expression` | `NEW_ARRAY` + loop + `CALL_FUNCTION("generator", ...)` |
| `set_comprehension` | `py_expr.lower_set_comprehension` | `NEW_OBJECT("set")` + loop + `STORE_INDEX` |
| `set` | `py_expr.lower_set_literal` | `NEW_OBJECT("set")` + `STORE_INDEX` per element |
| `yield` | `py_expr.lower_yield` | `CALL_FUNCTION("yield", ...)` |
| `await` | `py_expr.lower_await` | `CALL_FUNCTION("await", ...)` |
| `named_expression` | `py_expr.lower_named_expression` | lower value + `STORE_VAR` |
| `slice` | `py_expr.lower_slice` | `CALL_FUNCTION("slice", start, stop, step)` |
| `keyword_separator` | `py_expr.lower_noop_expr` | `CONST "None"` |
| `positional_separator` | `py_expr.lower_noop_expr` | `CONST "None"` |
| `list_pattern` | `py_expr.lower_list_pattern` | `NEW_ARRAY("list")` + `STORE_INDEX` per element |
| `case_pattern` | `py_expr.lower_case_pattern` | Delegates to inner child |
| `interpolation` | `py_expr.lower_interpolation` | Delegates to inner expression child |
| `format_specifier` | `common_expr.lower_const_literal` | `CONST` |
| `string_content` | `common_expr.lower_const_literal` | `CONST` |
| `string_start` | `common_expr.lower_const_literal` | `CONST` |
| `string_end` | `common_expr.lower_const_literal` | `CONST` |
| `type_conversion` | `common_expr.lower_const_literal` | `CONST` |
| `ellipsis` | `common_expr.lower_const_literal` | `CONST` |
| `list_splat` | `py_expr.lower_splat_expr` | `CALL_FUNCTION("spread", ...)` |
| `dictionary_splat` | `py_expr.lower_splat_expr` | `CALL_FUNCTION("spread", ...)` |
| `expression_list` | `py_expr.lower_tuple_literal` | `NEW_ARRAY("tuple")` + `STORE_INDEX` per element |
| `dotted_name` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `dict_pattern` | `py_expr.lower_dict_pattern` | `NEW_OBJECT("dict_pattern")` + `STORE_INDEX` per pair |
| `splat_pattern` | `py_expr.lower_splat_expr` | `CALL_FUNCTION("spread", ...)` |

## Statement Dispatch Table (from `_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `common_assign.lower_expression_statement` | Unwraps inner expression |
| `assignment` | `py_assign.lower_assignment` | Lower RHS + `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` |
| `augmented_assignment` | `py_assign.lower_augmented_assignment` | `BINOP` + store |
| `return_statement` | `common_assign.lower_return` | `RETURN` (with `CONST "None"` if bare return) |
| `if_statement` | `py_cf.lower_python_if` | `BRANCH_IF` + labels (with elif/else chain support) |
| `while_statement` | `common_cf.lower_while` | `LABEL` + `BRANCH_IF` loop |
| `for_statement` | `py_cf.lower_for` | Index-based iteration loop |
| `function_definition` | `common_decl.lower_function_def` | `BRANCH` past body, `LABEL`, params, body, implicit `RETURN`, `STORE_VAR` func ref |
| `class_definition` | `py_decl.lower_python_class_def` | `BRANCH` past body, `LABEL`, body, `STORE_VAR` class ref (with parent extraction) |
| `raise_statement` | `py_cf.lower_raise` | `THROW` |
| `try_statement` | `py_cf.lower_try` | `LABEL` blocks for try/except/else/finally |
| `pass_statement` | `lambda ctx, node: None` | No-op |
| `break_statement` | `common_cf.lower_break` | `BRANCH` to break target |
| `continue_statement` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `with_statement` | `py_cf.lower_with` | `CALL_METHOD("__enter__")` + body + `CALL_METHOD("__exit__")` |
| `decorated_definition` | `py_cf.lower_decorated_def` | Lower inner def, then wrap with `CALL_FUNCTION(decorator, func)` bottom-up |
| `assert_statement` | `py_cf.lower_assert` | `CALL_FUNCTION("assert", ...)` |
| `global_statement` | `lambda ctx, node: None` | No-op |
| `nonlocal_statement` | `lambda ctx, node: None` | No-op |
| `delete_statement` | `py_cf.lower_delete` | `CALL_FUNCTION("del", target)` per target |
| `import_statement` | `py_cf.lower_import` | `CALL_FUNCTION("import", module)` + `STORE_VAR` |
| `import_from_statement` | `py_cf.lower_import_from` | `CALL_FUNCTION("import", "from X import Y")` + `STORE_VAR` per name |
| `match_statement` | `py_cf.lower_match` | `BINOP("==")` + `BRANCH_IF` chain (if/elif/else) |
| `type_alias_statement` | `lambda ctx, node: None` | No-op |

## Language-Specific Lowering Methods

### `py_expr.lower_call(ctx, node) -> str`

Handles a Python-specific edge case: when a generator expression is the sole argument to a function call, tree-sitter makes it the `arguments` node directly (type `generator_expression`) rather than wrapping it in an `argument_list`. The function checks `args_node.type == "generator_expression"` and wraps it in a single-element list before proceeding.

Call dispatch order:
1. If `func_node.type == "attribute"` -- emits `CALL_METHOD`
2. If `func_node.type == "identifier"` -- emits `CALL_FUNCTION`
3. Otherwise -- emits `CALL_UNKNOWN` with a dynamic target register

### `py_cf.lower_for(ctx, node)`

Lowers Python `for x in iterable:` as an index-based iteration loop:
1. Evaluates iterable, calls `len(iterable)` via `CALL_FUNCTION`
2. Initializes index counter at `0`
3. Loop condition: `BINOP("<", idx, len)`
4. Body: `LOAD_INDEX` from iterable, store to loop variable via `py_expr.lower_store_target`
5. Update: increment via `py_expr._emit_for_increment`

### `py_expr._emit_for_increment(ctx, idx_reg, loop_label)`

Helper that emits index increment: `CONST "1"`, `BINOP("+", idx, one)`, `STORE_VAR("__for_idx", new_idx)`, `LOAD_VAR("__for_idx")`, `BRANCH` back to loop condition.

### `py_expr._lower_python_param(ctx, child)`

Handles four Python parameter types:
- `identifier` -- bare parameter name
- `default_parameter` -- `x=value`, extracts name from `name` field
- `typed_parameter` -- `x: int`, finds first `identifier` child
- `typed_default_parameter` -- `x: int = value`, extracts name from `name` field

Each emits: `SYMBOLIC("param:<name>")` + `STORE_VAR(<name>, reg)`.

### `py_cf.lower_raise(ctx, node)`

Delegates to `lower_raise_or_throw(ctx, node, keyword="raise")`, which emits `THROW`.

### `py_cf.lower_try(ctx, node)`

Parses Python's `try/except/else/finally` structure:
- Iterates children looking for `except_clause`, `finally_clause`, `else_clause`
- For each `except_clause`: extracts exception type and variable from `as_pattern` children
- Delegates to `lower_try_catch(ctx, node, body, catch_clauses, finally_node, else_node)`

### `py_expr.lower_tuple_literal(ctx, node) -> str`

Lowers `(a, b, c)` as `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element.

### `py_expr.lower_conditional_expr(ctx, node) -> str`

Lowers `x if cond else y` (note: Python's ternary has `true_expr if cond else false_expr` order, not C-style). Parses children excluding `if`/`else` keywords, yielding `[true_expr, cond_expr, false_expr]`. Uses `BRANCH_IF` with labels and a temporary `STORE_VAR`/`LOAD_VAR` phi variable (`__ternary_<n>`).

### `py_expr.lower_store_target(ctx, target, val_reg, parent_node)`

Python-specific store target that adds tuple/pattern_list unpacking. If `target.type` is `"pattern_list"` or `"tuple_pattern"`, delegates to `py_expr.lower_tuple_unpack`. Otherwise calls `common_lower_store_target`.

### `py_expr.lower_tuple_unpack(ctx, target, val_reg, parent_node)`

For `a, b = expr`: iterates children (excluding `,`), emits `CONST(index)` + `LOAD_INDEX` per element, then recursively calls `lower_store_target` for each (supporting nested unpacking).

### `py_expr.lower_list_comprehension(ctx, node) -> str`

Desugars `[expr for var in iterable if cond]`:
1. Creates result array: `NEW_ARRAY("list", 0)`
2. Initializes result index at 0
3. Calls `py_expr._lower_comprehension_loop` recursively for nested for-clauses

### `py_expr._lower_comprehension_loop(...)`

Recursive helper that emits one level of comprehension iteration. At the innermost level, applies if-clause filters via `BRANCH_IF` and stores the body expression result via `STORE_INDEX`. Supports arbitrary nesting of `for_in_clause` nodes.

### `py_expr.lower_dict_comprehension(ctx, node) -> str`

Desugars `{k: v for var in iterable if cond}`:
1. Creates result object: `NEW_OBJECT("dict")`
2. Emits index-based loop over iterable
3. Applies optional if-clause filter
4. Evaluates key/value from the `pair` node and stores via `STORE_INDEX`

### `py_cf.lower_with(ctx, node)`

Lowers `with ctx as var:` into `__enter__`/`__exit__` method calls:
1. Finds `with_clause` and its `with_item` children
2. For each item: evaluates context expression, emits `CALL_METHOD("__enter__")`, optionally `STORE_VAR` for the `as` variable
3. Lowers the body block
4. Exits in reverse (LIFO) order via `CALL_METHOD("__exit__")`

Handles `as_pattern` nodes for the `as` target and `as_pattern_target` wrapper nodes.

### `py_cf.lower_decorated_def(ctx, node)`

Lowers `@decorator\ndef f(): ...`:
1. Finds all `decorator` children and the inner `function_definition` or `class_definition`
2. Lowers the inner definition normally
3. Applies decorators bottom-up (last decorator is applied first): `LOAD_VAR(func)`, lower decorator expression, `CALL_FUNCTION(dec, func)`, `STORE_VAR(func, result)`

### `py_expr.lower_lambda(ctx, node) -> str`

Lowers `lambda x, y: expr`:
1. `BRANCH` past the lambda body
2. `LABEL(lambda_<n>)`
3. Lower parameters from `lambda_parameters` node
4. Lower body expression and emit `RETURN`
5. `LABEL(lambda_end_<n>)`
6. `CONST("func:<label>")` as the function reference

### `py_expr.lower_generator_expression(ctx, node) -> str`

Lowers `(expr for var in iterable)` like a list comprehension but wraps the result in `CALL_FUNCTION("generator", result_arr)`.

### `py_expr.lower_set_comprehension(ctx, node) -> str`

Lowers `{expr for var in iterable}` using `NEW_OBJECT("set")` and the shared comprehension loop infrastructure.

### `py_expr.lower_set_literal(ctx, node) -> str`

Lowers `{1, 2, 3}` as `NEW_OBJECT("set")` + `STORE_INDEX` per element with integer indices.

### `py_expr.lower_yield(ctx, node) -> str`

Lowers `yield expr` as `CALL_FUNCTION("yield", expr_regs...)`.

### `py_expr.lower_await(ctx, node) -> str`

Lowers `await expr` as `CALL_FUNCTION("await", expr_regs...)`.

### `py_expr.lower_named_expression(ctx, node) -> str`

Lowers `y := expr`: evaluates the value, emits `STORE_VAR(name, val_reg)`, returns the value register (so the expression result is available to the enclosing context).

### `py_cf.lower_assert(ctx, node)`

Lowers `assert cond, msg` as `CALL_FUNCTION("assert", cond_reg [, msg_reg])`.

### `py_cf.lower_delete(ctx, node)`

Lowers `del x, y` by iterating targets (unwrapping `expression_list` if present) and emitting `CALL_FUNCTION("del", target_reg)` for each.

### `py_cf.lower_import(ctx, node)`

Lowers `import os.path`:
1. `CALL_FUNCTION("import", "os.path")`
2. `STORE_VAR("os", import_reg)` -- stores under the top-level module name (splits on `.`)

### `py_cf.lower_import_from(ctx, node)`

Lowers `from X import Y, Z`:
- For each imported `dotted_name` child: `CALL_FUNCTION("import", "from X import Y")` + `STORE_VAR("Y", reg)`

### `py_cf.lower_match(ctx, node)`

Lowers `match subject:` as an if/elif chain:
1. Evaluates subject expression
2. For each `case_clause`:
   - If the pattern is `_` (wildcard): unconditionally lower the body
   - Otherwise: `BINOP("==", subject, pattern)` + `BRANCH_IF` to case body or next case
3. End label after all cases

### `py_expr.lower_slice(ctx, node) -> str`

Lowers `a[1:3:2]` as `CALL_FUNCTION("slice", start, stop, step)`. Missing components get `CONST("None")` placeholders. Parses colon positions in the child list to determine which parts are present.

### `py_expr.lower_noop_expr(ctx, node) -> str`

Returns `CONST("None")` for syntactic-only nodes like `keyword_separator` (`*`) and `positional_separator` (`/`).

### `py_expr.lower_list_pattern(ctx, node) -> str`

Lowers `[p1, p2, ...]` patterns in match/case as `NEW_ARRAY("list")` + `STORE_INDEX` per element (same structure as a list literal).

### `py_expr.lower_dict_pattern(ctx, node) -> str`

Lowers `{"key": pattern, ...}` in match/case as `NEW_OBJECT("dict_pattern")` with key/value pairs via `STORE_INDEX`.

### `py_expr.lower_case_pattern(ctx, node) -> str`

Wrapper node unwrapper: extracts the first named child and lowers it as an expression.

### `py_expr.lower_python_string(ctx, node) -> str`

Lowers string nodes, decomposing f-strings into parts + concatenation. Plain strings delegate to `lower_const_literal`. F-strings with `interpolation` children are decomposed into `CONST` fragments and interpolation results concatenated via `BINOP("+")`.

### `py_expr.lower_interpolation(ctx, node) -> str`

Lowers `{expr}` inside f-strings by extracting the inner expression (excluding `format_specifier` and `type_conversion` children) and lowering it.

### `py_expr.lower_splat_expr(ctx, node) -> str`

Lowers `*expr` (list_splat), `**expr` (dictionary_splat), or splat_pattern as `CALL_FUNCTION("spread", inner)`.

### `py_cf.lower_python_if(ctx, node)`

Lowers Python if/elif/else chains by iterating all sibling clauses. Python's tree-sitter grammar places `elif_clause` and `else_clause` as flat siblings under `if_statement`. This lowerer collects them all and chains them via `_lower_python_elif_chain`.

### `py_decl.lower_python_class_def(ctx, node)`

Lowers Python `class_definition`, extracting parent class names from `argument_list` children for inheritance support. Delegates to `common_decl.lower_class_def` with the extracted parents.

### `py_assign.lower_assignment(ctx, node)`

Lowers assignment using Python's `lower_store_target` which supports tuple/pattern_list unpacking.

### `py_assign.lower_augmented_assignment(ctx, node)`

Lowers augmented assignment (`+=`, `-=`, etc.) as `BINOP` + store via Python's `lower_store_target`.

## Canonical Literal Handling

| Python AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `none` | `common_expr.lower_canonical_none` | `CONST "None"` |

Since Python is the reference language for the IR, no translation is needed. The base class defaults (`none_literal = "None"`, `true_literal = "True"`, `false_literal = "False"`) are already Python-canonical.

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

2. **Comprehension recursion**: List/dict/set comprehensions and generator expressions all share a common recursive `_lower_comprehension_loop` helper in `py_expr`, supporting arbitrary nesting of `for_in_clause` nodes.

3. **Generator expressions**: Modeled as eagerly-evaluated arrays wrapped in `CALL_FUNCTION("generator", ...)`, not as true lazy generators. This is a deliberate simplification for static analysis purposes.

4. **Decorator application order**: Decorators are applied bottom-up (innermost first), matching Python's actual execution semantics.

5. **With statement**: Models context managers via explicit `__enter__`/`__exit__` calls, handling multiple context managers in a single `with` statement with LIFO exit ordering.

6. **Match/case simplification**: Match statements are lowered as equality-comparison chains (`==`), not as full pattern matching. Wildcard `_` patterns are detected by text comparison. Structural pattern matching (e.g., class patterns, sequence patterns) is partially supported via `lower_list_pattern`, `lower_dict_pattern`, and `lower_case_pattern` handlers.

7. **Import modeling**: Imports are modeled as `CALL_FUNCTION("import", ...)` calls, making them visible as side effects in the IR. `import os.path` stores under the top-level name `os`.

8. **Tuple unpacking**: Handled recursively via `py_expr.lower_store_target` override, supporting nested patterns like `(a, (b, c)) = expr`.

9. **No-op statements**: `pass`, `global`, `nonlocal`, and `type_alias_statement` are all treated as no-ops.

10. **F-string interpolation**: The `lower_python_string` handler decomposes f-strings into `CONST` fragments and interpolation results concatenated via `BINOP("+")`. The `lower_interpolation` handler extracts the inner expression, while `string_content`, `string_start`, `string_end`, `format_specifier`, and `type_conversion` are all lowered as `CONST` literals.

11. **Pure function architecture**: All lowering methods are pure functions taking `(ctx: TreeSitterEmitContext, node)` as arguments. The `PythonFrontend` class in `frontend.py` is a thin orchestrator that builds dispatch tables from these functions via `_build_expr_dispatch()` and `_build_stmt_dispatch()`.
