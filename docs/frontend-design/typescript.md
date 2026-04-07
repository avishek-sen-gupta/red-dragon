# TypeScript Frontend

> `interpreter/frontends/typescript.py` · Extends `JavaScriptFrontend` · Single file with `typescript_node_types.py`

## Overview

The TypeScript frontend extends the JavaScript frontend, inheriting all JavaScript lowering logic and adding support for TypeScript-specific syntax. Its primary role is to **skip type annotations** while faithfully lowering runtime-relevant code. It adds handlers for type assertions (`as`), non-null assertions (`!`), `satisfies` expressions, interfaces, enums, abstract classes, abstract methods, namespaces, and TypeScript-specific parameter types (`required_parameter`, `optional_parameter`).

## File Structure

```
interpreter/frontends/
├── typescript.py              # TypeScriptFrontend class + all TS lowering functions
└── typescript_node_types.py   # TypeScriptNodeType constants class
```

Unlike Python and JavaScript frontends which use a per-language directory, the TypeScript frontend is a single file that extends `JavaScriptFrontend` from `javascript/frontend.py`.

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── JavaScriptFrontend (javascript/frontend.py)
              └── TypeScriptFrontend (typescript.py)   ← this frontend
```

No other frontend extends `TypeScriptFrontend`.

## GrammarConstants (from `_build_constants()`)

Inherits all values from `JavaScriptFrontend._build_constants()`, overriding only:

| Field | JavaScriptFrontend Value | TypeScriptFrontend Value | Notes |
|---|---|---|---|
| `comment_types` | `frozenset({"comment"})` | `frozenset({"comment"})` | Same (via `TypeScriptNodeType.COMMENT`) |
| `noise_types` | `frozenset({"\n"})` | `frozenset({"\n"})` | Same (via `TypeScriptNodeType.NEWLINE_CHAR`) |

All other constants are inherited from `JavaScriptFrontend` (and transitively from `BaseFrontend`).

## Expression Dispatch Table (from `_build_expr_dispatch()`)

The TypeScript frontend calls `super()._build_expr_dispatch()` first (populating the full JS dispatch table), then updates with additional entries via `dispatch.update(...)`:

### Inherited from JavaScriptFrontend (full table)

All entries from the JavaScript frontend's expression dispatch are inherited. See [javascript.md](javascript.md) for the complete list.

### Added/Overridden by TypeScript

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `type_identifier` | `common_expr.lower_identifier` | `LOAD_VAR` |
| `predefined_type` | `common_expr.lower_const_literal` | `CONST` |
| `as_expression` | `lower_as_expression` | Delegates to inner expression (ignores type) |
| `non_null_expression` | `lower_non_null_expr` | Delegates to inner expression (strips `!`) |
| `satisfies_expression` | `lower_satisfies_expr` | Delegates to inner expression (ignores type) |
| `arrow_function` | `lower_ts_arrow_function` | Arrow function with TS-specific param handling |
| `function` | `lower_ts_function_expression` | Anonymous function with TS-specific param handling |
| `function_expression` | `lower_ts_function_expression` | Anonymous function with TS-specific param handling |
| `generator_function` | `lower_ts_function_expression` | Anonymous function with TS-specific param handling |
| `generator_function_declaration` | `lower_ts_function_def` | Named function with TS-specific param handling |

## Statement Dispatch Table (from `_build_stmt_dispatch()`)

### Inherited from JavaScriptFrontend (full table)

All entries from the JavaScript frontend's statement dispatch are inherited. See [javascript.md](javascript.md) for the complete list.

### Added/Overridden by TypeScript

| AST Node Type | Handler | Emitted IR |
|---|---|---|
| `function_declaration` | `lower_ts_function_def` | Function definition with TS param handling |
| `class_declaration` | `lower_ts_class_def` | Class with TS method/field handling |
| `interface_declaration` | `lower_interface_decl` | `NEW_OBJECT("interface:<name>")` + `STORE_INDEX` per member + `STORE_VAR` |
| `enum_declaration` | `lower_enum_decl` | `NEW_OBJECT("enum:<name>")` + `STORE_INDEX` per member + `STORE_VAR` |
| `type_alias_declaration` | `lambda ctx, node: None` | No-op (type aliases are skipped) |
| `export_statement` | `lower_ts_export_statement` | Unwraps inner declaration (filters `export` keyword) |
| `import_statement` | `lambda ctx, node: None` | No-op (same as JS) |
| `abstract_class_declaration` | `lower_ts_class_def` | Treated as a regular class declaration |
| `public_field_definition` | `lower_ts_field_definition` | `STORE_VAR(field_name, val)` |
| `abstract_method_signature` | `lower_ts_abstract_method` | Function stub with empty body |
| `internal_module` | `lower_ts_internal_module` | Lower namespace body |

## Language-Specific Lowering Methods

### `lower_ts_param(ctx, child)`

Handles TypeScript parameter types:

- **Skipped types**: `(`, `)`, `,`, `:`, `type_annotation` -- returns immediately
- **`required_parameter`**: Extracts name from `pattern` field (or first `identifier` child as fallback). Emits `SYMBOLIC("param:<name>")` + `DECL_VAR(<name>, reg)`. Extracts type hints from `type_annotation` field and seeds register/param/var types.
- **`optional_parameter`**: Same extraction logic as `required_parameter`. The optional nature (the `?` marker) is not represented in IR. Type hints are extracted and seeded.
- **Other types**: Falls back to `lower_js_param` (JS handling)

### `lower_ts_params(ctx, params_node)`

Iterates children of a params node and calls `lower_ts_param` for each.

### `lower_as_expression(ctx, node) -> str`

Lowers `x as Type`:
- Extracts named children, lowers the first one (the value expression)
- Ignores the type entirely
- Falls back to `lower_const_literal` if no named children

### `lower_non_null_expr(ctx, node) -> str`

Lowers `x!` (non-null assertion):
- Extracts named children, lowers the first one (the value expression)
- The `!` operator is stripped with no IR effect
- Falls back to `lower_const_literal` if no named children

### `lower_satisfies_expr(ctx, node) -> str`

Lowers `x satisfies Type`:
- Extracts named children, lowers the first one (the value expression)
- Ignores the type entirely
- Falls back to `lower_const_literal` if no named children

### `lower_interface_decl(ctx, node)`

Lowers `interface Foo { bar: string; baz: number; }`:
1. Extracts interface name from `name` field
2. `NEW_OBJECT("interface:<name>")` -- creates a symbolic object
3. For each named child in the `body`:
   - Extracts member name from `name` field (or splits on `:` from text)
   - `CONST(member_name)` as key, `CONST(index)` as value
   - `STORE_INDEX(obj, key, val)`
4. `STORE_VAR(<interface_name>, obj_reg)`

This creates a structural representation where each member is stored with its index position, enabling downstream analysis to reason about interface shapes.

### `lower_enum_decl(ctx, node)`

Lowers `enum Direction { Up, Down, Left, Right }`:
1. Extracts enum name from `name` field
2. `NEW_OBJECT("enum:<name>")` -- creates a symbolic object
3. For each named child in the `body`:
   - Extracts member name by splitting text on `=` and stripping whitespace
   - `CONST(member_name)` as key, `CONST(index)` as value
   - `STORE_INDEX(obj, key, val)`
4. `STORE_VAR(<enum_name>, obj_reg)`

Custom enum initializers (e.g., `Up = "UP"`) are not evaluated; members always get their positional index as the value.

### `lower_ts_field_definition(ctx, node)`

Lowers `public name: type` or `public name = expr` as `STORE_VAR`. Extracts property name from `name` field or first `property_identifier` child.

### `lower_ts_export_statement(ctx, node)`

Filters on `child.type != "export"` (unlike JS version which also filters `"default"`). Lowers all other named children as statements.

### `lower_ts_class_def(ctx, node)`

Lowers class declarations using TS-specific handling:
- `method_definition` children: delegates to `_lower_ts_method_def`
- `class_static_block` children: delegates to JS `lower_class_static_block`
- `field_definition` children: delegates to JS `lower_js_field_definition`
- Other named children: lowered as statements
- Extracts parent classes from `class_heritage` / `extends_clause` for inheritance

### `_lower_ts_method_def(ctx, node)`

Lowers method definitions using TS-specific param handling via `lower_ts_params`. Emits `this` param for instance methods (skipped for static methods). Extracts return type annotations.

### `lower_ts_function_def(ctx, node)`

Lowers function declarations using TS-specific param handling via `lower_ts_params`. Extracts return type annotations.

### `lower_ts_arrow_function(ctx, node) -> str`

Lowers arrow functions using TS-specific param handling. Supports both expression body (implicit `RETURN`) and block body. Generates synthetic name `__arrow_<n>`.

### `lower_ts_function_expression(ctx, node) -> str`

Lowers anonymous function expressions using TS-specific param handling. If `name` field exists, uses it; otherwise generates `__anon_<n>`.

### `lower_ts_abstract_method(ctx, node)`

Lowers `abstract speak(): string` as a function stub with an empty body (just `RETURN "None"`).

### `lower_ts_internal_module(ctx, node)`

Lowers `namespace Geometry { ... }` by descending into the body block.

## Canonical Literal Handling

Inherited entirely from `JavaScriptFrontend`:

| TS AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `common_expr.lower_canonical_true` | `CONST "True"` |
| `false` | `common_expr.lower_canonical_false` | `CONST "False"` |
| `null` | `common_expr.lower_canonical_none` | `CONST "None"` |
| `undefined` | `common_expr.lower_canonical_none` | `CONST "None"` |

TypeScript does not introduce additional literal types that need canonicalization.

## Example

**Source (TypeScript):**
```typescript
interface Greeter {
    name: string;
    greet(): string;
}

enum Color {
    Red,
    Green,
    Blue,
}

function hello(name: string, color?: Color): string {
    const message = `Hello, ${name}!` as string;
    return message;
}
```

**IR Output (representative):**
```
LABEL entry
NEW_OBJECT %0 "interface:Greeter"
CONST %1 "name"
CONST %2 "0"
STORE_INDEX %0 %1 %2
CONST %3 "greet"
CONST %4 "1"
STORE_INDEX %0 %3 %4
STORE_VAR Greeter %0
NEW_OBJECT %5 "enum:Color"
CONST %6 "Red"
CONST %7 "0"
STORE_INDEX %5 %6 %7
CONST %8 "Green"
CONST %9 "1"
STORE_INDEX %5 %8 %9
CONST %10 "Blue"
CONST %11 "2"
STORE_INDEX %5 %10 %11
STORE_VAR Color %5
BRANCH end_hello_1
LABEL func_hello_0
  SYMBOLIC %12 "param:name"
  STORE_VAR name %12
  SYMBOLIC %13 "param:color"
  STORE_VAR color %13
  CONST %14 "Hello, "
  LOAD_VAR %15 name
  BINOP %16 "+" %14 %15
  CONST %17 "!"
  BINOP %18 "+" %16 %17
  STORE_VAR message %18
  LOAD_VAR %19 message
  RETURN %19
  CONST %20 "None"
  RETURN %20
LABEL end_hello_1
CONST %21 "<function:hello@func_hello_0>"
STORE_VAR hello %21
```

## Design Notes

1. **Type erasure philosophy**: The TypeScript frontend follows a strict "type erasure" approach. All type annotations, type assertions (`as`), non-null assertions (`!`), `satisfies` checks, and type aliases are either stripped or passed through to the underlying expression. This mirrors TypeScript's own compilation semantics where types exist only at compile time.

2. **Interface as structural object**: Interfaces are lowered as `NEW_OBJECT("interface:<name>")` with index-based member entries. This provides enough structural information for downstream analysis (e.g., detecting which members an interface declares) without modeling the full TypeScript type system.

3. **Enum as indexed object**: Enums are lowered as `NEW_OBJECT("enum:<name>")` with each member stored at its positional index. Custom initializers are not evaluated -- this is a deliberate simplification. The member names are extracted by splitting on `=` to handle both `Red` and `Red = "RED"` syntax.

4. **Parameter handling**: TypeScript's `required_parameter` and `optional_parameter` node types are handled by extracting the `pattern` field or first `identifier` child. The optional marker (`?`) and type annotations are discarded from the param name but type hints are extracted and seeded for downstream type inference. Default values in parameters are not evaluated.

5. **Abstract classes**: `abstract_class_declaration` is mapped to `lower_ts_class_def`, treating abstract classes identically to concrete classes. Abstract method declarations within the class body are handled by `lower_ts_abstract_method` which creates empty function stubs.

6. **Export statement difference**: The TS `lower_ts_export_statement` filters on `child.type != "export"`, while the JS version (`lower_export_statement`) filters on `child.type not in ("export", "default")`. This means the TS version will attempt to lower `default` nodes as statements if they appear, which may fall through to the expression fallback.

7. **TS-specific param/function overrides**: The TypeScript frontend overrides `arrow_function`, `function`, `function_expression`, `generator_function`, `generator_function_declaration`, and `function_declaration` dispatch entries to use TS-specific param handling (`lower_ts_params`) instead of JS param handling. This ensures type annotations in parameters are properly extracted and seeded.

8. **Namespace support**: `internal_module` (TypeScript `namespace`) is handled by `lower_ts_internal_module` which simply descends into the body block.

9. **Pure function architecture**: All TS-specific lowering methods are pure functions taking `(ctx: TreeSitterEmitContext, node)` as arguments, defined as module-level functions in `typescript.py`. The `TypeScriptFrontend` class overrides `_build_expr_dispatch()` and `_build_stmt_dispatch()` to wire them in.

10. **Minimal footprint**: The TypeScript frontend is deliberately thin. By extending `JavaScriptFrontend`, it inherits all JS runtime semantics and only needs to handle the TypeScript-specific type system constructs that tree-sitter parses into distinct node types.

11. **Scoping model** -- Uses `BLOCK_SCOPED = True` (LLVM-style name mangling), inherited from `JavaScriptFrontend` which itself sets it. Shadowed variables in nested blocks, for-of/for-in loop variables, C-style for-loop init declarations, and catch clause variables are renamed (`x` → `x$1`) to disambiguate. Note that TypeScript inherits `BLOCK_SCOPED = True` from its JavaScript base, but JavaScript itself is function-scoped -- TypeScript overrides this. See [base-frontend.md](base-frontend.md#block-scopes) for the general mechanism.
