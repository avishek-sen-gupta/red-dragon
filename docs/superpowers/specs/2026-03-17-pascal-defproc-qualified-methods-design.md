# Pascal defProc Qualified Method Bodies Design

**Issue:** red-dragon-0b1
**Date:** 2026-03-17
**Status:** Approved

## Goal

Wire out-of-class Pascal method implementations (`procedure TFoo.SetName(...)`) back to their class so the VM dispatches them as class methods with `this` injection.

## Background

Pascal separates class declarations from method implementations. The class body contains forward declarations (stubs), and the actual method bodies are defined outside the class with qualified names:

```pascal
type
  TFoo = class
  private
    procedure SetName(const AValue: string);  { forward declaration }
  end;

procedure TFoo.SetName(const AValue: string);  { implementation }
begin
  self.FName := AValue;
end;
```

### Tree-sitter structure

The qualified `procedure TFoo.SetName(...)` parses as:

```
defProc
  declProc
    kProcedure
    genericDot              ← qualified name
      identifier "TFoo"    ← class name
      kDot
      identifier "SetName" ← method name
    declArgs
      ...
  block                    ← method body
    ...
```

The key difference from standalone procedures: the name is a `genericDot` node (two identifiers separated by a dot) instead of a plain `identifier`.

### Current behavior

`lower_pascal_proc` looks for a plain `identifier` child on the `declProc` node. When encountering `genericDot`, no `identifier` is found at the top level, so the function falls back to `__anon`. The method body is lowered as a standalone function with no `this` injection and the wrong name, making it unreachable from the class.

Meanwhile, `_lower_pascal_method` (called during class body traversal) creates a stub for `SetName` with `this` injection but an empty body (returns None immediately).

### Registry behavior (why the fix works)

The registry's `_scan_classes` keeps `in_class` set after encountering `end_class_X` labels. Any `CONST <func_label>` instruction emitted after the class body but before the next class is still registered as a method of the current class. Since `defProc` nodes appear after the class declaration in Pascal source, the correctly-named function reference will be picked up by the registry and overwrite the stub's label in `class_methods[TFoo][SetName]`.

## Design

### Node type constant

Add `GENERIC_DOT = "genericDot"` to `PascalNodeType`.

### Modify `lower_pascal_proc`

After finding `search_node` (the inner `declProc`), check for a `genericDot` child before looking for a plain `identifier`:

1. Look for `genericDot` child on `search_node`
2. If found, extract the two `identifier` children: first is `class_name`, second is `method_name`
3. Use `method_name` as `func_name` (not `TFoo.SetName`)
4. Set `is_qualified_method = True`

When `is_qualified_method` is True:
- Save/restore `ctx._current_class_name = class_name` around body lowering
- Emit `SYMBOLIC param:this` + `DECL_VAR this` before regular params
- Emit `DECL_VAR self` aliased to the same register as `this` — Pascal uses `self` (not `this`) to refer to the current instance in method bodies, so both names must resolve to the object

When `is_qualified_method` is False:
- Existing behavior unchanged

### No other file changes

The entire fix is contained in `lower_pascal_proc`. No VM changes, no registry changes, no changes to property accessor infrastructure.

## IR emission (after fix)

The `defProc` for `procedure TFoo.SetName(const AValue: string)` will emit:

```
BRANCH end_SetName
LABEL func_SetName
  SYMBOLIC param:this
  DECL_VAR this, %0
  DECL_VAR self, %0          ← alias so Pascal's `self` resolves
  SYMBOLIC param:AValue
  DECL_VAR AValue, %1
  LOAD_VAR AValue → %2
  LOAD_VAR self → %3         ← works because self is aliased to this
  STORE_FIELD %3, FName, %2
  CONST None → %4
  RETURN %4
LABEL end_SetName
CONST func_SetName → %5
DECL_VAR SetName, %5
```

Since this appears after `end_class_TFoo`, the registry picks up `func_SetName` as `class_methods["TFoo"]["SetName"]`, overwriting the stub.

## Scope

**In scope:**
- `GENERIC_DOT` node type constant
- `genericDot` detection in `lower_pascal_proc`
- `this` injection for qualified methods
- Class context (`_current_class_name`) around body lowering
- Unit and integration tests

**Out of scope:**
- Qualified function names that aren't class methods (e.g., `TFoo.TBar.Method` — nested classes)
- Constructor implementations (`constructor TFoo.Create`)

## Files to Modify

- `interpreter/frontends/pascal/node_types.py` — add `GENERIC_DOT`
- `interpreter/frontends/pascal/declarations.py` — modify `lower_pascal_proc`
- `tests/unit/test_pascal_frontend.py` — unit test for qualified defProc lowering
- `tests/integration/test_pascal_frontend_execution.py` — remove xfail from method-write test

## Testing

- Unit: `defProc` with `genericDot` emits `SYMBOLIC param:this`, uses correct method name, has correct body
- Integration: Remove xfail from `test_method_write_property_calls_setter_procedure` — `foo.Name := 'Charlie'` calls `SetName` which stores to `self.FName`
