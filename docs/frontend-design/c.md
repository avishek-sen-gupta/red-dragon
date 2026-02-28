# C Frontend

> `interpreter/frontends/c.py` · Extends `BaseFrontend` · 821 lines

## Overview

The C frontend lowers tree-sitter C ASTs into the RedDragon flattened three-address code IR. It handles the full range of C constructs including pointer arithmetic, struct/union/enum definitions, `sizeof`, ternary expressions, `goto`/labels, `switch` statements, compound literals, and C-style `for` loops. Preprocessor directives are treated as noise and skipped.

The frontend introduces several C-specific lowering patterns:
- Pointer dereference (`*p`) maps to `LOAD_FIELD ptr, "*"` and store-through-pointer (`*p = v`) maps to `STORE_FIELD ptr, "*", val`
- Address-of (`&x`) maps to `UNOP "&"`
- `sizeof` maps to `CALL_FUNCTION "sizeof"`
- `goto`/labels use a `user_` prefix to namespace user labels away from compiler-generated labels
- `switch` is lowered as an if/else chain with `BINOP "=="` comparisons

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend
        +-- CFrontend          <-- this file
              +-- CppFrontend  (extends CFrontend)
```

`CFrontend` extends `BaseFrontend` directly. It inherits all base infrastructure (dispatch tables, register/label allocation, `_emit`, `_lower_block`, `_lower_stmt`, `_lower_expr`, and the full library of reusable lowering methods). It overrides several constants and the `_lower_store_target` method, and adds ~20 C-specific lowering methods.

`CppFrontend` extends `CFrontend`, inheriting all C dispatch entries and methods, then adding C++-specific constructs on top.

## Overridden Constants

| Constant | BaseFrontend Default | CFrontend Value | Purpose |
|---|---|---|---|
| `DEFAULT_RETURN_VALUE` | `"None"` | `"0"` | Implicit return value for functions without explicit return |
| `ATTR_OBJECT_FIELD` | `"object"` | `"argument"` | Tree-sitter field name for the object in `obj.field` |
| `ATTR_ATTRIBUTE_FIELD` | `"attribute"` | `"field"` | Tree-sitter field name for the attribute in `obj.field` |
| `ATTRIBUTE_NODE_TYPE` | `"attribute"` | `"field_expression"` | Tree-sitter node type for member access expressions |
| `SUBSCRIPT_VALUE_FIELD` | `"value"` | `"argument"` | Tree-sitter field name for the array in `arr[idx]` |
| `SUBSCRIPT_INDEX_FIELD` | `"subscript"` | `"index"` | Tree-sitter field name for the index in `arr[idx]` |
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` | (Same as base) |
| `NOISE_TYPES` | `frozenset({"newline", "\n"})` | `frozenset({"\n"}) \| PREPROC_NOISE_TYPES` | Expanded to include all preprocessor directive node types |
| `BLOCK_NODE_TYPES` | `frozenset()` | `frozenset({"compound_statement"})` | Recognises `{ ... }` blocks as block nodes |

### `PREPROC_NOISE_TYPES`

A module-level constant (not a class attribute) defining preprocessor node types that are silently skipped:

```python
PREPROC_NOISE_TYPES = frozenset({
    "preproc_include",
    "preproc_define",
    "preproc_ifdef",
    "preproc_ifndef",
    "preproc_if",
    "preproc_else",
    "preproc_elif",
    "preproc_endif",
    "preproc_call",
    "preproc_def",
})
```

## Expression Dispatch Table

The full `_EXPR_DISPATCH` table populated in `__init__`:

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `identifier` | `_lower_identifier` (base) | `LOAD_VAR name` |
| `number_literal` | `_lower_const_literal` (base) | `CONST "literal_text"` |
| `string_literal` | `_lower_const_literal` (base) | `CONST "literal_text"` |
| `char_literal` | `_lower_const_literal` (base) | `CONST "literal_text"` |
| `true` | `_lower_canonical_true` (base) | `CONST "True"` |
| `false` | `_lower_canonical_false` (base) | `CONST "False"` |
| `null` | `_lower_canonical_none` (base) | `CONST "None"` |
| `binary_expression` | `_lower_binop` (base) | `BINOP op, lhs, rhs` |
| `unary_expression` | `_lower_unop` (base) | `UNOP op, operand` |
| `update_expression` | `_lower_update_expr` (base) | `CONST "1"` + `BINOP "+"/"−"` + `STORE_VAR/FIELD/INDEX` |
| `parenthesized_expression` | `_lower_paren` (base) | Unwraps to inner expression |
| `call_expression` | `_lower_call` (base) | `CALL_FUNCTION` / `CALL_METHOD` / `CALL_UNKNOWN` |
| `field_expression` | `_lower_field_expr` | `LOAD_FIELD obj, field_name` |
| `subscript_expression` | `_lower_subscript_expr` | `LOAD_INDEX arr, idx` |
| `assignment_expression` | `_lower_assignment_expr` | `lower_expr(rhs)` + `STORE_VAR/FIELD/INDEX` |
| `cast_expression` | `_lower_cast_expr` | Pass-through to inner value |
| `pointer_expression` | `_lower_pointer_expr` | `*p`: `LOAD_FIELD ptr, "*"` / `&x`: `UNOP "&"` |
| `sizeof_expression` | `_lower_sizeof` | `CALL_FUNCTION "sizeof", arg` |
| `conditional_expression` | `_lower_ternary` | `BRANCH_IF` + two arms + `LOAD_VAR __ternary_N` |
| `comma_expression` | `_lower_comma_expr` | Evaluates all, returns last register |
| `concatenated_string` | `_lower_const_literal` (base) | `CONST "literal_text"` |
| `type_identifier` | `_lower_identifier` (base) | `LOAD_VAR type_name` |
| `compound_literal_expression` | `_lower_compound_literal` | `NEW_OBJECT type` + `STORE_INDEX` per element |
| `initializer_list` | `_lower_initializer_list` | `NEW_ARRAY "array"` + `STORE_INDEX` per element |

## Statement Dispatch Table

The full `_STMT_DISPATCH` table populated in `__init__`:

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `expression_statement` | `_lower_expression_statement` (base) | Unwraps and dispatches inner expression |
| `declaration` | `_lower_declaration` | `CONST`/`lower_expr` + `STORE_VAR` per declarator |
| `return_statement` | `_lower_return` (base) | `RETURN val` (default: `CONST "0"`) |
| `if_statement` | `_lower_if` (base) | `BRANCH_IF` + true/false/end labels |
| `while_statement` | `_lower_while` (base) | `LABEL` + `BRANCH_IF` + body + `BRANCH` loop |
| `for_statement` | `_lower_c_style_for` (base) | init + `LABEL` cond + `BRANCH_IF` + body + update + `BRANCH` |
| `do_statement` | `_lower_do_while` | `LABEL` body + body + `LABEL` cond + `BRANCH_IF` |
| `function_definition` | `_lower_function_def_c` | `BRANCH` end + `LABEL` func + params + body + `RETURN` + `STORE_VAR` |
| `struct_specifier` | `_lower_struct_def` | `BRANCH` end + `LABEL` class + fields + `LABEL` end + `STORE_VAR` |
| `compound_statement` | `_lower_block` (base) | Iterates children as statements |
| `switch_statement` | `_lower_switch` | `BINOP "=="` per case + `BRANCH_IF` chain |
| `goto_statement` | `_lower_goto` | `BRANCH user_<label>` |
| `labeled_statement` | `_lower_labeled_stmt` | `LABEL user_<label>` + inner statement |
| `break_statement` | `_lower_break` (base) | `BRANCH` to innermost break target |
| `continue_statement` | `_lower_continue` (base) | `BRANCH` to innermost loop continue label |
| `translation_unit` | `_lower_block` (base) | Root node: iterates children as statements |
| `type_definition` | `_lower_typedef` | `CONST type_name` + `STORE_VAR alias` |
| `enum_specifier` | `_lower_enum_def` | `NEW_OBJECT "enum:<name>"` + `STORE_FIELD` per enumerator |
| `union_specifier` | `_lower_union_def` | Same structure as struct: `BRANCH` + `LABEL` + fields + `STORE_VAR` |

## Language-Specific Lowering Methods

### `_lower_declaration(node)`

Handles C variable declarations (`int x = 5;`, `int x;`). Iterates children looking for `init_declarator` nodes (declarations with initializers) and bare `identifier` nodes (declarations without initializers). Declarations without initializers get `CONST "None"` as their default value.

### `_lower_init_declarator(node)`

Handles a single `init_declarator` (e.g., `x = 5` inside `int x = 5;`). Extracts the declarator name via `_extract_declarator_name` and the value expression. If no value is present, assigns `CONST "None"`.

### `_extract_declarator_name(decl_node) -> str`

Recursively extracts the variable name from a declarator node, handling `pointer_declarator` (`*p`), `array_declarator` (`arr[10]`), and nested declarators by following the `declarator` field. Falls back to the first `identifier` child, then to the full node text.

### `_lower_function_def_c(node)`

Handles C function definitions with the `function_declarator` grammar structure (the declarator wraps both the name and parameters). Steps:
1. Extracts `declarator` and `body` fields from the `function_definition` node
2. If the declarator is a `function_declarator`, extracts name and parameters directly
3. Otherwise, recursively searches for a `function_declarator` inside (handles `pointer_declarator` wrappers like `int *foo(...)`)
4. Emits: `BRANCH end` + `LABEL func_<name>` + params + body + implicit `RETURN "0"` + `LABEL end` + `STORE_VAR name = <function:name@label>`

### `_find_function_declarator(node)`

Recursive helper that searches a declarator tree for a `function_declarator` node. Used when the top-level declarator is wrapped (e.g., pointer declarators).

### `_lower_c_params(params_node)`

Lowers C function parameters (`parameter_declaration` nodes). For each parameter, extracts the declarator name and emits `SYMBOLIC "param:<name>"` + `STORE_VAR name`.

### `_lower_struct_def(node)`

Lowers `struct_specifier` as a class-like construct. Emits the struct body inside a labeled block using the `class_` and `end_class_` label prefixes, then stores a class reference via `STORE_VAR`. Handles forward declarations and anonymous structs. Delegates field lowering to `_lower_struct_body`.

### `_lower_struct_body(node)`

Iterates a `field_declaration_list`, dispatching `field_declaration` children to `_lower_struct_field` and other named children to `_lower_stmt`.

### `_lower_struct_field(node)`

Lowers a struct field declaration as a `STORE_FIELD` on `this`. Emits: `LOAD_VAR "this"` + `CONST "0"` + `STORE_FIELD this, field_name, "0"`. The default value for all fields is `"0"`.

### `_lower_field_expr(node) -> str`

Lowers `field_expression` (both `obj.field` and `ptr->field` -- tree-sitter uses the same node type for both in C). Uses the `argument` and `field` field names. Emits `LOAD_FIELD obj_reg, field_name`.

### `_lower_subscript_expr(node) -> str`

Lowers `subscript_expression` (`arr[idx]`). Uses the `argument` and `index` field names (overridden from base's `value`/`subscript`). Emits `LOAD_INDEX arr_reg, idx_reg`.

### `_lower_assignment_expr(node) -> str`

Lowers assignment expressions (C treats assignment as an expression). Evaluates the right-hand side, stores to the left-hand side via `_lower_store_target`, and returns the value register (enabling chained assignments like `a = b = 5`).

### `_lower_store_target(target, val_reg, parent_node)` (override)

Overrides `BaseFrontend._lower_store_target` to handle C-specific store targets:
- `identifier` -> `STORE_VAR name, val`
- `field_expression` -> `STORE_FIELD obj, field_name, val`
- `subscript_expression` -> `STORE_INDEX arr, idx, val`
- `pointer_expression` (`*ptr = val`) -> `STORE_FIELD ptr, "*", val`
- Fallback -> `STORE_VAR node_text, val`

### `_lower_cast_expr(node) -> str`

Lowers `cast_expression` (e.g., `(int)x`). Type casts are transparent -- the method passes through to the inner value expression. Falls back to the last named child if the `value` field is absent.

### `_lower_pointer_expr(node) -> str`

Lowers pointer expressions with two modes based on the operator character:
- `*p` (dereference): emits `LOAD_FIELD ptr_reg, "*"`
- `&x` (address-of): emits `UNOP "&", operand_reg`

The operator is detected by scanning non-named children for `*` or `&`.

### `_lower_sizeof(node) -> str`

Lowers `sizeof(type)` and `sizeof(expr)` as `CALL_FUNCTION "sizeof", arg`. If the argument is a `type_descriptor`, it is emitted as a `CONST` string. Otherwise, the expression is lowered normally.

### `_lower_ternary(node) -> str`

Lowers `conditional_expression` (`a ? b : c`) using control flow:
1. Evaluates condition
2. Emits `BRANCH_IF cond -> ternary_true, ternary_false`
3. True arm: evaluate consequence, `STORE_VAR __ternary_N`
4. False arm: evaluate alternative, `STORE_VAR __ternary_N`
5. End: `LOAD_VAR __ternary_N` into result register

Uses a synthetic variable `__ternary_N` (where N is the label counter at emission time) to merge the two arms.

### `_lower_comma_expr(node) -> str`

Lowers comma expressions (`a, b, c`). Evaluates all subexpressions sequentially, returns the register of the last one. Initialises with a `CONST "None"` that is overwritten.

### `_lower_compound_literal(node) -> str`

Lowers compound literals (`(type){elem1, elem2, ...}`). Emits `NEW_OBJECT type_name` followed by `STORE_INDEX` for each element in the initializer list, indexed from 0.

### `_lower_do_while(node)`

Lowers `do { body } while (cond);`:
1. `LABEL do_body` + body (with loop context pushed: continue -> `do_cond`, break -> `do_end`)
2. `LABEL do_cond` + evaluate condition + `BRANCH_IF cond -> do_body, do_end`
3. `LABEL do_end`

### `_lower_switch(node)`

Lowers `switch(expr) { case ... }` as a sequential if/else chain (not a jump table):
1. Evaluate the switch subject
2. Push the end label onto `_break_target_stack`
3. For each `case_statement`: compare subject to case value with `BINOP "=="`, branch to arm or next case
4. Default case: unconditional branch to arm
5. Each arm body is followed by `BRANCH switch_end`
6. Pop break target, emit `LABEL switch_end`

Note: Fall-through is NOT modelled. Each case arm branches to `switch_end` after execution.

### `_lower_goto(node)`

Lowers `goto label;` as `BRANCH user_<label>`. The `user_` prefix namespaces user labels to avoid collisions with compiler-generated labels.

### `_lower_labeled_stmt(node)`

Lowers a labeled statement (`label: stmt`). Emits `LABEL user_<label>` then lowers the inner statement. The `user_` prefix matches `_lower_goto`.

### `_lower_enum_def(node)`

Lowers `enum_specifier` as a `NEW_OBJECT "enum:<name>"` with `STORE_FIELD` per enumerator. Enumerators with explicit values have those values lowered as expressions; enumerators without explicit values get sequential integer constants starting from 0. The enum object is stored via `STORE_VAR`.

### `_lower_union_def(node)`

Lowers `union_specifier` identically to `struct_specifier` -- uses `_lower_struct_body` for the body. Emits class-style labels and stores a class reference.

### `_lower_initializer_list(node) -> str`

Lowers `{a, b, c}` initializer lists as `NEW_ARRAY "array", size` + `STORE_INDEX` per element. Size is emitted as a `CONST`. Added to `_EXPR_DISPATCH` after the initial table construction.

### `_lower_typedef(node)`

Lowers `typedef` as `CONST original_type_name` + `STORE_VAR alias_name`. The alias (last `type_identifier` child) is stored as a variable pointing to the original type name, enabling data-flow tracking through type aliases.

## Canonical Literal Handling

C maps its boolean and null literals to canonical Python-form constants:

| C Node Type | Canonical Method | Emitted IR |
|---|---|---|
| `null` | `_lower_canonical_none` | `CONST "None"` |
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |

The `DEFAULT_RETURN_VALUE` is `"0"` (not `"None"`), so implicit function returns produce `CONST "0"` + `RETURN`.

## Example

### Source (C)

```c
struct Point {
    int x;
    int y;
};

int distance(Point* a, Point* b) {
    int dx = a->x - b->x;
    int dy = a->y - b->y;
    return dx * dx + dy * dy;
}
```

### Emitted IR (abbreviated)

```
LABEL entry
BRANCH end_class_Point_0
LABEL class_Point_1
  LOAD_VAR %0 = "this"
  CONST %1 = "0"
  STORE_FIELD %0, "x", %1
  LOAD_VAR %2 = "this"
  CONST %3 = "0"
  STORE_FIELD %2, "y", %3
LABEL end_class_Point_0
CONST %4 = "<class:Point@class_Point_1>"
STORE_VAR "Point", %4

BRANCH end_distance_2
LABEL func_distance_3
  SYMBOLIC %5 = "param:a"
  STORE_VAR "a", %5
  SYMBOLIC %6 = "param:b"
  STORE_VAR "b", %6

  LOAD_VAR %7 = "a"           # a->x
  LOAD_FIELD %8 = %7, "x"
  LOAD_VAR %9 = "b"           # b->x
  LOAD_FIELD %10 = %9, "x"
  BINOP %11 = "-", %8, %10    # dx = a->x - b->x
  STORE_VAR "dx", %11

  LOAD_VAR %12 = "a"          # a->y
  LOAD_FIELD %13 = %12, "y"
  LOAD_VAR %14 = "b"          # b->y
  LOAD_FIELD %15 = %14, "y"
  BINOP %16 = "-", %13, %15   # dy = a->y - b->y
  STORE_VAR "dy", %16

  LOAD_VAR %17 = "dx"
  LOAD_VAR %18 = "dx"
  BINOP %19 = "*", %17, %18   # dx * dx
  LOAD_VAR %20 = "dy"
  LOAD_VAR %21 = "dy"
  BINOP %22 = "*", %20, %21   # dy * dy
  BINOP %23 = "+", %19, %22   # dx*dx + dy*dy
  RETURN %23

  CONST %24 = "0"             # implicit return
  RETURN %24
LABEL end_distance_2
CONST %25 = "<function:distance@func_distance_3>"
STORE_VAR "distance", %25
```

## Design Notes

1. **Pointer dereference as field access**: `*ptr` is modelled as `LOAD_FIELD ptr, "*"` and `*ptr = v` as `STORE_FIELD ptr, "*", v`. This is a deliberate simplification -- it preserves the data-flow relationship (value flows through the pointer) without modelling actual memory addresses. The `"*"` sentinel field name is unique to the C/C++ frontends.

2. **Address-of as unary operator**: `&x` is modelled as `UNOP "&"` rather than creating a new opcode. This is consistent with the IR design philosophy of keeping the opcode set small.

3. **Cast transparency**: All cast expressions (`(int)x`, `(void*)p`) are lowered as pass-throughs to the inner value. Type information is discarded. This is intentional -- the IR is type-erased and casts do not affect data-flow analysis.

4. **No fall-through in switch**: Each `case` arm branches to `switch_end` after its body. C's fall-through semantics are not modelled. This means that `switch` without `break` in the original C code will produce different control flow in the IR than the actual C semantics. This is a known simplification.

5. **Goto/label namespacing**: User labels are prefixed with `user_` to prevent collisions with compiler-generated labels (which use prefixes like `if_true_`, `while_cond_`, `func_`, etc.).

6. **Preprocessor directives are noise**: All `preproc_*` node types are skipped entirely. `#define` macros, `#include` directives, and conditional compilation blocks do not produce IR. This means macro-expanded code is handled only through what tree-sitter produces after parsing the expanded source.

7. **Struct/union equivalence**: Unions are lowered identically to structs. The semantic difference (overlapping memory layout) is not captured in the IR.

8. **Enum representation**: Enums are modelled as objects with named fields. Each enumerator is a `STORE_FIELD` on the enum object. Enumerators without explicit values get sequential integer constants.

9. **Default return value**: Unlike most language frontends (which use `"None"`), the C frontend uses `"0"` as its `DEFAULT_RETURN_VALUE`, reflecting C's convention that `main` returns 0 on success.
