# Pointer Migration: Heap References from Bare Strings to Pointer Objects

## Problem

Heap object references are bare strings (`"obj_0"`, `"arr_0"`) wrapped in `TypedValue` with `UNKNOWN` type. This loses type information — a variable holding a `Point` struct shows up as `String` in the type system. It also forces downstream code to use string prefix patterns (`startswith("obj_")`) to deduce what a value represents, which is fragile and violates the principle established by the `FuncRef`/`ClassRef` migration.

## Design Principle

**Do not encode information in string representations.** Use typed objects (`Pointer`, `FuncRef`, `ClassRef`, etc.) to carry structured data. Never use string prefixes, patterns, or regex to deduce what a value represents — use `isinstance` checks on the actual type.

This migration eliminates the last major stringly-typed representation in the system.

## Solution

Wrap all heap addresses in `Pointer(base=addr, offset=0)` at creation time, paired with the correct parameterized type `pointer(scalar(type_hint))` on the `TypedValue`. The `Pointer` dataclass (in `vm_types.py`) stays unchanged — `(base: str, offset: int)`. The inner type lives on `TypedValue.type` where it belongs.

### Before

```python
# NEW_OBJECT
typed(addr, UNKNOWN)  # addr = "obj_0", type = UNKNOWN
```

### After

```python
# NEW_OBJECT
typed(Pointer(base=addr, offset=0), pointer(scalar(type_hint)))
```

## Approach: Bottom-Up Incremental

### Step 1: Prepare consumers (zero behavior change)

- Update `_heap_addr()` in `vm.py` to handle `Pointer` objects: add `isinstance(val, Pointer): return val.base` before the existing `isinstance(val, str)` check. All 14 executor callsites and 4 builtin callsites become Pointer-ready.
- `typed_from_runtime()` stays unchanged — a bare `Pointer` reaching it is a bug, not a fallback case.

### Step 1b: Unify Pointer early-return branches in LOAD_FIELD and STORE_FIELD

`_handle_load_field` and `_handle_store_field` have `isinstance(obj_val, Pointer)` early-return branches (originally for C/Rust explicit pointer deref) that are simpler than the main `_heap_addr()` paths. Post-migration, ALL heap objects are Pointers, so these early-return branches become the only path — but they're missing features:

- **`_handle_load_field`** (line 629): Pointer branch returns field value or symbolic. It does NOT check `__method_missing__`, does NOT trigger Box delegation via `_resolve_method_delegation_target`, and does NOT cache symbolic values in `heap_obj.fields`. After migration, Box auto-deref and method chaining would break.
- **`_handle_store_field`** (line 517): Pointer branch writes the field directly. It does NOT materialise synthetic heap entries for unknown addresses (lines 532-535). After migration, field stores on symbolic objects would silently fail.

**Fix:** Eliminate the Pointer-vs-string split. Both handlers should extract the address via `_heap_addr()` and follow a single unified path. The `isinstance(obj_val, Pointer)` early-return branches become dead code once `_heap_addr()` handles Pointer — delete them. The "Pointer not on heap" branch (line 640) is subsumed by the "addr not in heap" path (line 649-653).

### Step 1c: Replace `field_fallback.py`'s private `_heap_addr()` with shared one

`field_fallback.py` has its own `_heap_addr()` that only accepts `obj_`-prefixed strings. Replace with the shared `vm._heap_addr()`. This is a semantic change: the shared function accepts any string (including `arr_` prefixes). Sequence this after Step 3 (NEW_ARRAY conversion) to avoid false-positive field resolution on arrays during the transition. Alternatively, verify no test relies on `field_fallback` rejecting array addresses.

### Step 2: Convert `NEW_OBJECT`

Change `_handle_new_object` to produce `typed(Pointer(base=addr, offset=0), pointer(scalar(type_hint or "Object")))`. Fix any tests that assert on bare string addresses (e.g., `.startswith("obj_")`).

### Step 3: Convert `NEW_ARRAY`

Same pattern: `typed(Pointer(base=addr, offset=0), pointer(scalar(type_hint or "Array")))`. Fix breaking tests.

### Step 4: Convert builtins

`_builtin_array_of` and `_builtin_object_rest` wrap their addresses in `Pointer` with `pointer(scalar("Array"))`.

### Step 5: Convert `_try_class_constructor_call`

`_try_class_constructor_call` (executor.py ~line 1229) has four bare-address writes that all need conversion:

1. `register_writes` for `result_reg` in the no-init path (~line 1270)
2. `new_vars[params[0]]` for explicit `self`/`this` binding (~line 1282)
3. `new_vars[constants.PARAM_THIS]` for implicit `this` binding (~line 1288)
4. `register_writes` for `result_reg` in the with-init path (~line 1295)

All four must use `Pointer`. The `this`/`self` binding is critical: if `result_reg` is Pointer but `this` is a bare string, the constructor body sees a bare string while the caller sees a Pointer — breaking field fallback resolution.

### Step 6: Delete dead BINOP string-synthesis code

The BINOP handler has branches that synthesize `Pointer(base=lhs, offset=0)` from bare string addresses for pointer arithmetic. After migration, values are already Pointers — these branches are dead code. Delete them.

### Step 7: Update CLAUDE.md

Add the "no stringly-typed information" principle to the Programming Patterns section.

## What stays the same

- **`Pointer` dataclass** — `(base: str, offset: int)`, no new fields.
- **`_heap_addr()` function** — retained as the canonical address-extraction shim, updated to handle Pointer.
- **`typed_from_runtime()`** — unchanged. Pointers should never reach it bare; if they do, `UNKNOWN` is returned (surfacing as a test failure).
- **Existing `isinstance(val, Pointer)` checks in BINOP, STORE_INDIRECT, LOAD_INDIRECT** — these already work correctly with Pointer objects.
- **`LOAD_INDEX` native string indexing** — strings in registers are genuinely string values post-migration, not heap addresses. No change needed.
- **`_builtin_slice` string fallback** — same reasoning. No change.

## Bare strings vs. Pointers: where each is used

**Bare strings remain as heap dict keys and in StateUpdate address fields.** `vm.heap[addr]`, `NewObject(addr=addr)`, and `HeapWrite(obj_addr=addr)` all use the bare string address (e.g. `"obj_0"`). These are dict keys and internal plumbing — they never carry type information.

**Pointers wrap addresses in registers, variables, and local vars.** `register_writes`, `var_writes`, and `new_vars` entries use `typed(Pointer(base=addr, offset=0), pointer(scalar(type_hint)))`. These are the values that flow through the program and carry type information.

The bare string `addr` is always `Pointer.base` — the same value, just unwrapped for use as a dict key.

## Key decisions

1. **`_heap_addr()` kept as shim** — 14+ callsites is too much churn to eliminate. Updated to unwrap `Pointer.base`.
2. **`field_fallback.py` uses shared `_heap_addr()`** — eliminates its private string-prefix-based implementation.
3. **No `inner_type` field on Pointer** — the inner type lives on `TypedValue.type` as `pointer(scalar(...))`. No duplication.
4. **`typed_from_runtime` not updated for Pointer** — bare Pointers reaching it are bugs. `UNKNOWN` return surfaces them via test failures.
5. **BINOP dead code deleted** — string-to-Pointer synthesis branches become unreachable.

## Beads issue

`red-dragon-lr9y`
