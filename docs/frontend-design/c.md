# C Frontend

> `interpreter/frontends/c/` · Extends `BaseFrontend` · Directory structure below

## Overview

The C frontend lowers tree-sitter C ASTs into the RedDragon flattened three-address code IR. It handles the full range of C constructs including pointer arithmetic, struct/union/enum definitions, `sizeof`, ternary expressions, `goto`/labels, `switch` statements, compound literals, and C-style `for` loops. Preprocessor directives are treated as noise and skipped.

The frontend introduces several C-specific lowering patterns:
- Pointer dereference (`*p`) maps to `LOAD_FIELD ptr, "*"` and store-through-pointer (`*p = v`) maps to `STORE_FIELD ptr, "*", val`
- Address-of (`&x`) maps to `UNOP "&"`
- `sizeof` maps to `CALL_FUNCTION "sizeof"`
- `goto`/labels use a `user_` prefix to namespace user labels away from compiler-generated labels
- `switch` is lowered as an if/else chain with `BINOP "=="` comparisons

## Directory Structure

```
interpreter/frontends/c/
  frontend.py       CFrontend class (thin orchestrator)
  node_types.py     CNodeType constants for tree-sitter node type strings
  expressions.py    C-specific expression lowerers (pure functions)
  control_flow.py   C-specific control flow lowerers (pure functions)
  declarations.py   C-specific declaration lowerers (pure functions)
```

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend
        +-- CFrontend          <-- interpreter/frontends/c/frontend.py
              +-- CppFrontend  (extends CFrontend)
```

`CFrontend` extends `BaseFrontend` directly. It is a thin orchestrator that builds dispatch tables from pure functions defined in sibling modules (`expressions.py`, `control_flow.py`, `declarations.py`) and shared modules (`common.expressions`, `common.control_flow`, `common.assignments`). All lowering logic lives in pure functions that take a `TreeSitterEmitContext` as their first argument.

`CppFrontend` extends `CFrontend`, inheriting all C dispatch entries and pure functions, then adding C++-specific constructs on top.

## GrammarConstants (`_build_constants`)

`CFrontend._build_constants()` returns a `GrammarConstants` instance with these fields:

| Field | Value | Purpose |
|---|---|---|
| `default_return_value` | `"0"` | Implicit return value for functions without explicit return |
| `attr_object_field` | `"argument"` | Tree-sitter field name for the object in `obj.field` |
| `attr_attribute_field` | `"field"` | Tree-sitter field name for the attribute in `obj.field` |
| `attribute_node_type` | `CNodeType.FIELD_EXPRESSION` | Tree-sitter node type for member access expressions |
| `subscript_value_field` | `"argument"` | Tree-sitter field name for the array in `arr[idx]` |
| `subscript_index_field` | `"index"` | Tree-sitter field name for the index in `arr[idx]` |
| `comment_types` | `frozenset({CNodeType.COMMENT})` | Node types treated as comments |
| `noise_types` | `frozenset({"\n"}) \| PREPROC_NOISE_TYPES` | Expanded to include all preprocessor directive node types |
| `block_node_types` | `frozenset({CNodeType.COMPOUND_STATEMENT, CNodeType.TRANSLATION_UNIT})` | Recognises `{ ... }` blocks and top-level translation units as block nodes |
| `none_literal` | `"None"` | Canonical none |
| `true_literal` | `"True"` | Canonical true |
| `false_literal` | `"False"` | Canonical false |

### `PREPROC_NOISE_TYPES`

A module-level constant in `frontend.py` defining preprocessor node types that are silently skipped:

```python
PREPROC_NOISE_TYPES = frozenset({
    CNodeType.PREPROC_INCLUDE,
    CNodeType.PREPROC_DEFINE,
    CNodeType.PREPROC_IFDEF,
    CNodeType.PREPROC_IFNDEF,
    CNodeType.PREPROC_IF,
    CNodeType.PREPROC_ELSE,
    CNodeType.PREPROC_ELIF,
    CNodeType.PREPROC_ENDIF,
    CNodeType.PREPROC_CALL,
    CNodeType.PREPROC_DEF,
})
```

## Expression Dispatch Table

The full expression dispatch returned by `_build_expr_dispatch()`:

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `identifier` | `common_expr.lower_identifier` | `LOAD_VAR name` |
| `number_literal` | `common_expr.lower_const_literal` | `CONST "literal_text"` |
| `string_literal` | `common_expr.lower_const_literal` | `CONST "literal_text"` |
| `char_literal` | `common_expr.lower_const_literal` | `CONST "literal_text"` |
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `null` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `binary_expression` | `common_expr.lower_binop` | `BINOP op, lhs, rhs` |
| `unary_expression` | `common_expr.lower_unop` | `UNOP op, operand` |
| `update_expression` | `common_expr.lower_update_expr` | `CONST "1"` + `BINOP "+"/"−"` + `STORE_VAR/FIELD/INDEX` |
| `parenthesized_expression` | `common_expr.lower_paren` | Unwraps to inner expression |
| `call_expression` | `common_expr.lower_call` | `CALL_FUNCTION` / `CALL_METHOD` / `CALL_UNKNOWN` |
| `field_expression` | `c_expr.lower_field_expr` | `LOAD_FIELD obj, field_name` |
| `subscript_expression` | `c_expr.lower_subscript_expr` | `LOAD_INDEX arr, idx` |
| `assignment_expression` | `c_expr.lower_assignment_expr` | `lower_expr(rhs)` + `STORE_VAR/FIELD/INDEX` |
| `cast_expression` | `c_expr.lower_cast_expr` | Pass-through to inner value |
| `pointer_expression` | `c_expr.lower_pointer_expr` | `*p`: `LOAD_FIELD ptr, "*"` / `&x`: `UNOP "&"` |
| `sizeof_expression` | `c_expr.lower_sizeof` | `CALL_FUNCTION "sizeof", arg` |
| `conditional_expression` | `c_expr.lower_ternary` | `BRANCH_IF` + two arms + `LOAD_VAR __ternary_N` |
| `comma_expression` | `c_expr.lower_comma_expr` | Evaluates all, returns last register |
| `concatenated_string` | `common_expr.lower_const_literal` | `CONST "literal_text"` |
| `type_identifier` | `common_expr.lower_identifier` | `LOAD_VAR type_name` |
| `compound_literal_expression` | `c_expr.lower_compound_literal` | `NEW_OBJECT type` + `STORE_INDEX` per element |
| `preproc_arg` | `common_expr.lower_const_literal` | `CONST "literal_text"` |
| `initializer_list` | `c_expr.lower_initializer_list` | `NEW_ARRAY "array"` + `STORE_INDEX` per element |
| `initializer_pair` | `c_expr.lower_initializer_pair` | Lowers the value (field binding handled by parent) |

## Statement Dispatch Table

The full statement dispatch returned by `_build_stmt_dispatch()`:

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `expression_statement` | `common_assign.lower_expression_statement` | Unwraps and dispatches inner expression |
| `declaration` | `c_decl.lower_declaration` | `CONST`/`lower_expr` + `STORE_VAR` per declarator |
| `return_statement` | `common_assign.lower_return` | `RETURN val` (default: `CONST "0"`) |
| `if_statement` | `common_cf.lower_if` | `BRANCH_IF` + true/false/end labels |
| `while_statement` | `common_cf.lower_while` | `LABEL` + `BRANCH_IF` + body + `BRANCH` loop |
| `for_statement` | `common_cf.lower_c_style_for` | init + `LABEL` cond + `BRANCH_IF` + body + update + `BRANCH`; init vars block-scoped |
| `do_statement` | `c_cf.lower_do_while` | `LABEL` body + body + `LABEL` cond + `BRANCH_IF` |
| `function_definition` | `c_decl.lower_function_def_c` | `BRANCH` end + `LABEL` func + params + body + `RETURN` + `STORE_VAR` |
| `struct_specifier` | `c_decl.lower_struct_def` | `BRANCH` end + `LABEL` class + fields + `LABEL` end + `STORE_VAR` |
| `compound_statement` | `lambda ctx, node: ctx.lower_block(node)` | Iterates children as statements |
| `switch_statement` | `c_cf.lower_switch` | `BINOP "=="` per case + `BRANCH_IF` chain |
| `case_statement` | `c_cf.lower_case_as_block` | Safety net: lowers case body children as statements |
| `goto_statement` | `c_cf.lower_goto` | `BRANCH user_<label>` |
| `labeled_statement` | `c_cf.lower_labeled_stmt` | `LABEL user_<label>` + inner statement |
| `break_statement` | `common_cf.lower_break` | `BRANCH` to innermost break target |
| `continue_statement` | `common_cf.lower_continue` | `BRANCH` to innermost loop continue label |
| `translation_unit` | `lambda ctx, node: ctx.lower_block(node)` | Root node: iterates children as statements |
| `type_definition` | `c_decl.lower_typedef` | Seeds type alias (no IR emitted) |
| `enum_specifier` | `c_decl.lower_enum_def` | `NEW_OBJECT "enum:<name>"` + `STORE_FIELD` per enumerator |
| `union_specifier` | `c_decl.lower_union_def` | Same structure as struct: `BRANCH` + `LABEL` + fields + `STORE_VAR` |
| `preproc_function_def` | `c_decl.lower_preproc_function_def` | `BRANCH` + `LABEL` + params + body + `RETURN` + `STORE_VAR` |

## Language-Specific Lowering Methods

### `c_decl.lower_declaration(ctx, node)`

Handles C variable declarations (`int x = 5;`, `int x;`). Extracts struct type and type hint, then iterates children looking for `init_declarator` nodes (declarations with initializers) and bare `identifier`/`pointer_declarator` nodes (declarations without initializers). Declarations without initializers get `CONST "None"` as their default value, or `CALL_FUNCTION struct_type` if a struct type is detected. Seeds variable types via `ctx.seed_var_type`.

### `c_decl._lower_init_declarator(ctx, node, struct_type, type_hint)`

Handles a single `init_declarator` (e.g., `x = 5` inside `int x = 5;`). Extracts the declarator name via `extract_declarator_name` and the value expression. If no value is present, assigns `CONST "None"` or calls the struct constructor.

### `c_decl.extract_declarator_name(ctx, decl_node) -> str`

Recursively extracts the variable name from a declarator node, handling `pointer_declarator` (`*p`), `array_declarator` (`arr[10]`), `parenthesized_declarator`, and nested declarators by following the `declarator` field. Falls back to the first `identifier` child, then to the full node text.

### `c_decl.lower_function_def_c(ctx, node)`

Handles C function definitions with the `function_declarator` grammar structure (the declarator wraps both the name and parameters). Steps:
1. Extracts `declarator` and `body` fields from the `function_definition` node
2. Uses `_find_innermost_function_declarator` to handle complex declarators (e.g., function-pointer return types)
3. Extracts name and parameters from the target function_declarator
4. Emits: `BRANCH end` + `LABEL func_<name>` + params + body + implicit `RETURN "0"` + `LABEL end` + `STORE_VAR name = <function:name@label>`
5. Seeds function return type via `ctx.seed_func_return_type`

### `c_decl.lower_c_params(ctx, params_node)`

Lowers C function parameters (`parameter_declaration` nodes). For each parameter, extracts the declarator name, computes type hint (including pointer depth), and emits `SYMBOLIC "param:<name>"` + `STORE_VAR name`. Seeds register, parameter, and variable types.

### `c_decl.lower_struct_def(ctx, node)`

Lowers `struct_specifier` as a class-like construct. Emits the struct body inside a labeled block using the `class_` and `end_class_` label prefixes, then stores a class reference via `STORE_VAR`. Handles forward declarations and anonymous structs. Delegates field lowering to `lower_struct_body`.

### `c_decl.lower_struct_body(ctx, node)`

Iterates a `field_declaration_list`, dispatching `field_declaration` children to `lower_struct_field` and other named children to `ctx.lower_stmt`.

### `c_decl.lower_struct_field(ctx, node)`

Lowers a struct field declaration as a `STORE_FIELD` on `this`. Emits: `LOAD_VAR "this"` + `CONST "0"` + `STORE_FIELD this, field_name, "0"`. The default value for all fields is `"0"`.

### `c_expr.lower_field_expr(ctx, node) -> str`

Lowers `field_expression` (both `obj.field` and `ptr->field` -- tree-sitter uses the same node type for both in C). Uses the `argument` and `field` field names. Emits `LOAD_FIELD obj_reg, field_name`.

### `c_expr.lower_subscript_expr(ctx, node) -> str`

Lowers `subscript_expression` (`arr[idx]`). Uses the `argument` and `index` field names. Emits `LOAD_INDEX arr_reg, idx_reg`.

### `c_expr.lower_assignment_expr(ctx, node) -> str`

Lowers assignment expressions (C treats assignment as an expression). Evaluates the right-hand side, stores to the left-hand side via `lower_c_store_target`, and returns the value register (enabling chained assignments like `a = b = 5`).

### `c_expr.lower_c_store_target(ctx, target, val_reg, parent_node)`

C-specific store target handling:
- `identifier` -> `STORE_VAR name, val`
- `field_expression` -> `STORE_FIELD obj, field_name, val`
- `subscript_expression` -> `STORE_INDEX arr, idx, val`
- `pointer_expression` (`*ptr = val`) -> `STORE_FIELD ptr, "*", val`
- Fallback -> `STORE_VAR node_text, val`

### `c_expr.lower_cast_expr(ctx, node) -> str`

Lowers `cast_expression` (e.g., `(int)x`). Type casts are transparent -- the method passes through to the inner value expression. Falls back to the last named child if the `value` field is absent.

### `c_expr.lower_pointer_expr(ctx, node) -> str`

Lowers pointer expressions with two modes based on the operator character:
- `*p` (dereference): emits `LOAD_FIELD ptr_reg, "*"`
- `&x` (address-of): emits `UNOP "&", operand_reg`

The operator is detected by scanning non-named children for `*` or `&`.

### `c_expr.lower_sizeof(ctx, node) -> str`

Lowers `sizeof(type)` and `sizeof(expr)` as `CALL_FUNCTION "sizeof", arg`. If the argument is a `type_descriptor`, it is emitted as a `CONST` string. Otherwise, the expression is lowered normally.

### `c_expr.lower_ternary(ctx, node) -> str`

Lowers `conditional_expression` (`a ? b : c`) using control flow:
1. Evaluates condition
2. Emits `BRANCH_IF cond -> ternary_true, ternary_false`
3. True arm: evaluate consequence, `STORE_VAR __ternary_N`
4. False arm: evaluate alternative, `STORE_VAR __ternary_N`
5. End: `LOAD_VAR __ternary_N` into result register

Uses a synthetic variable `__ternary_N` (where N is the label counter at emission time) to merge the two arms.

### `c_expr.lower_comma_expr(ctx, node) -> str`

Lowers comma expressions (`a, b, c`). Evaluates all subexpressions sequentially, returns the register of the last one. Initialises with a `CONST "None"` that is overwritten.

### `c_expr.lower_compound_literal(ctx, node) -> str`

Lowers compound literals (`(type){elem1, elem2, ...}`). Emits `NEW_OBJECT type_name` followed by `STORE_INDEX` for each element in the initializer list, indexed from 0.

### `c_expr.lower_initializer_list(ctx, node) -> str`

Lowers `{a, b, c}` initializer lists as `NEW_ARRAY "array", size` + `STORE_INDEX` per element. Size is emitted as a `CONST`.

### `c_expr.lower_initializer_pair(ctx, node) -> str`

Lowers `.field = value` designated initializers. Extracts and lowers the value expression (field binding is handled by the parent compound literal).

### `c_cf.lower_do_while(ctx, node)`

Lowers `do { body } while (cond);`:
1. `LABEL do_body` + body (with loop context pushed: continue -> `do_cond`, break -> `do_end`)
2. `LABEL do_cond` + evaluate condition + `BRANCH_IF cond -> do_body, do_end`
3. `LABEL do_end`

### `c_cf.lower_switch(ctx, node)`

Lowers `switch(expr) { case ... }` as a sequential if/else chain (not a jump table):
1. Evaluate the switch subject
2. Push the end label onto `break_target_stack`
3. For each `case_statement`: compare subject to case value with `BINOP "=="`, branch to arm or next case
4. Default case: unconditional branch to arm
5. Each arm body is followed by `BRANCH switch_end`
6. Pop break target, emit `LABEL switch_end`

Note: Fall-through is NOT modelled. Each case arm branches to `switch_end` after execution.

### `c_cf.lower_case_as_block(ctx, node)`

Defensive handler for `case_statement` encountered via `lower_block`. In normal flow, `case_statement` is consumed by `lower_switch`. This handler exists as a safety net and lowers the case body children as statements.

### `c_cf.lower_goto(ctx, node)`

Lowers `goto label;` as `BRANCH user_<label>`. The `user_` prefix namespaces user labels to avoid collisions with compiler-generated labels.

### `c_cf.lower_labeled_stmt(ctx, node)`

Lowers a labeled statement (`label: stmt`). Emits `LABEL user_<label>` then lowers the inner statement. The `user_` prefix matches `lower_goto`.

### `c_decl.lower_enum_def(ctx, node)`

Lowers `enum_specifier` as a `NEW_OBJECT "enum:<name>"` with `STORE_FIELD` per enumerator. Enumerators with explicit values have those values lowered as expressions; enumerators without explicit values get sequential integer constants starting from 0. The enum object is stored via `STORE_VAR`.

### `c_decl.lower_union_def(ctx, node)`

Lowers `union_specifier` identically to `struct_specifier` -- uses `lower_struct_body` for the body. Emits class-style labels and stores a class reference.

### `c_decl.lower_typedef(ctx, node)`

Lowers `typedef` by seeding a type alias via `ctx.seed_type_alias`. Extracts the base type, resolves pointer depth for pointer typedefs (e.g., `typedef int* IntPtr`), and registers the alias name to the effective type.

### `c_decl.lower_preproc_function_def(ctx, node)`

Lowers `#define FUNC(args) body` as a function stub. Emits the same function definition pattern as `lower_function_def_c` but extracts name/params/value from the preprocessor macro structure.

## Canonical Literal Handling

C maps its boolean and null literals to canonical Python-form constants:

| C Node Type | Handler | Emitted IR |
|---|---|---|
| `null` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |

The `default_return_value` is `"0"` (not `"None"`), so implicit function returns produce `CONST "0"` + `RETURN`.

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

6. **Preprocessor directives are noise**: All `preproc_*` node types are skipped entirely. `#define` macros, `#include` directives, and conditional compilation blocks do not produce IR. This means macro-expanded code is handled only through what tree-sitter produces after parsing the expanded source. Exception: `preproc_function_def` (`#define FUNC(args) body`) is lowered as a function stub.

7. **Struct/union equivalence**: Unions are lowered identically to structs. The semantic difference (overlapping memory layout) is not captured in the IR.

8. **Enum representation**: Enums are modelled as objects with named fields. Each enumerator is a `STORE_FIELD` on the enum object. Enumerators without explicit values get sequential integer constants.

9. **Default return value**: Unlike most language frontends (which use `"None"`), the C frontend uses `"0"` as its `default_return_value`, reflecting C's convention that `main` returns 0 on success.

10. **Pure function architecture**: All lowering logic is implemented as pure functions taking `(ctx: TreeSitterEmitContext, node)` rather than instance methods. The `CFrontend` class is a thin orchestrator that builds dispatch tables from these functions via `_build_expr_dispatch()` and `_build_stmt_dispatch()`. Node type strings are centralised in `CNodeType` constants.

11. **Scoping model** -- Uses `BLOCK_SCOPED = True` (LLVM-style name mangling). Shadowed variables in nested compound statements (`{ }`), C-style for-loop init declarations, and variables in switch/case blocks are renamed (`x` → `x$1`) to disambiguate. See [base-frontend.md](base-frontend.md#block-scopes) for the general mechanism.
