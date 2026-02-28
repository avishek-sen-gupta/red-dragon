# TypeScript Frontend

> `interpreter/frontends/typescript.py` · Extends `JavaScriptFrontend` · ~173 lines

## Overview

The TypeScript frontend extends the JavaScript frontend, inheriting all JavaScript lowering logic and adding support for TypeScript-specific syntax. Its primary role is to **skip type annotations** while faithfully lowering runtime-relevant code. It adds handlers for type assertions (`as`), non-null assertions (`!`), `satisfies` expressions, interfaces, enums, abstract classes, and TypeScript-specific parameter types (`required_parameter`, `optional_parameter`).

## Class Hierarchy

```
Frontend (abstract)
  └── BaseFrontend (_base.py)
        └── JavaScriptFrontend (javascript.py)
              └── TypeScriptFrontend (typescript.py)   ← this file
```

No other frontend extends `TypeScriptFrontend`.

## Overridden Constants

| Constant | JavaScriptFrontend Value | TypeScriptFrontend Value | Notes |
|---|---|---|---|
| `COMMENT_TYPES` | `frozenset({"comment"})` | `frozenset({"comment"})` | Same (explicit re-declaration) |
| `NOISE_TYPES` | `frozenset({"\n"})` | `frozenset({"\n"})` | Same (explicit re-declaration) |

All other constants are inherited from `JavaScriptFrontend` (and transitively from `BaseFrontend`).

## Expression Dispatch Table

The TypeScript frontend calls `super().__init__()` first (populating the full JS dispatch tables), then updates with additional entries via `_EXPR_DISPATCH.update(...)`:

### Inherited from JavaScriptFrontend (full table)

All 34 entries from the JavaScript frontend's `_EXPR_DISPATCH` are inherited. See [javascript.md](javascript.md) for the complete list.

### Added by TypeScript

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `type_identifier` | `_lower_identifier` (base) | `LOAD_VAR` |
| `predefined_type` | `_lower_const_literal` (base) | `CONST` |
| `as_expression` | `_lower_as_expression` | Delegates to inner expression (ignores type) |
| `non_null_expression` | `_lower_non_null_expr` | Delegates to inner expression (strips `!`) |
| `satisfies_expression` | `_lower_satisfies_expr` | Delegates to inner expression (ignores type) |

## Statement Dispatch Table

### Inherited from JavaScriptFrontend (full table)

All 20 entries from the JavaScript frontend's `_STMT_DISPATCH` are inherited. See [javascript.md](javascript.md) for the complete list.

### Added/Overridden by TypeScript

| AST Node Type | Handler Method | Emitted IR |
|---|---|---|
| `interface_declaration` | `_lower_interface_decl` | `NEW_OBJECT("interface:<name>")` + `STORE_INDEX` per member + `STORE_VAR` |
| `enum_declaration` | `_lower_enum_decl` | `NEW_OBJECT("enum:<name>")` + `STORE_INDEX` per member + `STORE_VAR` |
| `type_alias_declaration` | `lambda _: None` | No-op (type aliases are skipped) |
| `export_statement` | `_lower_export_statement` (override) | Unwraps inner declaration (slightly different filter than JS version) |
| `import_statement` | `lambda _: None` | No-op (same as JS) |
| `abstract_class_declaration` | `_lower_class_def` (from JS) | Treated as a regular class declaration |

## Language-Specific Lowering Methods

### `_lower_param(child)` (override)

Overrides `JavaScriptFrontend._lower_param` to handle TypeScript parameter types:

- **Skipped types**: `(`, `)`, `,`, `:`, `type_annotation` -- returns immediately
- **`required_parameter`**: Extracts name from `pattern` field (or first `identifier` child as fallback). Emits `SYMBOLIC("param:<name>")` + `STORE_VAR(<name>, reg)`
- **`optional_parameter`**: Same extraction logic as `required_parameter`. The optional nature (the `?` marker) is not represented in IR
- **Other types**: Falls back to `super()._lower_param(child)` (JS handling)

### `_lower_as_expression(node) -> str`

Lowers `x as Type`:
- Extracts named children, lowers the first one (the value expression)
- Ignores the type entirely
- Falls back to `_lower_const_literal` if no named children

### `_lower_non_null_expr(node) -> str`

Lowers `x!` (non-null assertion):
- Extracts named children, lowers the first one (the value expression)
- The `!` operator is stripped with no IR effect
- Falls back to `_lower_const_literal` if no named children

### `_lower_satisfies_expr(node) -> str`

Lowers `x satisfies Type`:
- Extracts named children, lowers the first one (the value expression)
- Ignores the type entirely
- Falls back to `_lower_const_literal` if no named children

### `_lower_interface_decl(node)`

Lowers `interface Foo { bar: string; baz: number; }`:
1. Extracts interface name from `name` field
2. `NEW_OBJECT("interface:<name>")` -- creates a symbolic object
3. For each named child in the `body`:
   - Extracts member name from `name` field (or splits on `:` from text)
   - `CONST(member_name)` as key, `CONST(index)` as value
   - `STORE_INDEX(obj, key, val)`
4. `STORE_VAR(<interface_name>, obj_reg)`

This creates a structural representation where each member is stored with its index position, enabling downstream analysis to reason about interface shapes.

### `_lower_enum_decl(node)`

Lowers `enum Direction { Up, Down, Left, Right }`:
1. Extracts enum name from `name` field
2. `NEW_OBJECT("enum:<name>")` -- creates a symbolic object
3. For each named child in the `body`:
   - Extracts member name by splitting text on `=` and stripping whitespace
   - `CONST(member_name)` as key, `CONST(index)` as value
   - `STORE_INDEX(obj, key, val)`
4. `STORE_VAR(<enum_name>, obj_reg)`

Custom enum initializers (e.g., `Up = "UP"`) are not evaluated; members always get their positional index as the value.

### `_lower_export_statement(node)` (override)

Overrides the JS version with a slightly different filter: skips children where `child.type == "export"` (checking type equality rather than inclusion in a set with `"default"`). Lowers all other named children as statements.

## Canonical Literal Handling

Inherited entirely from `JavaScriptFrontend`:

| TS AST Node Type | Handler | Canonical IR Value |
|---|---|---|
| `true` | `_lower_canonical_true` | `CONST "True"` |
| `false` | `_lower_canonical_false` | `CONST "False"` |
| `null` | `_lower_canonical_none` | `CONST "None"` |
| `undefined` | `_lower_canonical_none` | `CONST "None"` |

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

4. **Parameter handling**: TypeScript's `required_parameter` and `optional_parameter` node types are handled by extracting the `pattern` field or first `identifier` child. The optional marker (`?`) and type annotations are discarded. Default values in parameters are not evaluated.

5. **Abstract classes**: `abstract_class_declaration` is mapped directly to `_lower_class_def` from the JS frontend, treating abstract classes identically to concrete classes. Abstract method declarations within the class body will be handled by the JS class body iteration logic.

6. **Export statement difference**: The TS `_lower_export_statement` filters on `child.type != "export"`, while the JS version filters on `child.type not in ("export", "default")`. This means the TS version will attempt to lower `default` nodes as statements if they appear, which may fall through to the expression fallback.

7. **Minimal footprint**: At ~173 lines, the TypeScript frontend is deliberately thin. By extending `JavaScriptFrontend`, it inherits all JS runtime semantics and only needs to handle the TypeScript-specific type system constructs that tree-sitter parses into distinct node types.
