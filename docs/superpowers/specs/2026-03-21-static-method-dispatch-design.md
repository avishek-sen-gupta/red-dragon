# Static Method Dispatch — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** `Class.method()` static method calls return symbolic — fix via ClassRef check in `_handle_call_method`
**Issue:** red-dragon-ww3j

## Problem

`Math.square(5)` returns symbolic across Java, C#, C++. `CALL_METHOD` receives a `ClassRef` as the object but doesn't recognize it — falls through to the unresolved call resolver.

## Design

Add a `ClassRef` check early in `_handle_call_method` (after `BoundFuncRef`, before method builtins). When `obj_val.value` is a `ClassRef`, look up `method_name` in `registry.class_methods[class_name]` and dispatch via `_try_user_function_call`. No `self`/`this` injection — static methods don't receive an instance.

### Files Changed

- `interpreter/executor.py` — add ClassRef block in `_handle_call_method`

## Testing

- `test_java_static_method` — `Math.square(5)` → `25`
- `test_csharp_static_method` — `Util.Square(5)` → `25`
- `test_cpp_static_method` — `Util::square(5)` → `25`
- `test_static_method_with_multiple_args` — `Math.add(3, 4)` → `7`
