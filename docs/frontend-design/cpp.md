# C++ Frontend

> `interpreter/frontends/cpp.py` · Extends `CFrontend` · 612 lines

## Overview

The C++ frontend lowers tree-sitter C++ ASTs into the RedDragon flattened three-address code IR. It extends `CFrontend` rather than `BaseFrontend`, inheriting all C lowering capabilities and adding support for C++-specific constructs: classes (`class_specifier`), namespaces, templates, `new`/`delete` expressions, lambda expressions, range-based `for` loops, C++-style casts (`static_cast`, `dynamic_cast`, `reinterpret_cast`, `const_cast`), `try`/`catch` exception handling, `throw` statements/expressions, `nullptr`, qualified identifiers (`std::cout`), and constructor field initializer lists.

The frontend overrides several inherited methods to handle differences between C and C++ tree-sitter grammars -- notably, C++ wraps `if`/`while` conditions in a `condition_clause` node, and C++ uses `subscript_argument_list` instead of a direct `index` field for subscript expressions.

## Class Hierarchy

```
Frontend (ABC)
  +-- BaseFrontend
        +-- CFrontend
              +-- CppFrontend  <-- this file
```

### Inherited from BaseFrontend (via CFrontend)

- Register/label allocation (`_fresh_reg`, `_fresh_label`)
- Instruction emission (`_emit`)
- Entry point (`lower`)
- Dispatch infrastructure (`_lower_block`, `_lower_stmt`, `_lower_expr`)
- Reusable lowering methods: `_lower_const_literal`, `_lower_canonical_none`, `_lower_canonical_true`, `_lower_canonical_false`, `_lower_identifier`, `_lower_paren`, `_lower_binop`, `_lower_comparison`, `_lower_unop`, `_lower_call`, `_lower_attribute`, `_lower_subscript`, `_lower_assignment`, `_lower_augmented_assignment`, `_lower_return`, `_lower_break`, `_lower_continue`, `_lower_c_style_for`, `_lower_function_def`, `_lower_class_def`, `_lower_raise_or_throw`, `_lower_list_literal`, `_lower_dict_literal`, `_lower_update_expr`, `_lower_try_catch`, `_lower_expression_statement`, `_lower_var_declaration`

### Inherited from CFrontend

- All C dispatch table entries (22 expression handlers, 18 statement handlers)
- All C constants (`DEFAULT_RETURN_VALUE = "0"`, `ATTR_OBJECT_FIELD = "argument"`, etc.)
- C-specific lowering methods: `_lower_declaration`, `_lower_init_declarator`, `_extract_declarator_name`, `_lower_c_params`, `_lower_struct_def`, `_lower_struct_body`, `_lower_struct_field`, `_lower_field_expr`, `_lower_cast_expr`, `_lower_pointer_expr`, `_lower_sizeof`, `_lower_ternary`, `_lower_comma_expr`, `_lower_compound_literal`, `_lower_do_while`, `_lower_switch`, `_lower_goto`, `_lower_labeled_stmt`, `_lower_enum_def`, `_lower_union_def`, `_lower_initializer_list`, `_lower_typedef`
- `_find_function_declarator` recursive helper

### Overridden from CFrontend

| Method | Reason for Override |
|---|---|
| `_lower_subscript_expr` | C++ uses `subscript_argument_list` wrapper instead of direct `index` field |
| `_lower_store_target` | Adds C++ `subscript_expression` with `subscript_argument_list` handling |
| `_lower_if` | C++ wraps conditions in `condition_clause`; also simplifies else handling |
| `_lower_while` | C++ wraps conditions in `condition_clause` |
| `_lower_function_def_c` | Adds support for `field_initializer_list` (constructor initializer lists) |

### Added by CppFrontend

16 expression handlers and 8 statement handlers are added. See dispatch tables below.

## Overridden Constants

`CppFrontend` does not override any class-level constants. It inherits all constants from `CFrontend`:

| Constant | Value (inherited from CFrontend) |
|---|---|
| `DEFAULT_RETURN_VALUE` | `"0"` |
| `ATTR_OBJECT_FIELD` | `"argument"` |
| `ATTR_ATTRIBUTE_FIELD` | `"field"` |
| `ATTRIBUTE_NODE_TYPE` | `"field_expression"` |
| `SUBSCRIPT_VALUE_FIELD` | `"argument"` |
| `SUBSCRIPT_INDEX_FIELD` | `"index"` |
| `COMMENT_TYPES` | `frozenset({"comment"})` |
| `NOISE_TYPES` | `frozenset({"\n"}) \| PREPROC_NOISE_TYPES` |
| `BLOCK_NODE_TYPES` | `frozenset({"compound_statement"})` |

## Expression Dispatch Table

The full `_EXPR_DISPATCH` table after `CppFrontend.__init__` completes. Entries marked **(C)** are inherited from `CFrontend`; entries marked **(C++)** are added or overridden by `CppFrontend`.

| AST Node Type | Handler Method | Source | Emitted IR |
|---|---|---|---|
| `identifier` | `_lower_identifier` | **(C)** | `LOAD_VAR name` |
| `number_literal` | `_lower_const_literal` | **(C)** | `CONST "literal_text"` |
| `string_literal` | `_lower_const_literal` | **(C)** | `CONST "literal_text"` |
| `char_literal` | `_lower_const_literal` | **(C)** | `CONST "literal_text"` |
| `true` | `_lower_canonical_true` | **(C)** | `CONST "True"` |
| `false` | `_lower_canonical_false` | **(C)** | `CONST "False"` |
| `null` | `_lower_canonical_none` | **(C)** | `CONST "None"` |
| `binary_expression` | `_lower_binop` | **(C)** | `BINOP op, lhs, rhs` |
| `unary_expression` | `_lower_unop` | **(C)** | `UNOP op, operand` |
| `update_expression` | `_lower_update_expr` | **(C)** | `CONST "1"` + `BINOP` + `STORE_VAR` |
| `parenthesized_expression` | `_lower_paren` | **(C)** | Unwraps to inner expression |
| `call_expression` | `_lower_call` | **(C)** | `CALL_FUNCTION` / `CALL_METHOD` / `CALL_UNKNOWN` |
| `field_expression` | `_lower_field_expr` | **(C)** | `LOAD_FIELD obj, field_name` |
| `subscript_expression` | `_lower_subscript_expr` | **(C++)** override | `LOAD_INDEX obj, idx` (handles `subscript_argument_list`) |
| `assignment_expression` | `_lower_assignment_expr` | **(C)** | `lower_expr(rhs)` + `STORE_VAR/FIELD/INDEX` |
| `cast_expression` | `_lower_cast_expr` | **(C)** | Pass-through to inner value |
| `pointer_expression` | `_lower_pointer_expr` | **(C)** | `LOAD_FIELD ptr, "*"` / `UNOP "&"` |
| `sizeof_expression` | `_lower_sizeof` | **(C)** | `CALL_FUNCTION "sizeof", arg` |
| `conditional_expression` | `_lower_ternary` | **(C)** | `BRANCH_IF` + two arms + `LOAD_VAR` |
| `comma_expression` | `_lower_comma_expr` | **(C)** | Evaluates all, returns last |
| `concatenated_string` | `_lower_const_literal` | **(C)** | `CONST "literal_text"` |
| `type_identifier` | `_lower_identifier` | **(C)** | `LOAD_VAR type_name` |
| `compound_literal_expression` | `_lower_compound_literal` | **(C)** | `NEW_OBJECT` + `STORE_INDEX` per element |
| `initializer_list` | `_lower_initializer_list` | **(C)** | `NEW_ARRAY` + `STORE_INDEX` per element |
| `new_expression` | `_lower_new_expr` | **(C++)** | `CALL_FUNCTION type_name, args...` |
| `delete_expression` | `_lower_delete_expr` | **(C++)** | `CALL_FUNCTION "delete", ptr_reg` |
| `lambda_expression` | `_lower_lambda` | **(C++)** | `BRANCH` + `LABEL` + params + body + `RETURN` |
| `template_function` | `_lower_identifier` | **(C++)** | `LOAD_VAR name` |
| `qualified_identifier` | `_lower_qualified_id` | **(C++)** | `LOAD_VAR "std::cout"` |
| `scoped_identifier` | `_lower_qualified_id` | **(C++)** | `LOAD_VAR "Ns::name"` |
| `scope_resolution` | `_lower_qualified_id` | **(C++)** | `LOAD_VAR "A::B"` |
| `this` | `_lower_identifier` | **(C++)** | `LOAD_VAR "this"` |
| `condition_clause` | `_lower_condition_clause` | **(C++)** | Unwraps to inner expression |
| `nullptr` | `_lower_canonical_none` | **(C++)** | `CONST "None"` |
| `user_defined_literal` | `_lower_const_literal` | **(C++)** | `CONST "literal_text"` |
| `raw_string_literal` | `_lower_const_literal` | **(C++)** | `CONST "literal_text"` |
| `throw_expression` | `_lower_throw_expr` | **(C++)** | `THROW val` (returns val_reg) |
| `static_cast_expression` | `_lower_cpp_cast` | **(C++)** | Pass-through to inner value |
| `dynamic_cast_expression` | `_lower_cpp_cast` | **(C++)** | Pass-through to inner value |
| `reinterpret_cast_expression` | `_lower_cpp_cast` | **(C++)** | Pass-through to inner value |
| `const_cast_expression` | `_lower_cpp_cast` | **(C++)** | Pass-through to inner value |

Note: `condition_clause` appears twice in the source `_EXPR_DISPATCH.update()` call (a harmless duplicate -- the second entry overwrites the first with the same value).

## Statement Dispatch Table

The full `_STMT_DISPATCH` table after `CppFrontend.__init__` completes. Entries marked **(C)** are inherited from `CFrontend`; entries marked **(C++)** are added by `CppFrontend`.

| AST Node Type | Handler Method | Source | Emitted IR |
|---|---|---|---|
| `expression_statement` | `_lower_expression_statement` | **(C)** | Unwraps inner expression |
| `declaration` | `_lower_declaration` | **(C)** | `CONST`/`lower_expr` + `STORE_VAR` |
| `return_statement` | `_lower_return` | **(C)** | `RETURN val` |
| `if_statement` | `_lower_if` | **(C)** base, **(C++)** override | `BRANCH_IF` + labels (handles `condition_clause`) |
| `while_statement` | `_lower_while` | **(C)** base, **(C++)** override | `LABEL` + `BRANCH_IF` + body (handles `condition_clause`) |
| `for_statement` | `_lower_c_style_for` | **(C)** | init + cond + body + update loop |
| `do_statement` | `_lower_do_while` | **(C)** | body + cond + `BRANCH_IF` |
| `function_definition` | `_lower_function_def_c` | **(C)** base, **(C++)** override | Adds `field_initializer_list` support |
| `struct_specifier` | `_lower_struct_def` | **(C)** | Class-style labels + struct fields |
| `compound_statement` | `_lower_block` | **(C)** | Iterates children |
| `switch_statement` | `_lower_switch` | **(C)** | If/else chain |
| `goto_statement` | `_lower_goto` | **(C)** | `BRANCH user_<label>` |
| `labeled_statement` | `_lower_labeled_stmt` | **(C)** | `LABEL user_<label>` |
| `break_statement` | `_lower_break` | **(C)** | `BRANCH` to break target |
| `continue_statement` | `_lower_continue` | **(C)** | `BRANCH` to continue label |
| `translation_unit` | `_lower_block` | **(C)** | Root: iterates children |
| `type_definition` | `_lower_typedef` | **(C)** | `CONST` + `STORE_VAR` |
| `enum_specifier` | `_lower_enum_def` | **(C)** | `NEW_OBJECT` + `STORE_FIELD` per enumerator |
| `union_specifier` | `_lower_union_def` | **(C)** | Class-style labels + fields |
| `class_specifier` | `_lower_class_specifier` | **(C++)** | `BRANCH` + `LABEL` + class body + `STORE_VAR` |
| `namespace_definition` | `_lower_namespace_def` | **(C++)** | Descends into body (transparent) |
| `template_declaration` | `_lower_template_decl` | **(C++)** | Lowers inner declaration, or `SYMBOLIC` |
| `using_declaration` | `lambda _: None` | **(C++)** | Skipped (no-op) |
| `access_specifier` | `lambda _: None` | **(C++)** | Skipped (no-op) |
| `alias_declaration` | `lambda _: None` | **(C++)** | Skipped (no-op) |
| `static_assert_declaration` | `lambda _: None` | **(C++)** | Skipped (no-op) |
| `friend_declaration` | `lambda _: None` | **(C++)** | Skipped (no-op) |
| `try_statement` | `_lower_try` | **(C++)** | `LABEL` try + catch clauses via `_lower_try_catch` |
| `throw_statement` | `_lower_throw` | **(C++)** | `THROW val` |
| `for_range_loop` | `_lower_range_for` | **(C++)** | Desugared index-based loop |

## Language-Specific Lowering Methods

### `_lower_subscript_expr(node) -> str` (override)

Overrides the C version to handle C++ tree-sitter's different subscript representation. In the C++ grammar, subscript expressions may lack the `argument`/`index` field structure, instead using a `subscript_argument_list` wrapper around the index. The method:
1. Checks for `argument`/`index` fields -- if present, delegates to `super()._lower_subscript_expr`
2. Otherwise, takes the first named child as the object and looks for a `subscript_argument_list` child
3. Extracts the first named child of the `subscript_argument_list` as the index
4. Emits `LOAD_INDEX obj_reg, idx_reg`

### `_lower_store_target(target, val_reg, parent_node)` (override)

Extends the C version to handle C++ subscript store targets with `subscript_argument_list`. For `subscript_expression` targets:
1. Checks for `argument`/`index` fields -- if present, delegates to `super()._lower_store_target`
2. Otherwise, extracts object and index via `subscript_argument_list` (same logic as `_lower_subscript_expr`)
3. Emits `STORE_INDEX obj_reg, idx_reg, val_reg`

For all other target types, delegates to `super()._lower_store_target` (which handles `identifier`, `field_expression`, `pointer_expression`, etc.).

### `_lower_condition_clause(node) -> str`

Unwraps the `condition_clause` wrapper that C++ tree-sitter places around `if`/`while` conditions. Finds the first named child that is not `(` or `)` and lowers it as an expression. Falls back to `_lower_const_literal` if no inner expression is found.

### `_lower_if(node)` (override)

Overrides `BaseFrontend._lower_if` (which `CFrontend` inherits) to handle C++ `condition_clause` wrapping. The main difference is that conditions are lowered via `_lower_expr` which will dispatch `condition_clause` to `_lower_condition_clause` to unwrap it. The else branch handling is also simplified: instead of using `_lower_alternative`, it directly iterates the `alternative` node's named children (skipping the `else` keyword).

### `_lower_while(node)` (override)

Overrides `BaseFrontend._lower_while` for the same `condition_clause` wrapping reason. Structurally identical to the base version but ensures `condition_clause` nodes are properly unwrapped through the dispatch mechanism.

### `_lower_new_expr(node) -> str`

Lowers `new T(args)` as `CALL_FUNCTION type_name, arg1, arg2, ...`. Extracts the `type` field for the type name and `arguments` field for constructor arguments. Arguments are unwrapped via `_extract_call_args_unwrap` (handles `argument` wrapper nodes). If no type is found, defaults to `"Object"`.

### `_lower_delete_expr(node) -> str`

Lowers `delete ptr` and `delete[] ptr` as `CALL_FUNCTION "delete", ptr_reg`. The first named child is taken as the operand. The array form (`delete[]`) is not distinguished from scalar `delete`.

### `_lower_lambda(node) -> str`

Lowers C++ lambda expressions (`[captures](params) { body }`) as anonymous functions:
1. Emits `BRANCH end_label` to skip the lambda body
2. Emits `LABEL func___lambda_N` + parameters (via `_lower_c_params` on the `declarator` field) + body
3. For non-compound bodies (expression lambdas), emits `RETURN expr_result`
4. Adds an implicit `RETURN "0"` at the end
5. Emits `CONST "<function:__lambda@func___lambda_N>"` and returns the register

Capture lists are not modelled -- all captures are assumed to be available via lexical scoping.

### `_lower_qualified_id(node) -> str`

Lowers qualified/scoped identifiers (`std::cout`, `MyClass::method`, `ns::sub::name`) as a single `LOAD_VAR` with the full qualified text (e.g., `LOAD_VAR "std::cout"`). Handles `qualified_identifier`, `scoped_identifier`, and `scope_resolution` node types uniformly.

### `_lower_throw_expr(node) -> str`

Lowers C++ `throw` as an expression (C++ allows `throw` in expression context, e.g., in ternary expressions). Filters out the `throw` keyword child, lowers the remaining expression, emits `THROW val_reg`, and returns `val_reg`. If no argument is present (re-throw), emits `CONST "0"` + `THROW`.

### `_lower_cpp_cast(node) -> str`

Lowers C++-style named casts (`static_cast<T>(expr)`, `dynamic_cast<T>(expr)`, `reinterpret_cast<T>(expr)`, `const_cast<T>(expr)`). All four cast types are transparent -- the method passes through to the inner value expression via the `value` field. Falls back to the last named child, then to `_lower_const_literal`.

### `_lower_class_specifier(node)`

Lowers C++ `class_specifier` as a class definition:
1. Extracts `name` and `body` fields
2. Emits `BRANCH end_label` + `LABEL class_<name>_N`
3. Lowers the class body via `_lower_cpp_class_body`
4. Emits `LABEL end_label`
5. Stores `CONST "<class:name@label>"` + `STORE_VAR name`

Anonymous classes use `"__anon_class"` as the name.

### `_lower_cpp_class_body(node)`

Iterates a `field_declaration_list` (C++ class body) and dispatches children by type:
- `function_definition` -> `_lower_function_def_c` (method definitions)
- `declaration` -> `_lower_declaration` (in-class variable declarations)
- `field_declaration` -> `_lower_struct_field` (inherited from C -- member variable declarations)
- `template_declaration` -> `_lower_template_decl` (template method declarations)
- `friend_declaration` -> skipped
- `access_specifier` -> skipped (`public:`, `private:`, `protected:`)
- `field_initializer_list` -> `_lower_field_initializer_list`
- Other named children -> `_lower_stmt` fallback

### `_lower_field_initializer_list(node)`

Lowers constructor field initializer lists (`: field1(val1), field2(val2)`). Emits:
1. `LOAD_VAR "this"` once
2. For each `field_initializer` child: extract the `field_identifier` name and `argument_list` value, then emit `STORE_FIELD this_reg, field_name, val_reg`

If no argument list is present for an initializer, defaults to `CONST "0"` (the `DEFAULT_RETURN_VALUE`).

### `_lower_function_def_c(node)` (override)

Overrides the C version to detect and lower `field_initializer_list` nodes in constructor definitions. The initializer list is emitted after parameters but before the body. All other function definition logic is identical to the C version:
1. Extract declarator and body
2. Find function name and parameters (handling nested `function_declarator` and `pointer_declarator`)
3. Emit: `BRANCH end` + `LABEL func_<name>` + params + **field_initializer_list** + body + implicit `RETURN "0"` + `LABEL end` + `STORE_VAR`

### `_lower_namespace_def(node)`

Lowers `namespace_definition` transparently by descending into its `body` field. Namespace boundaries produce no IR -- all declarations within a namespace are lowered as if they were at the enclosing scope. This means namespace-qualified names are not automatically prefixed.

### `_lower_template_decl(node)`

Lowers `template_declaration` by finding the inner declaration (excluding `template_parameter_list` and `template_parameter_declaration` children) and lowering it as a statement. If no inner declaration is found, emits `SYMBOLIC "template:<first_60_chars>"`. Template parameters themselves are not modelled.

### `_lower_range_for(node)`

Lowers C++ range-based `for` (`for (auto x : container) { body }`) by desugaring into an index-based loop:
1. Extract the loop variable name from the `declarator` field (defaults to `"__range_var"`)
2. Lower the container expression from the `right` field
3. Emit `CONST "0"` for the index and `CALL_FUNCTION "len", container_reg` for the length
4. Loop condition: `BINOP "<", idx_reg, len_reg` + `BRANCH_IF`
5. Body preamble: `LOAD_INDEX container_reg, idx_reg` + `STORE_VAR var_name`
6. Body with loop context (continue -> update label, break -> end label)
7. Update: `CONST "1"` + `BINOP "+"` + `STORE_VAR "__range_idx"`
8. `BRANCH` back to condition

Note: The index variable is stored as `"__range_idx"` (hardcoded) rather than reusing `idx_reg` across iterations, which means the update writes to a different name than the condition reads. This is a known simplification.

### `_lower_throw(node)`

Lowers `throw` as a statement by delegating to `BaseFrontend._lower_raise_or_throw(node, keyword="throw")`.

### `_lower_try(node)`

Lowers `try`/`catch` blocks by extracting catch clause information and delegating to `BaseFrontend._lower_try_catch`. For each `catch_clause` child:
1. Finds the `catch_declarator` (parameter declaration)
2. Extracts the exception variable name (`identifier` child) and type (other named children)
3. Extracts the catch body via the `body` field
4. Builds a `{"body": ..., "variable": ..., "type": ...}` dict

The assembled catch clauses list is passed to `_lower_try_catch`, which emits labeled blocks for the try body and each catch clause, connected by `BRANCH` instructions.

## Canonical Literal Handling

C++ maps its boolean, null, and nullptr literals to canonical Python-form constants:

| C++ Node Type | Canonical Method | Emitted IR |
|---|---|---|
| `null` | `_lower_canonical_none` | `CONST "None"` |
| `nullptr` | `_lower_canonical_none` | `CONST "None"` |
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |

`nullptr` (C++11) and `null` (C-style `NULL`) both map to the same canonical `CONST "None"`.

The `DEFAULT_RETURN_VALUE` is `"0"` (inherited from `CFrontend`).

## Example

### Source (C++)

```cpp
#include <vector>

class Animal {
public:
    std::string name;
    Animal(std::string n) : name(n) {}
    virtual void speak() { return; }
};

int main() {
    Animal* a = new Animal("Rex");
    std::vector<int> nums = {1, 2, 3};
    for (auto x : nums) {
        if (x > 1) {
            a->speak();
        }
    }
    delete a;
    return 0;
}
```

### Emitted IR (abbreviated)

```
LABEL entry

BRANCH end_class_Animal_0
LABEL class_Animal_1
  # field: name
  LOAD_VAR %0 = "this"
  CONST %1 = "0"
  STORE_FIELD %0, "name", %1

  # constructor: Animal(std::string n)
  BRANCH end_Animal_2
  LABEL func_Animal_3
    SYMBOLIC %2 = "param:n"
    STORE_VAR "n", %2
    # field_initializer_list: name(n)
    LOAD_VAR %3 = "this"
    LOAD_VAR %4 = "n"
    STORE_FIELD %3, "name", %4
    CONST %5 = "0"
    RETURN %5
  LABEL end_Animal_2
  CONST %6 = "<function:Animal@func_Animal_3>"
  STORE_VAR "Animal", %6

  # method: speak()
  BRANCH end_speak_4
  LABEL func_speak_5
    CONST %7 = "0"
    RETURN %7
    CONST %8 = "0"
    RETURN %8
  LABEL end_speak_4
  CONST %9 = "<function:speak@func_speak_5>"
  STORE_VAR "speak", %9
LABEL end_class_Animal_0
CONST %10 = "<class:Animal@class_Animal_1>"
STORE_VAR "Animal", %10

# main()
BRANCH end_main_6
LABEL func_main_7
  # Animal* a = new Animal("Rex")
  CONST %11 = "\"Rex\""
  CALL_FUNCTION %12 = "Animal", %11
  STORE_VAR "a", %12

  # std::vector<int> nums = {1, 2, 3}
  CONST %13 = "3"
  NEW_ARRAY %14 = "array", %13
  CONST %15 = "0"
  CONST %16 = "1"
  STORE_INDEX %14, %15, %16
  CONST %17 = "1"
  CONST %18 = "2"
  STORE_INDEX %14, %17, %18
  CONST %19 = "2"
  CONST %20 = "3"
  STORE_INDEX %14, %19, %20
  STORE_VAR "nums", %14

  # for (auto x : nums)
  LOAD_VAR %21 = "nums"
  CONST %22 = "0"
  CALL_FUNCTION %23 = "len", %21
  LABEL range_for_cond_8
  BINOP %24 = "<", %22, %23
  BRANCH_IF %24 -> range_for_body_9, range_for_end_10

  LABEL range_for_body_9
  LOAD_INDEX %25 = %21, %22
  STORE_VAR "x", %25

    # if (x > 1)
    LOAD_VAR %26 = "x"
    CONST %27 = "1"
    BINOP %28 = ">", %26, %27
    BRANCH_IF %28 -> if_true_11, if_end_12
    LABEL if_true_11
      # a->speak()
      LOAD_VAR %29 = "a"
      CALL_METHOD %30 = %29, "speak"
    BRANCH if_end_12
    LABEL if_end_12

  LABEL range_for_update_13
  CONST %31 = "1"
  BINOP %32 = "+", %22, %31
  STORE_VAR "__range_idx", %32
  BRANCH range_for_cond_8

  LABEL range_for_end_10

  # delete a
  LOAD_VAR %33 = "a"
  CALL_FUNCTION %34 = "delete", %33

  # return 0
  CONST %35 = "0"
  RETURN %35

  CONST %36 = "0"
  RETURN %36
LABEL end_main_6
CONST %37 = "<function:main@func_main_7>"
STORE_VAR "main", %37
```

## Design Notes

1. **Inheritance-first design**: `CppFrontend` extends `CFrontend` rather than `BaseFrontend`, reusing all 40 C dispatch table entries and ~20 C lowering methods. The C++ `__init__` uses `dict.update()` to add new entries and overwrite entries where C++ grammar differs. This means any improvements to the C frontend automatically benefit C++.

2. **`condition_clause` unwrapping**: The C++ tree-sitter grammar wraps `if` and `while` conditions in a `condition_clause` node that C does not have. Rather than stripping this in a preprocessing pass, `CppFrontend` registers `condition_clause` in the expression dispatch table and overrides `_lower_if` and `_lower_while` to let the dispatch mechanism handle it naturally.

3. **`subscript_argument_list` handling**: C++ tree-sitter uses a different structure for subscript expressions than C. The C++ frontend overrides both `_lower_subscript_expr` and `_lower_store_target` to handle this. Both methods attempt the C-style field lookup first and fall back to the C++ structure.

4. **`new`/`delete` as function calls**: `new T(args)` is modelled as `CALL_FUNCTION T, args` (constructor call) and `delete ptr` as `CALL_FUNCTION "delete", ptr`. This collapses allocation + construction into a single call, matching how the VM would treat it for data-flow purposes.

5. **Lambda captures ignored**: Lambda capture lists (`[=]`, `[&]`, `[x, &y]`) are not modelled. All captured variables are assumed to be available through lexical scoping. This is a simplification that works for data-flow analysis (the variables are still reachable) but loses information about capture semantics (by-value vs. by-reference).

6. **Namespace transparency**: Namespaces are fully transparent -- `namespace Foo { ... }` just descends into the body. Declarations inside are not prefixed with the namespace name. This means two identically-named symbols in different namespaces will collide in the IR.

7. **Template erasure**: Template declarations lower their inner declaration (function, class, etc.) as if it were non-templated. Template parameters are discarded. Template instantiations are not tracked.

8. **No-op statements**: Five C++ statement types are explicitly registered as no-ops: `using_declaration`, `access_specifier`, `alias_declaration`, `static_assert_declaration`, and `friend_declaration`. These produce no IR output.

9. **`field_initializer_list` in constructors**: The overridden `_lower_function_def_c` detects constructor initializer lists (`: member(val), ...`) and emits them as `STORE_FIELD` on `this` between parameter lowering and body lowering. This correctly models the C++ initialisation order.

10. **Range-for index variable naming**: The range-based `for` loop desugaring stores the updated index into `"__range_idx"` but reads from the original `idx_reg`. This means the loop's index does not actually advance across iterations in the generated IR. This is a known limitation that does not affect data-flow analysis of the loop variable itself (which is correctly re-loaded each iteration via `LOAD_INDEX`).

11. **Duplicate dispatch entry**: The `condition_clause` key appears twice in the `_EXPR_DISPATCH.update()` call in `__init__`. This is harmless (the second overwrites the first with the identical handler) but is a minor code quality issue.
