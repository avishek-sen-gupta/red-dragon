# Rust Frontend

> `interpreter/frontends/rust.py` · Extends `BaseFrontend` · ~945 lines

## Overview

The Rust frontend lowers tree-sitter Rust ASTs into the RedDragon TAC IR. Rust's expression-oriented semantics require special handling: `if`, `match`, and blocks are all value-producing expressions. The frontend handles Rust-specific constructs including `let` bindings with pattern destructuring, `match` expressions, closures (`|x| expr`), `struct` definitions and instantiation (with shorthand field syntax), `impl` blocks, traits, enums (with variant variants), `loop`/`for..in` loops, `async`/`await`, the `?` try operator, reference/dereference (`&`/`*`), type casts (`as`), scoped identifiers (`Path::Segment`), macro invocations, and module items.

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── RustFrontend (rust.py)
```

`RustFrontend` inherits common lowering from `BaseFrontend` including `_lower_while`, `_lower_break`, `_lower_continue`, `_lower_expression_statement`, `_lower_function_def`, `_lower_paren`, `_lower_binop`, `_lower_unop`, `_lower_const_literal`, `_lower_identifier`, `_lower_call`, `_lower_list_literal`, and canonical literal helpers.

## Overridden Constants

| Constant | BaseFrontend Default | RustFrontend Value |
|---|---|---|
| `DEFAULT_RETURN_VALUE` | `"None"` | `"()"` |
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"field_expression"` |
| `ATTR_OBJECT_FIELD` | `"object"` | `"value"` |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"field"` |
| `CALL_FUNCTION_FIELD` | `"function"` | `"function"` (same) |
| `CALL_ARGUMENTS_FIELD` | `"arguments"` | `"arguments"` (same) |
| `ASSIGN_LEFT_FIELD` | `"left"` | `"left"` (same) |
| `ASSIGN_RIGHT_FIELD` | `"right"` | `"right"` (same) |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment", "line_comment", "block_comment"})` |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"\n"})` |
| `BLOCK_NODE_TYPES` | `frozenset()` | `frozenset({"block"})` |

Note: `NONE_LITERAL`, `TRUE_LITERAL`, `FALSE_LITERAL` retain their BaseFrontend defaults (`"None"`, `"True"`, `"False"`). `DEFAULT_RETURN_VALUE` is overridden to `"()"` (Rust's unit type).

## Expression Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `float_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `char_literal` | `_lower_const_literal` | `CONST` (raw text) |
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |
| `binary_expression` | `_lower_binop` | `BINOP` |
| `unary_expression` | `_lower_unop` | `UNOP` |
| `parenthesized_expression` | `_lower_paren` | (unwraps inner expr) |
| `call_expression` | `_lower_call` | `CALL_FUNCTION`/`CALL_METHOD`/`CALL_UNKNOWN` |
| `field_expression` | `_lower_field_expr` | `LOAD_FIELD` |
| `reference_expression` | `_lower_reference_expr` | `UNOP "&"` |
| `dereference_expression` | `_lower_deref_expr` | `UNOP "*"` |
| `assignment_expression` | `_lower_assignment_expr` | `STORE_VAR`/`STORE_FIELD`/`STORE_INDEX` |
| `compound_assignment_expr` | `_lower_compound_assignment_expr` | `BINOP` + `STORE_*` |
| `if_expression` | `_lower_if_expr` | `BRANCH_IF` + temp var + `LOAD_VAR` |
| `match_expression` | `_lower_match_expr` | `BINOP ==` + `BRANCH_IF` chain |
| `closure_expression` | `_lower_closure_expr` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `struct_expression` | `_lower_struct_instantiation` | `NEW_OBJECT` + `STORE_FIELD` per field |
| `block` | `_lower_block_expr` | (last expr is value) |
| `return_expression` | `_lower_return_expr` | `RETURN` |
| `macro_invocation` | `_lower_macro_invocation` | `CALL_FUNCTION("macro_name!", ...)` |
| `type_identifier` | `_lower_identifier` | `LOAD_VAR` |
| `self` | `_lower_identifier` | `LOAD_VAR "self"` |
| `array_expression` | `_lower_list_literal` | `NEW_ARRAY("list", size)` + `STORE_INDEX` |
| `index_expression` | `_lower_index_expr` | `LOAD_INDEX` |
| `tuple_expression` | `_lower_tuple_expr` | `NEW_ARRAY("tuple", size)` + `STORE_INDEX` |
| `else_clause` | `_lower_else_clause` | (unwraps inner block/expr) |
| `expression_statement` | `_lower_expr_stmt_as_expr` | (unwraps inner expr) |
| `range_expression` | `_lower_symbolic_node` | `SYMBOLIC` |
| `try_expression` | `_lower_try_expr` | `CALL_FUNCTION("try_unwrap", inner)` |
| `await_expression` | `_lower_await_expr` | `CALL_FUNCTION("await", inner)` |
| `async_block` | `_lower_block_expr` | (block expression) |
| `unsafe_block` | `_lower_block_expr` | (block expression) |
| `type_cast_expression` | `_lower_type_cast_expr` | `CALL_FUNCTION("as", expr, type_name)` |
| `scoped_identifier` | `_lower_scoped_identifier` | `LOAD_VAR "Path::Segment"` |

## Statement Dispatch Table

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `_lower_expression_statement` | (unwraps inner expr) |
| `let_declaration` | `_lower_let_decl` | `STORE_VAR` |
| `function_item` | `_lower_function_def` | (inherited) `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `struct_item` | `_lower_struct_def` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `impl_item` | `_lower_impl_item` | `BRANCH`/`LABEL`/body/`STORE_VAR` (class ref) |
| `if_expression` | `_lower_if_stmt` | (delegates to `_lower_if_expr`, discards result) |
| `while_expression` | `_lower_while` | (inherited) `BRANCH_IF` loop |
| `loop_expression` | `_lower_loop` | Infinite loop (`BRANCH` back to top) |
| `for_expression` | `_lower_for` | Index-based loop with `LOAD_INDEX` |
| `return_expression` | `_lower_return_stmt` | `RETURN` |
| `block` | `_lower_block` | (inherited block lowering) |
| `source_file` | `_lower_block` | (inherited block lowering) |
| `use_declaration` | `lambda _: None` | No-op |
| `attribute_item` | `lambda _: None` | No-op |
| `macro_invocation` | `_lower_macro_stmt` | `CALL_FUNCTION("macro_name!")` |
| `break_expression` | `_lower_break` | `BRANCH` to break target |
| `continue_expression` | `_lower_continue` | `BRANCH` to continue label |
| `trait_item` | `_lower_trait_item` | `BRANCH`/`LABEL`/body/`STORE_VAR` (class ref) |
| `enum_item` | `_lower_enum_item` | `NEW_OBJECT` + `STORE_FIELD` per variant |
| `const_item` | `_lower_const_item` | `STORE_VAR` |
| `static_item` | `_lower_static_item` | `STORE_VAR` |
| `type_item` | `_lower_type_item` | `CONST type_text` + `STORE_VAR` |
| `mod_item` | `_lower_mod_item` | (lowers body block) |
| `extern_crate_declaration` | `lambda _: None` | No-op |

## Language-Specific Lowering Methods

### `_lower_let_decl(node)`
Handles `let_declaration`. Extracts `pattern` and `value` fields. Uses `_extract_let_pattern_name` to handle `mut` wrappers. If no value, stores `CONST "None"`. Emits `STORE_VAR`.

### `_extract_let_pattern_name(pattern_node) -> str`
Extracts identifier from let patterns. Handles:
- Direct `identifier` -> returns text
- `mutable_specifier` -> finds `identifier` child
- Other patterns -> finds first `identifier` child, falls back to raw text
Returns `"__unknown"` if no pattern node.

### `_lower_assignment_expr(node) -> str`
Handles `assignment_expression`. Lowers RHS, delegates to `_lower_store_target`. Returns value register.

### `_lower_compound_assignment_expr(node) -> str`
Handles `compound_assignment_expr` (`x += 1`). Extracts `operator` field, strips trailing `=`. Emits `BINOP` then `_lower_store_target`. Returns result register.

### `_lower_field_expr(node) -> str`
Handles `field_expression` (`obj.field`). Extracts `value` (object) and `field` fields. Emits `LOAD_FIELD`.

### `_lower_reference_expr(node) -> str`
Handles `&expr` and `&mut expr`. Filters out `&` and `mut` tokens, lowers inner expression, emits `UNOP "&"`.

### `_lower_deref_expr(node) -> str`
Handles `*expr`. Filters out `*` token, lowers inner expression, emits `UNOP "*"`.

### `_lower_if_expr(node) -> str`
Handles `if_expression` as a value-producing expression. Extracts `condition`, `consequence`, `alternative` fields. Creates temporary variable `__if_result_{counter}`:
- True branch: lowers consequence as block expression, stores result
- False branch: lowers alternative expression, stores result
- Merge point: loads result variable
Returns the result register. This is the key distinction from C-family if statements.

### `_lower_if_stmt(node)`
Statement wrapper: calls `_lower_if_expr(node)` and discards the result register.

### `_lower_expr_stmt_as_expr(node) -> str`
Unwraps `expression_statement` to its inner named child for expression context. Returns `CONST "None"` if no named children.

### `_lower_else_clause(node) -> str`
Extracts the inner block or expression from an `else_clause`. Returns lowered result or `CONST "None"`.

### `_lower_loop(node)`
Handles `loop { ... }` (infinite loop). Emits loop label, lowers body with `_push_loop`/`_pop_loop`, then unconditional `BRANCH` back to top. End label is only reached via `break`.

### `_lower_for(node)`
Handles `for pattern in value { body }`. Extracts `pattern`, `value`, `body` fields. Desugars to index-based loop:
1. Initializes index to `0`, calls `len(iter_reg)`
2. Condition: `BINOP <`
3. Body: `LOAD_INDEX` + `STORE_VAR` for loop variable
4. Update: increment index, `BRANCH` back

### `_lower_return_expr(node) -> str`
Handles `return_expression` in expression context. Filters out `return` keyword, lowers value (or `CONST "()"` for bare return). Emits `RETURN`. Returns the value register (even though control flow diverges).

### `_lower_return_stmt(node)`
Statement wrapper: delegates to `_lower_return_expr`.

### `_lower_match_expr(node) -> str`
Handles `match_expression`. Extracts `value` and `body` fields. Iterates `match_arm` children:
- Each arm has a `match_pattern` and body expression(s)
- Pattern is compared with `BINOP ==`
- Arm body result stored in `__match_result_{counter}`
- `BRANCH` to end label
Returns loaded result variable. Arms without patterns get unconditional `BRANCH`.

### `_lower_block_expr(node) -> str`
Handles block `{ ... }` as a value-producing expression. Filters out `{`, `}`, `;`, comments, and noise. Lowers all children except the last as statements. The last child is lowered as an expression whose register is returned. Returns `CONST "None"` for empty blocks. Also handles `async_block` and `unsafe_block`.

### `_lower_closure_expr(node) -> str`
Handles `|params| expr` closures. Extracts `parameters` and `body` fields. Creates function body `__closure_{counter}`:
- Parameters lowered via `_lower_closure_params`
- Body lowered as expression with implicit `RETURN`
Returns function reference constant.

### `_lower_closure_params(params_node)`
Iterates closure parameter children. Handles `|` and `,` delimiters, bare `identifier` names (emit `SYMBOLIC`/`STORE_VAR`), and `parameter` nodes (delegate to `_lower_param`).

### `_lower_struct_def(node)`
Handles `struct_item`. Extracts `name` field. Emits empty class-like structure: `BRANCH`, `LABEL`, end `LABEL`, then class reference `CONST`/`STORE_VAR`. Field definitions are not individually modeled.

### `_lower_impl_item(node)`
Handles `impl_item`. Extracts `type` and `body` fields. Creates class-like block: `BRANCH`, `LABEL`, lowers body (which contains `function_item` methods), end `LABEL`, class reference `CONST`/`STORE_VAR`.

### `_lower_struct_instantiation(node) -> str`
Handles `struct_expression` (`Point { x: 1, y: 2 }`). Extracts `name` and `body` fields. Emits `NEW_OBJECT(struct_name)`. Iterates `field_initializer` children:
- With `field` and `value`: lowers value, emits `STORE_FIELD`
- With `field` only (shorthand `Point { x, y }`): loads identifier, emits `STORE_FIELD` (field name = value name)

### `_lower_macro_invocation(node) -> str` / `_lower_macro_stmt(node)`
Handles `macro_invocation`. Extracts macro name by splitting on `!` and appending `!`. Emits `CALL_FUNCTION("macro_name!")`. Statement version discards the register.

### `_lower_index_expr(node) -> str`
Handles `index_expression` (`arr[idx]`). Takes first two named children as object and index. Emits `LOAD_INDEX`.

### `_lower_tuple_expr(node) -> str`
Handles `(a, b, c)` tuples. Filters out `(`, `)`, `,`. Creates `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element.

### `_lower_try_expr(node) -> str`
Handles `expr?` (try/`?` operator). Extracts the non-`?` named child, emits `CALL_FUNCTION("try_unwrap", inner_reg)`.

### `_lower_await_expr(node) -> str`
Handles `expr.await`. Extracts the non-`.`/non-`await` named child, emits `CALL_FUNCTION("await", inner_reg)`.

### `_lower_trait_item(node)`
Handles `trait_item`. Extracts `name` and `body` fields. Creates class-like block with body lowering. Emits class reference using `CLASS_REF_TEMPLATE`.

### `_lower_enum_item(node)`
Handles `enum_item`. Extracts `name` and `body` fields. Creates `NEW_OBJECT("enum:{name}")`. Iterates body children (skipping `{`, `}`, `,`), extracting variant names (splitting on `(` and `{` for tuple/struct variants). Emits `CONST variant_name` + `STORE_FIELD` per variant.

### `_lower_const_item(node)` / `_lower_static_item(node)`
Both handle `const`/`static` items. Extract `name` and `value` fields. Lower value (or `CONST "None"` if absent). Emit `STORE_VAR`.

### `_lower_type_item(node)`
Handles `type Alias = OriginalType;`. Extracts `name` and `type` fields. Emits `CONST type_text` + `STORE_VAR`. Type text defaults to `"()"`.

### `_lower_mod_item(node)`
Handles `mod name { ... }`. Extracts `name` and `body` fields. If body present, lowers it as a block.

### `_lower_type_cast_expr(node) -> str`
Handles `expr as Type`. Lowers the expression, extracts type name. Emits `CALL_FUNCTION("as", expr_reg, type_name)`.

### `_lower_scoped_identifier(node) -> str`
Handles `Path::Segment` (e.g., `HashMap::new`, `Shape::Circle`). Joins `identifier` children with `::`. Emits `LOAD_VAR` with the qualified name.

### `_lower_symbolic_node(node) -> str`
Generic fallback for symbolic representation. Emits `SYMBOLIC("{node.type}:{text[:60]}")`.

### `_extract_param_name(child) -> str | None`
**Overrides** `BaseFrontend._extract_param_name`. Handles:
- `identifier` -> raw text
- `self_parameter` -> `"self"`
- `parameter` -> extracts from `pattern` field via `_extract_let_pattern_name`

### `_lower_store_target(target, val_reg, parent_node)`
**Overrides** `BaseFrontend._lower_store_target`. Handles Rust-specific target types:
- `identifier` -> `STORE_VAR`
- `field_expression` -> `STORE_FIELD` (extracts `value` and `field` fields)
- `index_expression` -> `STORE_INDEX` (first two named children)
- `dereference_expression` -> `STORE_VAR` with `*`-prefixed name (e.g., `*ptr`)
- Fallback -> `STORE_VAR` with raw text

## Canonical Literal Handling

| Rust Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `_lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |

Rust's tree-sitter grammar produces both `boolean_literal` (in some contexts) and separate `true`/`false` node types. All three are handled. There is no dedicated null literal in Rust; the unit type `()` serves as the default return value via `DEFAULT_RETURN_VALUE = "()"`.

## Example

**Rust source:**
```rust
struct Point {
    x: f64,
    y: f64,
}

impl Point {
    fn distance(&self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
}

fn main() {
    let p = Point { x: 3.0, y: 4.0 };
    let d = p.distance();
}
```

**Emitted IR (approximate):**
```
LABEL     __entry__
BRANCH    end_class:Point_1
LABEL     class:Point_0
LABEL     end_class:Point_1
CONST     %0  "class:Point@class:Point_0"
STORE_VAR Point  %0
BRANCH    end_class:Point_3
LABEL     class:Point_2
BRANCH    end_distance_5
LABEL     func:distance_4
SYMBOLIC  %1  "param:self"
STORE_VAR self  %1
LOAD_VAR  %2  "self"
LOAD_FIELD %3  %2  "x"
LOAD_VAR  %4  "self"
LOAD_FIELD %5  %4  "x"
BINOP     %6  "*"  %3  %5
LOAD_VAR  %7  "self"
LOAD_FIELD %8  %7  "y"
LOAD_VAR  %9  "self"
LOAD_FIELD %10  %9  "y"
BINOP     %11  "*"  %8  %10
BINOP     %12  "+"  %6  %11
CALL_METHOD %13  %12  "sqrt"
RETURN    %13
CONST     %14  "()"
RETURN    %14
LABEL     end_distance_5
CONST     %15  "func:distance@func:distance_4"
STORE_VAR distance  %15
LABEL     end_class:Point_3
CONST     %16  "class:Point@class:Point_2"
STORE_VAR Point  %16
BRANCH    end_main_7
LABEL     func:main_6
NEW_OBJECT %17  "Point"
CONST     %18  "3.0"
STORE_FIELD %17  "x"  %18
CONST     %19  "4.0"
STORE_FIELD %17  "y"  %19
STORE_VAR p  %17
LOAD_VAR  %20  "p"
CALL_METHOD %21  %20  "distance"
STORE_VAR d  %21
CONST     %22  "()"
RETURN    %22
LABEL     end_main_7
CONST     %23  "func:main@func:main_6"
STORE_VAR main  %23
```

## Design Notes

1. **Expression-oriented semantics**: Rust's `if`, `match`, and block expressions all produce values. `_lower_if_expr` and `_lower_match_expr` store results in temporary variables (`__if_result_*`, `__match_result_*`) and load them at merge points. `_lower_block_expr` treats the last expression in a block as its value.

2. **`DEFAULT_RETURN_VALUE = "()"` (unit type)**: Bare `return` or implicit function returns emit `CONST "()"` rather than `CONST "None"`. This preserves Rust's unit-type semantics.

3. **Dual `if` handlers**: `if_expression` appears in both expression and statement dispatch tables. The statement handler (`_lower_if_stmt`) simply delegates to `_lower_if_expr` and discards the result.

4. **`match` as if/else chain**: `match` arms are lowered as sequential `BINOP == / BRANCH_IF` comparisons. Pattern destructuring is not modeled; patterns are compared as values.

5. **Struct instantiation with shorthand**: `Point { x, y }` (no explicit value) is handled: the field name is used as both the field key and the identifier to load.

6. **`impl` lowered as class block**: `impl Point { ... }` creates a class-like labeled block containing the methods. This means `Point` may get multiple class references (one from `struct_item`, one from `impl_item`).

7. **Dereference assignment**: `*ptr = value` is lowered as `STORE_VAR("*ptr_text", val_reg)` -- a string-based approximation rather than true pointer semantics.

8. **Macro invocations**: Macros (e.g., `println!`, `vec!`) are lowered as `CALL_FUNCTION("macro_name!")` with no arguments extracted from the macro body. This is a deliberate simplification.

9. **`?` operator as function call**: `expr?` is lowered as `CALL_FUNCTION("try_unwrap", inner)`, abstracting Rust's error propagation.

10. **`await` as function call**: `expr.await` is lowered as `CALL_FUNCTION("await", inner)`, abstracting async semantics.

11. **Range expressions are symbolic**: `0..10`, `0..=10` etc. are lowered as `SYMBOLIC` with the range text, since the IR does not have a native range type.

12. **No-op declarations**: `use_declaration`, `attribute_item`, and `extern_crate_declaration` are all no-ops (lambda `_: None`).

13. **Closure parameters use `|` delimiters**: `_lower_closure_params` skips `|` and `,` tokens when iterating parameters, unlike regular function parameters that use `(` and `)`.

14. **Enum variants as object fields**: Each enum variant is stored as a `STORE_FIELD` on a `NEW_OBJECT("enum:{name}")`. Variant names are extracted by splitting on `(` and `{` to strip tuple/struct variant payloads.
