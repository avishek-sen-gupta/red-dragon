# Rust Box Auto-Deref via `__method_missing__` Protocol

## Problem

`Box::new(x)` is currently a pass-through that returns `x` directly. This makes the Rosetta linked list work but breaks explicit deref (`*box_val`) and type identity — you can't distinguish a boxed value from an unboxed one. The Box prelude class is emitted but never instantiated.

## Goal

Make Box a real object with transparent auto-deref for field access and method calls, using a general-purpose `__method_missing__` VM protocol. Multi-level chaining (`Box<Box<T>>`) must work naturally.

## Design

### 1. New Opcode: `LOAD_FIELD_INDIRECT`

```
LOAD_FIELD_INDIRECT obj_reg name_reg → result_reg
```

Dynamic field access where the field name comes from a register at runtime, not a static string operand. This enables `__method_missing__` to delegate field access by name without knowing the name at compile time.

**Operand layout:** `operands[0]` is the object register (resolved via `_resolve_reg` to a heap address), `operands[1]` is the name register (resolved via `_resolve_reg` to a string). Both are register names, not literal values — unlike `LOAD_FIELD` where `operands[1]` is a static string.

Contrast with existing opcodes:
- `LOAD_FIELD obj "static_name"` — field name baked into instruction
- `LOAD_INDIRECT ptr` — pointer dereference through heap via `Pointer(base, offset)`
- `LOAD_FIELD_INDIRECT obj name_reg` — field name from register, on a regular object

### 2. VM `__method_missing__` Protocol

When `LOAD_FIELD` or `CALL_METHOD` fails to find the requested name on an object, the VM checks if the object has a `__method_missing__` field *before* falling through to symbolic materialization or `call_resolver`. This is critical: the existing `_handle_load_field` auto-materializes symbolic values for missing fields — `__method_missing__` must intercept before that point.

**Resolution order for `LOAD_FIELD`:**
1. Look up field on the object
2. If not found AND object has `__method_missing__`: call it with the field name, return result
3. If not found AND no `__method_missing__`: existing symbolic materialization (unchanged)

**Resolution order for `CALL_METHOD`:**
1. Look up method on the object (including parent chain walk for known types)
2. If not found after parent chain AND object has `__method_missing__`: call `__method_missing__(name, *args)` → return its result directly
3. If not found AND no `__method_missing__`: existing `call_resolver` chain (unchanged)

**Implementation note:** `_handle_call_method` has two distinct fallback sites: (a) unknown type (no `type_hint`) and (b) known type but method not found after parent chain walk. The `__method_missing__` check should be inserted at site (b) only — at site (a) there's no heap object to inspect. For Box, the type_hint will be "Box" (a registered class), so the check fires at site (b) after the parent chain walk fails to find the requested method.

The VM's role is the same for both opcodes: "I can't find this name, call `__method_missing__` instead, return whatever it returns." What `__method_missing__` does internally is its own business.

**Affected opcodes:** `LOAD_FIELD`, `CALL_METHOD`

**Not affected:** `BINOP`, `UNOP`, `STORE_FIELD`, `NEW_OBJECT`. In real Rust, auto-deref only applies to field reads and method calls, not operators. `Box<Int> + Box<Int>` requires explicit deref (`*a + *b`), which matches Rust semantics.

**Terminal behavior:** If `__method_missing__` itself returns a value whose field is also missing (and that value has no `__method_missing__`), the chain bottoms out in the standard symbolic fallback. This is the intended terminal behavior.

### 3. Box Prelude Class (Pure IR)

The existing Box prelude class in `_emit_box_class()` gains a `__method_missing__` method:

```python
class Box:
    def __init__(self, value):
        self.value = value

    def __method_missing__(self, name, *args):
        target = LOAD_FIELD_INDIRECT(self.value, name)
        if args:
            return CALL_UNKNOWN(target, *args)
        return target
```

For field access, `__method_missing__` loads the field from `self.value` by name and returns it. For method calls, it loads the method reference and calls it with the forwarded args. If `self.value` is also a Box, the inner `LOAD_FIELD_INDIRECT` triggers that Box's `__method_missing__`, and so on — multi-level chaining falls out naturally with no special cases.

### 4. `Box::new(x)` — Real Instantiation

Revert the pass-through. `Box::new(x)` emits `CALL_FUNCTION Box x`, creating a real Box object with `self.value = x`. The Box prelude class is already emitted; it just needs to be instantiated.

**Note:** `String::from(x)` currently shares the same `_lower_box_new` code path. It must be split out and remain a pass-through — `String::from` has nothing to do with Box.

### 5. `*box_val` — Explicit Deref

`*expr` on a Box lowers to `LOAD_FIELD "value"`, returning the inner value directly. This is the explicit unwrap — the user wrote `*` so they want the raw inner value.

Note: the current Rust frontend lowers `*expr` to `LOAD_INDIRECT`. Since frontend type tracking is out of scope, the frontend cannot distinguish `*box` from `*ptr` at lowering time. The simplest approach: always emit `LOAD_FIELD "value"` for Rust `*expr`. If the operand is a real C-style Pointer (not a Box), `LOAD_FIELD "value"` will trigger `__method_missing__` (which Pointer doesn't have) and fall through to symbolic — acceptable since Rust doesn't have raw C pointers. The existing `LOAD_INDIRECT` path is only used by the C frontend.

**DEFERRED:** If Rust raw pointers (`*const T`, `*mut T`) are added later, frontend type tracking will be needed to distinguish Box deref from pointer deref. For now, all Rust `*expr` emits `LOAD_FIELD "value"`.

### 6. Option Interaction

No changes to Option. `Some(Box::new(node)).unwrap()` returns a Box object. Subsequent field/method access on the result triggers `__method_missing__`, which delegates transparently:

```rust
let next = current.next.unwrap();  // returns Box<Node>
next.value    // __method_missing__ → LOAD_FIELD_INDIRECT(inner_node, "value")
next.next     // __method_missing__ → LOAD_FIELD_INDIRECT(inner_node, "next")
```

### 7. Generality

`__method_missing__` is a general-purpose protocol, not Box-specific. Any class can define it to intercept unresolved field/method access. Potential future uses: proxy objects, lazy loading, delegation patterns in other languages.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | New `LOAD_FIELD_INDIRECT` opcode | Enables dynamic field access by name. Reusing `LOAD_INDIRECT` would conflate pointer dereference with field lookup. |
| 2 | `__method_missing__` with no existence check | If absent, the call itself fails through existing symbolic fallback. Zero-cost for non-participating objects. |
| 3 | No BINOP auto-deref | Matches real Rust: operators don't auto-deref. `Box<Int> + Box<Int>` requires explicit `*`. |
| 4 | Box fully defined in IR | VM provides the hook (`__method_missing__` fallback + `LOAD_FIELD_INDIRECT`). All Box behavior lives in the Rust prelude IR. |
| 5 | `*expr` lowers to `LOAD_FIELD "value"` for Box | Explicit unwrap. Distinct from `LOAD_INDIRECT` which is for C-style pointer deref. |

## Scope

**In scope:**
- `LOAD_FIELD_INDIRECT` opcode + executor handler
- `__method_missing__` fallback in `_handle_load_field` and `_handle_call_method`
- Box prelude: add `__method_missing__`, revert `Box::new` pass-through
- `*expr` lowering change for Box deref
- Unit + integration tests

**Out of scope (by design — `__method_missing__` eliminates the need):**
- BINOP/UNOP auto-deref through Box (matches real Rust)
- Frontend type tracking / type parameter resolution (the original approach required knowing `Option<Box<Node>>.unwrap()` returns `Box<Node>` at lowering time — `__method_missing__` handles this at runtime instead)
- Other languages using `__method_missing__` (future work)

## Files to Modify

- `interpreter/ir.py` — add `LOAD_FIELD_INDIRECT` to `Opcode` enum
- `interpreter/executor.py` — add `_handle_load_field_indirect`, update `_handle_load_field` and `_handle_call_method` with `__method_missing__` fallback
- `interpreter/frontends/rust/declarations.py` — update `_emit_box_class()` with `__method_missing__`, update prelude emission
- `interpreter/frontends/rust/expressions.py` — revert `Box::new` pass-through to real `CALL_FUNCTION`, change `*expr` to `LOAD_FIELD "value"`
- `tests/unit/test_rust_box_option_lowering.py` — update for real Box instantiation
- `tests/unit/test_rust_prelude.py` — verify `__method_missing__` in Box class
- `tests/integration/` — new integration tests for Box delegation, multi-level, linked list

## Supersedes

- ADR-103 Decision 2 (Box::new pass-through) — replaced by real instantiation
- ADR-103 Decision 7 (`*box_expr` via LOAD_FIELD) — confirmed, but via `__method_missing__` protocol rather than frontend type tracking
