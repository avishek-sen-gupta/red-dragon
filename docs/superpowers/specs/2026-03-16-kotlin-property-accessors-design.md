# Kotlin Property Getters/Setters Design

**Issue:** red-dragon-3l0
**Date:** 2026-03-16
**Status:** Approved

## Goal

Support Kotlin custom property accessors (`get() = ...`, `set(value) { ... }`) so that reading/writing a property calls the getter/setter instead of raw field access. Build a common property-accessor layer reusable by other frontends (C#, JS/TS, Scala).

## Background

Kotlin properties can have custom accessors:

```kotlin
class Foo {
    var x: Int = 0
        get() = field + 1
        set(value) { field = value * 2 }
}
```

The `field` keyword refers to the backing field. After `foo.x = 5`, the backing field holds 10 (doubled by setter), and reading `foo.x` returns 11 (backing field + 1).

Currently, `getter` and `setter` nodes are dispatched as no-ops (`lambda ctx, node: None`) in `frontend.py` lines 116-117. Properties work as plain fields only.

### Tree-sitter structure

Verified by parsing actual Kotlin with tree-sitter. `getter` and `setter` are **siblings** of `property_declaration` in `class_body`, not nested inside it:

```
class_body
  property_declaration        ← var x: Int = 0
    binding_pattern_kind "var"
    variable_declaration
    integer_literal "0"
  getter                      ← sibling, not child
    function_body
      additive_expression     ← field + 1
  setter                      ← sibling, not child
    parameter_with_optional_type
      simple_identifier "value"
    function_body
      statements
        assignment            ← field = value * 2
```

## Design

### No backing field rename

The property field keeps its original name (`x`, not `__x`). Recursion is avoided because:
- Inside getter/setter bodies, `field` emits raw `LOAD_FIELD this "x"` / `STORE_FIELD this "x"` — these are direct IR emissions, not navigation expressions, so they bypass the accessor interception.
- `lower_navigation_expr` only intercepts `this.x` navigation expressions by checking `ctx.property_accessors`. Raw `LOAD_FIELD`/`STORE_FIELD` emitted by the `field` keyword handler never passes through `lower_navigation_expr`.
- External access (`foo.x`) also emits plain `LOAD_FIELD`/`STORE_FIELD` which reads/writes the field directly — correct behavior for external callers.

### Common property-accessor infrastructure

**New file:** `interpreter/frontends/common/property_accessors.py`

**Registration:**

`register_property_accessor(ctx, class_name, prop_name, kind)` — records that property `prop_name` on class `class_name` has a custom `"get"` or `"set"` accessor. Stored in `ctx.property_accessors: dict[str, dict[str, set[str]]]` mapping `class_name → {prop_name → {"get", "set"}}`.

The `property_accessors` dict is added to `TreeSitterEmitContext` in `context.py`.

**Emit helpers:**

- `emit_field_load_or_getter(ctx, obj_reg, class_name, field_name, node) → str` — if `field_name` has a registered getter on `class_name`, emits `CALL_METHOD obj "__get_<field_name>__"` and returns the result register. Otherwise emits plain `LOAD_FIELD obj field_name`.
- `emit_field_store_or_setter(ctx, obj_reg, class_name, field_name, val_reg, node)` — if `field_name` has a registered setter on `class_name`, emits `CALL_METHOD obj "__set_<field_name>__" val`. Otherwise emits plain `STORE_FIELD obj field_name val`.

**Naming convention:**
- Getter method: `__get_<prop>__`
- Setter method: `__set_<prop>__`

### Kotlin-specific changes

**`_lower_class_body_with_companions`** (in `declarations.py`): When iterating `class_body` children, track the most recent `property_declaration`'s name. When a `getter` or `setter` node follows, associate it with that property name and emit the synthetic method. This is done in `_lower_class_body_with_companions` itself, not in `_collect_kotlin_field_init`.

For each getter:
- Emit as a synthetic method `__get_<prop>__` with `this` injected, using existing LABEL + BRANCH + RETURN pattern (same as `lower_function_decl`).
- Inside the getter body, the `field` identifier resolves to `LOAD_FIELD this "<prop>"` (raw emit, no navigation expression).
- Register the accessor via `register_property_accessor(ctx, class_name, prop_name, "get")`.

For each setter:
- Emit as a synthetic method `__set_<prop>__` with parameters `this` and `value`.
- Inside the setter body, `field` on the LHS resolves to `STORE_FIELD this "<prop>"` (raw emit).
- Register the accessor via `register_property_accessor(ctx, class_name, prop_name, "set")`.

**`field` keyword**: During lowering of getter/setter bodies, `field` is intercepted as a special identifier. In read position, it emits `LOAD_FIELD this "<prop>"`. In write position (assignment target), it emits `STORE_FIELD this "<prop>" val`. This is done by temporarily setting a context variable (e.g., `ctx._accessor_backing_field = "x"`) that the identifier and assignment lowering checks.

**`lower_navigation_expr`**: Calls `emit_field_load_or_getter` instead of emitting `LOAD_FIELD` directly. Requires knowing the class name of the object — use `ctx._current_class_name` when the object is `this`, otherwise fall back to plain `LOAD_FIELD` (class-agnostic access cannot resolve accessors at compile time without type inference).

**Assignment handler** (in the `NAVIGATION_EXPRESSION` branch of `_lower_assignment_target`): Calls `emit_field_store_or_setter` instead of emitting `STORE_FIELD` directly, with the same `this`-only scope.

### Scope limitation

Accessor interception works when the object is `this` (i.e., `this.x` or bare `x` within the class). External access (`foo.x` where `foo` is a variable) reads/writes the field directly — which is correct since the field keeps its original name. Full accessor interception for external access requires type inference and is out of scope.

### No VM changes

The entire feature is frontend-only. Synthetic methods use existing LABEL/BRANCH/RETURN function infrastructure and `CALL_METHOD`. Field access uses existing `LOAD_FIELD`/`STORE_FIELD`.

## IR emission example

```kotlin
class Foo {
    var x: Int = 0
        get() = field + 1
        set(value) { field = value * 2 }
}
```

IR for class body (pseudo-IR, actual uses LABEL/BRANCH pattern):
```
# Synthetic __init__ stores field x
BRANCH end___init__
LABEL __init__
  CONST 0 → %0
  STORE_FIELD this, "x", %0
  RETURN
LABEL end___init__

# Getter method
BRANCH end___get_x__
LABEL __get_x__
  LOAD_FIELD this, "x" → %0       ← raw emit from 'field' keyword
  CONST 1 → %1
  ADD %0, %1 → %2
  RETURN %2
LABEL end___get_x__

# Setter method
BRANCH end___set_x__
LABEL __set_x__
  LOAD_VAR value → %0
  CONST 2 → %1
  MUL %0, %1 → %2
  STORE_FIELD this, "x", %2       ← raw emit from 'field' keyword
  RETURN
LABEL end___set_x__
```

Internal usage (`this.x` in another method):
```
# this.x read → intercepted, calls getter
CALL_METHOD this, "__get_x__" → %0

# this.x = 5 → intercepted, calls setter
CONST 5 → %0
CALL_METHOD this, "__set_x__", %0
```

External usage (`foo.x`):
```
# foo.x read → plain LOAD_FIELD (no interception, reads field directly)
LOAD_FIELD foo, "x" → %0

# foo.x = 5 → plain STORE_FIELD (no interception, writes field directly)
CONST 5 → %0
STORE_FIELD foo, "x", %0
```

## Scope

**In scope:**
- Common property-accessor registration and emit helpers
- Kotlin `getter`/`setter` lowering as synthetic methods
- `field` keyword handling in accessor bodies
- Internal (`this`-scoped) accessor interception
- Unit and integration tests

**Out of scope:**
- External accessor interception (requires type inference)
- Other frontends adopting the common layer (separate issues)
- Computed properties without backing fields

## Files to Modify

- `interpreter/frontends/common/property_accessors.py` — new file: registration + emit helpers
- `interpreter/frontends/context.py` — add `property_accessors` dict to `TreeSitterEmitContext`
- `interpreter/frontends/kotlin/declarations.py` — parse getter/setter siblings, emit synthetic methods
- `interpreter/frontends/kotlin/expressions.py` — wire `lower_navigation_expr` and assignment handler to use emit helpers; handle `field` keyword
- `interpreter/frontends/kotlin/frontend.py` — update getter/setter dispatch from no-op
- `tests/unit/test_kotlin_frontend.py` — unit tests for IR emission
- `tests/integration/test_kotlin_frontend_execution.py` — integration tests for accessor behavior

## Testing

- Unit: `var x` with `get()` emits getter method label with `LOAD_FIELD this "x"`
- Unit: `var x` with `set(value)` emits setter method label with `STORE_FIELD this "x"`
- Unit: `this.x` read in a class with custom getter emits `CALL_METHOD` not `LOAD_FIELD`
- Integration: `get() = field + 1` — reading property within class returns transformed value
- Integration: `set(value) { field = value * 2 }` — writing property within class stores transformed value
- Integration: Getter and setter together — write then read shows both transformations
- Integration: Regression — property without accessors still works as plain field
