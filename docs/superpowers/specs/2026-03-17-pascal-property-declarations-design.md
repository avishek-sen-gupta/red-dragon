# Pascal Property Declarations Design

**Issue:** red-dragon-93w
**Date:** 2026-03-17
**Status:** Approved

## Goal

Support Delphi/Object Pascal property declarations (`property Name: string read FName write SetName;`) so that accessing a property routes through the correct field or method. Reuse the common property-accessor infrastructure created for Kotlin.

## Background

Pascal (Delphi/Object Pascal) properties are declarative mappings:

```pascal
type
  TFoo = class
  private
    FName: string;
    procedure SetName(const AValue: string);
  public
    property Name: string read FName write SetName;
  end;
```

`property Name: string read FName write SetName` means:
- Reading `obj.Name` reads field `FName` directly
- Writing `obj.Name := value` calls procedure `SetName(value)`

Accessors come in two flavors:
- **Field accessor**: `read FName` — direct field access on backing field
- **Method accessor**: `read GetName` — calls a function/procedure

### Tree-sitter structure

Verified by parsing actual Pascal with tree-sitter:

```
declClass
  kClass
  declSection
    kPrivate
    declField              ← FName: string
      identifier "FName"
      type > declString
    declProc               ← procedure SetName(...)
      kProcedure
      identifier "SetName"
      declArgs
  declSection
    kPublic
    declProp               ← property Name: string read FName write SetName
      kProperty
      identifier "Name"
      type > declString
      kRead
      identifier "FName"   ← read accessor target
      kWrite
      identifier "SetName" ← write accessor target
  kEnd
```

### Current state

The Pascal frontend currently does NOT traverse `declClass` bodies. `lower_pascal_decl_type` only registers the type name in `ctx._pascal_record_types` and emits CLASS_REF. Fields, methods, and properties inside classes are all ignored. This must be fixed as a prerequisite.

## Design

### Prerequisite: Class body traversal

Expand `lower_pascal_decl_type` to iterate `declSection` children inside `declClass`:
- `declField` nodes: collect field names (for accessor-type detection) and emit field defaults in synthetic `__init__`. Pascal fields have no explicit initializer, so use `None` as the default value for all field types.
- `declProc` nodes: lower as methods via a new `_lower_pascal_method` function. This emits the same BRANCH/LABEL/params/body/RETURN pattern as `lower_pascal_proc` but prepends `SYMBOLIC param:this` + `DECL_VAR this` before the method parameters. Note: `declProc` nodes inside `declClass` are forward declarations only (no body); the actual method bodies are defined outside the class as `defProc` with `procedure TFoo.MethodName(...)`. The class body traversal should lower forward declarations as method signatures with `this` injected, and the existing `defProc` lowering handles the bodies.
- `declProp` nodes: parse and emit synthetic accessor methods

Set `ctx._current_class_name` around class body traversal (save/restore pattern used by all other frontends).

### Property accessor handling

For each `declProp` node, extract:
- Property name (first `identifier` child)
- Read accessor name (`identifier` after `kRead`)
- Write accessor name (`identifier` after `kWrite`, if present)

**Determine accessor type** by checking if the accessor name matches any `declField` across all `declSection` children of the `declClass`. Collect all field names from `declField` nodes in a first pass over the class body before processing properties.

**For field-targeted read accessor** (`read FName` where `FName` is a field):
- Emit a synthetic `__get_<prop>__` method that does `LOAD_FIELD this "FName"` and returns it
- Register via `register_property_accessor(ctx, class_name, prop_name, "get")`

**For method-targeted read accessor** (`read GetName` where `GetName` is a method):
- Emit a synthetic `__get_<prop>__` method that does `CALL_METHOD this "GetName"` and returns it
- Register via `register_property_accessor(ctx, class_name, prop_name, "get")`

**For field-targeted write accessor** (`write FName` where `FName` is a field):
- Emit a synthetic `__set_<prop>__` method with `this` and `value` params that does `STORE_FIELD this "FName" value`
- Register via `register_property_accessor(ctx, class_name, prop_name, "set")`

**For method-targeted write accessor** (`write SetName` where `SetName` is a method):
- Emit a synthetic `__set_<prop>__` method with `this` and `value` params that does `CALL_METHOD this "SetName" value`
- Register via `register_property_accessor(ctx, class_name, prop_name, "set")`

**Read-only properties**: If no `kWrite` is present, only the getter is registered. Writing to the property falls through to plain `STORE_FIELD` (which stores to the property name, not the backing field — acceptable behavior for an unregistered setter).

### Wiring dot access and assignment

Unlike Kotlin (where `this.x` interception is sufficient because the backing field keeps its original name), Pascal properties map a property name (`Name`) to a different backing field (`FName`). This means `LOAD_FIELD foo "Name"` would fail — there is no field called `Name`. Therefore, **all dot access on typed variables must be intercepted**, not just `self`.

**`lower_pascal_dot`**: Look up the object's class type via `ctx._pascal_var_types` (for variables) or `ctx._current_class_name` (for `self`). If a class is resolved, call `emit_field_load_or_getter`. Otherwise, fall through to plain `LOAD_FIELD`.

**`lower_pascal_assignment`** (EXPR_DOT branch): Same logic — look up object class type, call `emit_field_store_or_setter` if resolved, otherwise plain `STORE_FIELD`.

Note: Pascal uses `self` in method bodies to refer to the current instance. However, Pascal programmers typically access fields and properties by bare name (no `self.` prefix) inside methods. Since bare identifier access goes through `LOAD_VAR`/`STORE_VAR` (not through dot access), accessor interception for bare names would require intercepting identifier lowering. **In-scope: dot-based property access (`foo.Name`, `self.Name`). Out of scope: bare `Name` interception inside methods (requires type inference).**

### Variable-to-class tracking

Add `ctx._pascal_var_types: dict[str, str]` mapping variable names to their class type names. Populated in `lower_pascal_decl_var` when the type is in `_pascal_record_types`. Also populated in `_lower_pascal_single_param` when a parameter's type is in `_pascal_record_types`.

Initialize `_pascal_var_types` in `_build_context` alongside `_pascal_record_types` (not via `getattr`).

**Scoping**: This is a flat dict — variable name shadowing in nested procedures would overwrite earlier entries. This is acceptable for our target programs: Pascal nested-procedure shadowing of typed class variables is rare, and handling it correctly would require scope-aware type tracking. If shadowing causes issues, it can be addressed in a follow-up.

In `lower_pascal_dot`, check if the object identifier's name is in `_pascal_var_types`. If so, use `emit_field_load_or_getter` with that class name. Same for the assignment EXPR_DOT branch.

### No VM changes

The entire feature is frontend-only. Synthetic methods use existing LABEL/BRANCH/RETURN function infrastructure and CALL_METHOD. Field access uses existing LOAD_FIELD/STORE_FIELD.

## IR emission example

```pascal
type
  TFoo = class
  private
    FName: string;
    procedure SetName(const AValue: string);
  public
    property Name: string read FName write SetName;
  end;
```

IR for class body (pseudo-IR):
```
# Synthetic __init__ stores default field values (None for all types — Pascal
# fields have no explicit initializers; the VM's type coercion handles
# converting None to 0/""/ etc. when the field is first written)
BRANCH end___init__
LABEL __init__
  SYMBOLIC param:this
  DECL_VAR this, %0
  CONST "None" → %1
  STORE_FIELD this, "FName", %1
  RETURN
LABEL end___init__

# SetName method (lowered from declProc with this injected)
BRANCH end_SetName
LABEL SetName
  SYMBOLIC param:this
  DECL_VAR this, %0
  SYMBOLIC param:AValue
  DECL_VAR AValue, %1
  STORE_FIELD this, "FName", %1   ← FName := AValue
  RETURN
LABEL end_SetName

# Synthetic getter for property Name (read FName → field access)
BRANCH end___get_Name__
LABEL __get_Name__
  SYMBOLIC param:this
  DECL_VAR this, %0
  LOAD_FIELD this, "FName" → %1
  RETURN %1
LABEL end___get_Name__

# Synthetic setter for property Name (write SetName → method call)
BRANCH end___set_Name__
LABEL __set_Name__
  SYMBOLIC param:this
  DECL_VAR this, %0
  SYMBOLIC param:value
  DECL_VAR value, %1
  CALL_METHOD this, "SetName", %1 → %2
  RETURN
LABEL end___set_Name__
```

External usage (`foo.Name`):
```
# foo.Name read → CALL_METHOD __get_Name__ (intercepted via var type tracking)
CALL_METHOD foo, "__get_Name__" → %0

# foo.Name := "hello" → CALL_METHOD __set_Name__ (intercepted via var type tracking)
CONST "hello" → %0
CALL_METHOD foo, "__set_Name__", %0
```

## Scope

**In scope:**
- Node type constants for `declProp`, `kProperty`, `kRead`, `kWrite`, `declSection`, `kPrivate`, `kPublic`, `declField`
- Class body traversal (fields, methods, properties)
- Synthetic `__init__` for field defaults
- Method lowering with `this` injection inside classes
- Property accessor synthetic methods (field-targeted and method-targeted)
- Variable-to-class type tracking for external property access
- Dot access and assignment interception
- Unit and integration tests

**Out of scope:**
- Bare name property access inside methods (requires type inference)
- Indexed properties (`property Items[Index: Integer]: string read GetItem write SetItem;`)
- Default properties
- Property inheritance from parent classes

## Files to Modify

- `interpreter/frontends/pascal/node_types.py` — add node type constants
- `interpreter/frontends/pascal/declarations.py` — expand class body traversal, property parsing, synthetic method emission
- `interpreter/frontends/pascal/expressions.py` — wire dot access and assignment to use emit helpers
- `interpreter/frontends/pascal/frontend.py` — add `_pascal_var_types` init, add `declProp` to no-op dispatch if needed
- `tests/unit/test_pascal_frontend.py` — unit tests for IR emission
- `tests/integration/test_pascal_frontend_execution.py` — integration tests for property behavior (new file or append to existing)

## Testing

- Unit: `declProp` with `read FName` (field) emits synthetic `__get_Name__` with `LOAD_FIELD this "FName"`
- Unit: `declProp` with `write SetName` (method) emits synthetic `__set_Name__` with `CALL_METHOD this "SetName"`
- Unit: Class body traversal emits field initializers in synthetic `__init__`
- Unit: Methods inside class are lowered with `this` parameter
- Integration: Field-targeted read property — `foo.Name` returns backing field value
- Integration: Method-targeted write property — `foo.Name := value` calls setter procedure
- Integration: Read-only property (no write accessor) — `foo.Name` returns value
- Integration: Regression — class without properties still works
