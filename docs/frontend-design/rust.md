# Rust Frontend

> `interpreter/frontends/rust/` -- Extends `BaseFrontend`

## Overview

The Rust frontend lowers tree-sitter Rust ASTs into the RedDragon TAC IR. Rust's expression-oriented semantics require special handling: `if`, `match`, and blocks are all value-producing expressions. The frontend handles Rust-specific constructs including `let` bindings with pattern destructuring (tuple and struct), `match` expressions, closures (`|x| expr`), `struct` definitions and instantiation (with shorthand field syntax), `impl` blocks, traits, enums (with variant variants), `loop`/`for..in` loops, `async`/`await`, the `?` try operator, reference/dereference (`&`/`*`), type casts (`as`), scoped identifiers (`Path::Segment`), macro invocations, module items, generic functions, `let` conditions, and struct patterns.

## Directory Structure

```
interpreter/frontends/rust/
  frontend.py          RustFrontend class (thin orchestrator)
  node_types.py         RustNodeType constants
  expressions.py        Expression lowerers (pure functions)
  control_flow.py       Control flow lowerers (pure functions)
  declarations.py       Declaration lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (abstract)
  +-- BaseFrontend (_base.py)
        +-- RustFrontend
```

`RustFrontend` is a thin orchestrator that builds dispatch tables from pure functions defined in the sibling modules. It inherits common lowering from `BaseFrontend` via the common module functions (`common_expr`, `common_cf`, `common_assign`).

## Grammar Constants (`_build_constants()`)

| Field | Value | Notes |
|---|---|---|
| `default_return_value` | `"()"` | Rust's unit type |
| `attribute_node_type` | `"field_expression"` | Rust uses `value.field` syntax |
| `attr_object_field` | `"value"` | tree-sitter Rust names the LHS `value` |
| `attr_attribute_field` | `"field"` | tree-sitter Rust names the RHS `field` |
| `comment_types` | `frozenset({"comment", "line_comment", "block_comment"})` | Multiple comment node types |
| `noise_types` | `frozenset({"\n"})` | Newlines only |
| `block_node_types` | `frozenset({"block", "source_file"})` | Block-like containers |
| `none_literal` | `"None"` | Same as base |
| `true_literal` | `"True"` | Same as base |
| `false_literal` | `"False"` | Same as base |

## Expression Dispatch Table (`_build_expr_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `integer_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `float_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `string_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `char_literal` | `common_expr.lower_const_literal` | `CONST` (raw text) |
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `binary_expression` | `common_expr.lower_binop` | `BINOP` |
| `unary_expression` | `common_expr.lower_unop` | `UNOP` |
| `parenthesized_expression` | `common_expr.lower_paren` | (unwraps inner expr) |
| `call_expression` | `common_expr.lower_call` | `CALL_FUNCTION`/`CALL_METHOD`/`CALL_UNKNOWN` |
| `field_expression` | `rust_expr.lower_field_expr` | `LOAD_FIELD` |
| `reference_expression` | `rust_expr.lower_reference_expr` | `UNOP "&"` |
| `dereference_expression` | `rust_expr.lower_deref_expr` | `UNOP "*"` |
| `assignment_expression` | `rust_expr.lower_assignment_expr` | `STORE_VAR`/`STORE_FIELD`/`STORE_INDEX` |
| `compound_assignment_expr` | `rust_expr.lower_compound_assignment_expr` | `BINOP` + `STORE_*` |
| `if_expression` | `rust_expr.lower_if_expr` | `BRANCH_IF` + temp var + `LOAD_VAR` |
| `match_expression` | `rust_expr.lower_match_expr` | `BINOP ==` + `BRANCH_IF` chain |
| `closure_expression` | `rust_expr.lower_closure_expr` | `BRANCH`/`LABEL`/`RETURN` (func ref) |
| `struct_expression` | `rust_expr.lower_struct_instantiation` | `NEW_OBJECT` + `STORE_FIELD` per field |
| `block` | `rust_expr.lower_block_expr` | (last expr is value) |
| `return_expression` | `rust_expr.lower_return_expr` | `RETURN` |
| `macro_invocation` | `rust_expr.lower_macro_invocation` | `CALL_FUNCTION("macro_name!", ...)` |
| `type_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `self` | `common_expr.lower_identifier` | `LOAD_VAR "self"` |
| `array_expression` | `common_expr.lower_list_literal` | `NEW_ARRAY("list", size)` + `STORE_INDEX` |
| `index_expression` | `rust_expr.lower_index_expr` | `LOAD_INDEX` |
| `tuple_expression` | `rust_expr.lower_tuple_expr` | `NEW_ARRAY("tuple", size)` + `STORE_INDEX` |
| `else_clause` | `rust_expr.lower_else_clause` | (unwraps inner block/expr) |
| `expression_statement` | `rust_expr.lower_expr_stmt_as_expr` | (unwraps inner expr) |
| `range_expression` | `rust_expr.lower_range_expr` | `CALL_FUNCTION("range", start, end)` |
| `try_expression` | `rust_expr.lower_try_expr` | `CALL_FUNCTION("try_unwrap", inner)` |
| `await_expression` | `rust_expr.lower_await_expr` | `CALL_FUNCTION("await", inner)` |
| `async_block` | `rust_expr.lower_block_expr` | (block expression) |
| `unsafe_block` | `rust_expr.lower_block_expr` | (block expression) |
| `type_cast_expression` | `rust_expr.lower_type_cast_expr` | `CALL_FUNCTION("as", expr, type_name)` |
| `scoped_identifier` | `rust_expr.lower_scoped_identifier` | `LOAD_VAR "Path::Segment"` |
| `while_expression` | `rust_expr.lower_loop_as_expr` | (lowers as stmt, returns unit) |
| `loop_expression` | `rust_expr.lower_loop_as_expr` | (lowers as stmt, returns unit) |
| `for_expression` | `rust_expr.lower_loop_as_expr` | (lowers as stmt, returns unit) |
| `continue_expression` | `rust_expr.lower_continue_as_expr` | (lowers continue, returns unit) |
| `break_expression` | `rust_expr.lower_break_as_expr` | (lowers break, returns unit) |
| `match_pattern` | `common_expr.lower_paren` | (unwraps inner pattern) |
| `tuple_struct_pattern` | `rust_expr.lower_tuple_struct_pattern` | `CONST` + `STORE_INDEX` per inner binding |
| `generic_function` | `rust_expr.lower_generic_function` | (strips type params, lowers inner) |
| `let_condition` | `rust_expr.lower_let_condition` | `BINOP ==` (pattern match condition) |
| `struct_pattern` | `rust_expr.lower_struct_pattern_expr` | `NEW_OBJECT` + `STORE_INDEX` per field |

**46 entries total.**

## Statement Dispatch Table (`_build_stmt_dispatch()`)

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `common_assign.lower_expression_statement` | (unwraps inner expr) |
| `let_declaration` | `rust_decl.lower_let_decl` | `STORE_VAR` |
| `function_item` | `rust_decl.lower_function_def` | `BRANCH`/`LABEL`/`RETURN`/`STORE_VAR` |
| `struct_item` | `rust_decl.lower_struct_def` | `BRANCH`/`LABEL`/`STORE_VAR` (class ref) |
| `impl_item` | `rust_decl.lower_impl_item` | `BRANCH`/`LABEL`/body/`STORE_VAR` (class ref) |
| `if_expression` | `rust_cf.lower_if_stmt` | (delegates to `rust_expr.lower_if_expr`, discards result) |
| `while_expression` | `common_cf.lower_while` | (inherited) `BRANCH_IF` loop |
| `loop_expression` | `rust_cf.lower_loop` | Infinite loop (`BRANCH` back to top) |
| `for_expression` | `rust_cf.lower_for` | Index-based loop with `LOAD_INDEX` |
| `return_expression` | `rust_cf.lower_return_stmt` | `RETURN` |
| `block` | `lambda ctx, node: ctx.lower_block(node)` | (inherited block lowering) |
| `source_file` | `lambda ctx, node: ctx.lower_block(node)` | (inherited block lowering) |
| `use_declaration` | `lambda ctx, node: None` | No-op |
| `attribute_item` | `lambda ctx, node: None` | No-op |
| `macro_invocation` | `rust_cf.lower_macro_stmt` | `CALL_FUNCTION("macro_name!")` |
| `break_expression` | `common_cf.lower_break` | `BRANCH` to break target |
| `continue_expression` | `common_cf.lower_continue` | `BRANCH` to continue label |
| `trait_item` | `rust_decl.lower_trait_item` | `BRANCH`/`LABEL`/body/`STORE_VAR` (class ref) |
| `enum_item` | `rust_decl.lower_enum_item` | `NEW_OBJECT` + `STORE_FIELD` per variant |
| `const_item` | `rust_decl.lower_const_item` | `STORE_VAR` |
| `static_item` | `rust_decl.lower_static_item` | `STORE_VAR` |
| `type_item` | `rust_decl.lower_type_item` | `CONST type_text` + `STORE_VAR` |
| `mod_item` | `rust_decl.lower_mod_item` | (lowers body block) |
| `extern_crate_declaration` | `lambda ctx, node: None` | No-op |
| `function_signature_item` | `rust_decl.lower_function_signature` | `BRANCH`/`LABEL`/params/`RETURN`/`STORE_VAR` (stub) |

**25 entries total.**

## Language-Specific Lowering Methods

### `rust_decl.lower_let_decl(ctx, node)`
Handles `let_declaration`. Extracts `pattern` and `value` fields. Uses `_extract_let_pattern_name` to handle `mut` wrappers. If no value, stores `CONST "None"`. Supports tuple destructuring (`let (a, b) = expr`) via `_lower_tuple_destructure` and struct destructuring (`let Point { x, y } = expr`) via `_lower_struct_destructure`. Emits `STORE_VAR`.

### `rust_expr.lower_assignment_expr(ctx, node) -> str`
Handles `assignment_expression`. Lowers RHS, delegates to `rust_expr.lower_rust_store_target`. Returns value register.

### `rust_expr.lower_compound_assignment_expr(ctx, node) -> str`
Handles `compound_assignment_expr` (`x += 1`). Extracts `operator` field, strips trailing `=`. Emits `BINOP` then `rust_expr.lower_rust_store_target`. Returns result register.

### `rust_expr.lower_field_expr(ctx, node) -> str`
Handles `field_expression` (`obj.field`). Extracts `value` (object) and `field` fields. Emits `LOAD_FIELD`.

### `rust_expr.lower_reference_expr(ctx, node) -> str`
Handles `&expr` and `&mut expr`. Filters out `&` and `mut` tokens, lowers inner expression, emits `UNOP "&"`.

### `rust_expr.lower_deref_expr(ctx, node) -> str`
Handles `*expr`. Filters out `*` token, lowers inner expression, emits `UNOP "*"`.

### `rust_expr.lower_if_expr(ctx, node) -> str`
Handles `if_expression` as a value-producing expression. Extracts `condition`, `consequence`, `alternative` fields. Creates temporary variable `__if_result_{counter}`:
- True branch: lowers consequence as block expression, stores result
- False branch: lowers alternative expression, stores result
- Merge point: loads result variable
Returns the result register. This is the key distinction from C-family if statements.

### `rust_cf.lower_if_stmt(ctx, node)`
Statement wrapper: calls `rust_expr.lower_if_expr(ctx, node)` and discards the result register.

### `rust_expr.lower_expr_stmt_as_expr(ctx, node) -> str`
Unwraps `expression_statement` to its inner named child for expression context. Returns `CONST "None"` if no named children.

### `rust_expr.lower_else_clause(ctx, node) -> str`
Extracts the inner block or expression from an `else_clause`. Returns lowered result or `CONST "None"`.

### `rust_cf.lower_loop(ctx, node)`
Handles `loop { ... }` (infinite loop). Emits loop label, lowers body with `ctx.push_loop`/`ctx.pop_loop`, then unconditional `BRANCH` back to top. End label is only reached via `break`.

### `rust_cf.lower_for(ctx, node)`
Handles `for pattern in value { body }`. Extracts `pattern`, `value`, `body` fields. Desugars to index-based loop:
1. Initializes index to `0`, calls `len(iter_reg)`
2. Condition: `BINOP <`
3. Body: `LOAD_INDEX` + `STORE_VAR` for loop variable
4. Update: increment index, `BRANCH` back

### `rust_expr.lower_return_expr(ctx, node) -> str`
Handles `return_expression` in expression context. Filters out `return` keyword, lowers value (or `CONST "()"` for bare return). Emits `RETURN`. Returns the value register (even though control flow diverges).

### `rust_cf.lower_return_stmt(ctx, node)`
Statement wrapper: delegates to `rust_expr.lower_return_expr`.

### `rust_expr.lower_match_expr(ctx, node) -> str`
Handles `match_expression`. Extracts `value` and `body` fields. Iterates `match_arm` children:
- Each arm has a `match_pattern` and body expression(s)
- Pattern is compared with `BINOP ==`
- Arm body result stored in `__match_result_{counter}`
- `BRANCH` to end label
Returns loaded result variable. Arms without patterns get unconditional `BRANCH`.

### `rust_expr.lower_block_expr(ctx, node) -> str`
Handles block `{ ... }` as a value-producing expression. Filters out `{`, `}`, `;`, comments, and noise. Lowers all children except the last as statements. The last child is lowered as an expression whose register is returned. Returns `CONST "None"` for empty blocks. Also handles `async_block` and `unsafe_block`.

### `rust_expr.lower_closure_expr(ctx, node) -> str`
Handles `|params| expr` closures. Extracts `parameters` and `body` fields. Creates function body `__closure_{counter}`:
- Parameters lowered via `_lower_closure_params`
- Body lowered as expression with implicit `RETURN`
Returns function reference constant.

### `rust_decl.lower_struct_def(ctx, node)`
Handles `struct_item`. Extracts `name` field. Emits empty class-like structure: `BRANCH`, `LABEL`, end `LABEL`, then class reference `CONST`/`STORE_VAR`. Field definitions are not individually modeled.

### `rust_decl.lower_impl_item(ctx, node)`
Handles `impl_item`. Extracts `type` and `body` fields. Creates class-like block: `BRANCH`, `LABEL`, lowers body (which contains `function_item` methods), end `LABEL`, class reference `CONST`/`STORE_VAR`.

### `rust_expr.lower_struct_instantiation(ctx, node) -> str`
Handles `struct_expression` (`Point { x: 1, y: 2 }`). Extracts `name` and `body` fields. Emits `NEW_OBJECT(struct_name)`. Iterates `field_initializer` children:
- With `field` and `value`: lowers value, emits `STORE_FIELD`
- With `field` only (shorthand `Point { x, y }`): loads identifier, emits `STORE_FIELD` (field name = value name)

### `rust_expr.lower_macro_invocation(ctx, node) -> str` / `rust_cf.lower_macro_stmt(ctx, node)`
Handles `macro_invocation`. Extracts macro name by splitting on `!` and appending `!`. Emits `CALL_FUNCTION("macro_name!")`. Statement version discards the register.

### `rust_expr.lower_index_expr(ctx, node) -> str`
Handles `index_expression` (`arr[idx]`). Takes first two named children as object and index. Emits `LOAD_INDEX`.

### `rust_expr.lower_tuple_expr(ctx, node) -> str`
Handles `(a, b, c)` tuples. Filters out `(`, `)`, `,`. Creates `NEW_ARRAY("tuple", size)` + `STORE_INDEX` per element.

### `rust_expr.lower_try_expr(ctx, node) -> str`
Handles `expr?` (try/`?` operator). Extracts the non-`?` named child, emits `CALL_FUNCTION("try_unwrap", inner_reg)`.

### `rust_expr.lower_await_expr(ctx, node) -> str`
Handles `expr.await`. Extracts the non-`.`/non-`await` named child, emits `CALL_FUNCTION("await", inner_reg)`.

### `rust_decl.lower_trait_item(ctx, node)`
Handles `trait_item`. Extracts `name` and `body` fields. Creates class-like block with body lowering. Emits class reference using `CLASS_REF_TEMPLATE`.

### `rust_decl.lower_enum_item(ctx, node)`
Handles `enum_item`. Extracts `name` and `body` fields. Creates `NEW_OBJECT("enum:{name}")`. Iterates body children (skipping `{`, `}`, `,`), extracting variant names (splitting on `(` and `{` for tuple/struct variants). Emits `CONST variant_name` + `STORE_FIELD` per variant.

### `rust_decl.lower_const_item(ctx, node)` / `rust_decl.lower_static_item(ctx, node)`
Both handle `const`/`static` items. Extract `name` and `value` fields. Lower value (or `CONST "None"` if absent). Emit `STORE_VAR`.

### `rust_decl.lower_type_item(ctx, node)`
Handles `type Alias = OriginalType;`. Extracts `name` and `type` fields. Emits `CONST type_text` + `STORE_VAR`. Type text defaults to `"()"`.

### `rust_decl.lower_mod_item(ctx, node)`
Handles `mod name { ... }`. Extracts `name` and `body` fields. If body present, lowers it as a block.

### `rust_expr.lower_type_cast_expr(ctx, node) -> str`
Handles `expr as Type`. Lowers the expression, extracts type name. Emits `CALL_FUNCTION("as", expr_reg, type_name)`.

### `rust_expr.lower_scoped_identifier(ctx, node) -> str`
Handles `Path::Segment` (e.g., `HashMap::new`, `Shape::Circle`). Joins `identifier` children with `::`. Emits `LOAD_VAR` with the qualified name.

### `rust_expr.lower_range_expr(ctx, node) -> str`
Handles `0..10`, `0..=10` etc. Lowers start and end as expressions, emits `CALL_FUNCTION("range", start, end)`.

### `rust_expr.lower_loop_as_expr(ctx, node) -> str`
Handles `while`/`loop`/`for` in expression position. Lowers as statement, returns `CONST "None"` (unit).

### `rust_expr.lower_continue_as_expr(ctx, node) -> str` / `rust_expr.lower_break_as_expr(ctx, node) -> str`
Handle `continue`/`break` in expression position. Delegate to common control flow, return `CONST "None"`.

### `rust_expr.lower_tuple_struct_pattern(ctx, node) -> str`
Handles `Some(x)` or `Message::Write(text)`. Extracts variant name, creates `CONST` + `STORE_INDEX` per inner binding.

### `rust_expr.lower_generic_function(ctx, node) -> str`
Handles `a.parse::<i32>()`. Strips type parameters, lowers inner identifier.

### `rust_expr.lower_let_condition(ctx, node) -> str`
Handles `let Some(val) = opt`. Lowers value and pattern, emits `BINOP ==` as condition.

### `rust_expr.lower_struct_pattern_expr(ctx, node) -> str`
Handles `Message::Move { x, y }` as pattern value. Creates `NEW_OBJECT("struct_pattern:Type")` + `STORE_INDEX` per field.

### `rust_expr.lower_rust_store_target(ctx, target, val_reg, parent_node)`
Rust-specific store target handling:
- `identifier` -> `STORE_VAR`
- `field_expression` -> `STORE_FIELD` (extracts `value` and `field` fields)
- `index_expression` -> `STORE_INDEX` (first two named children)
- `dereference_expression` -> `STORE_VAR` with `*`-prefixed name (e.g., `*ptr`)
- Fallback -> `STORE_VAR` with raw text

### `rust_decl.lower_function_def(ctx, node)`
Lowers `function_item` with Rust-specific param handling via `rust_decl.lower_rust_params`. Extracts return type from `return_type` field.

### `rust_decl.lower_function_signature(ctx, node)`
Lowers `fn area(&self) -> f64;` as a function stub with no body. Emits params, implicit return, and function reference.

### `rust_decl.lower_rust_params(ctx, params_node)` / `rust_decl.lower_rust_param(ctx, child)`
Lowers Rust function parameters. Handles `self_parameter` -> `"self"`, `parameter` -> extracts from `pattern` field via `_extract_let_pattern_name`. Emits `SYMBOLIC("param:name")` + `STORE_VAR`.

## Canonical Literal Handling

| Rust Node Type | Handler | Canonical IR Value |
|---|---|---|
| `boolean_literal` | `common_expr.lower_canonical_bool` | `CONST "True"` or `CONST "False"` |
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |

Rust's tree-sitter grammar produces both `boolean_literal` (in some contexts) and separate `true`/`false` node types. All three are handled. There is no dedicated null literal in Rust; the unit type `()` serves as the default return value via `default_return_value = "()"`.

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

1. **Expression-oriented semantics**: Rust's `if`, `match`, and block expressions all produce values. `rust_expr.lower_if_expr` and `rust_expr.lower_match_expr` store results in temporary variables (`__if_result_*`, `__match_result_*`) and load them at merge points. `rust_expr.lower_block_expr` treats the last expression in a block as its value.

2. **`default_return_value = "()"` (unit type)**: Bare `return` or implicit function returns emit `CONST "()"` rather than `CONST "None"`. This preserves Rust's unit-type semantics.

3. **Dual `if` handlers**: `if_expression` appears in both expression and statement dispatch tables. The statement handler (`rust_cf.lower_if_stmt`) simply delegates to `rust_expr.lower_if_expr` and discards the result.

4. **`match` as if/else chain**: `match` arms are lowered as sequential `BINOP == / BRANCH_IF` comparisons. Pattern destructuring is not modeled; patterns are compared as values.

5. **Struct instantiation with shorthand**: `Point { x, y }` (no explicit value) is handled: the field name is used as both the field key and the identifier to load.

6. **`impl` lowered as class block**: `impl Point { ... }` creates a class-like labeled block containing the methods. This means `Point` may get multiple class references (one from `struct_item`, one from `impl_item`).

7. **Dereference assignment**: `*ptr = value` is lowered as `STORE_VAR("*ptr_text", val_reg)` -- a string-based approximation rather than true pointer semantics.

8. **Macro invocations**: Macros (e.g., `println!`, `vec!`) are lowered as `CALL_FUNCTION("macro_name!")` with no arguments extracted from the macro body. This is a deliberate simplification.

9. **`?` operator as function call**: `expr?` is lowered as `CALL_FUNCTION("try_unwrap", inner)`, abstracting Rust's error propagation.

10. **`await` as function call**: `expr.await` is lowered as `CALL_FUNCTION("await", inner)`, abstracting async semantics.

11. **Range expressions as function calls**: `0..10`, `0..=10` etc. are lowered as `CALL_FUNCTION("range", start, end)`.

12. **No-op declarations**: `use_declaration`, `attribute_item`, and `extern_crate_declaration` are all no-ops.

13. **Closure parameters use `|` delimiters**: `_lower_closure_params` skips `|` and `,` tokens when iterating parameters, unlike regular function parameters that use `(` and `)`.

14. **Enum variants as object fields**: Each enum variant is stored as a `STORE_FIELD` on a `NEW_OBJECT("enum:{name}")`. Variant names are extracted by splitting on `(` and `{` to strip tuple/struct variant payloads.

15. **Loops in expression position**: `while`, `loop`, and `for` can appear as expressions in Rust. `rust_expr.lower_loop_as_expr` lowers them as statements and returns `CONST "None"` (unit). Similarly, `break` and `continue` in expression position delegate to the common handlers and return unit.

16. **`RustNodeType` constants**: All tree-sitter node type strings are centralised in `node_types.py` as `RustNodeType` class attributes, so typos are caught at import time and grep/refactor is trivial.
