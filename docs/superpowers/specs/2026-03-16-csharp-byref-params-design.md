# C# out/ref/in Parameter Pass-by-Reference Design

**Issue:** red-dragon-ia8
**Date:** 2026-03-16
**Status:** Approved

## Goal

Support C# `out`, `ref`, and `in` parameter modifiers with true pass-by-reference semantics. Callee assignments to `out`/`ref` parameters must propagate back to the caller.

## Approach

Frontend-emitted dereferences, mirroring CLR IL (`ldarga`/`ldind`/`stind`). Zero VM changes. Reuses existing ADR-099 infrastructure: `ADDRESS_OF` opcode, `Pointer` type, `LOAD_FIELD`/`STORE_FIELD` with `"*"` dereference convention.

## Design

### Call Site

When an `argument` node has an `out`, `ref`, or `in` keyword child:

**`out int result`** (declaration_expression):
```
%0 = const 0
decl_var result %0       # declare with default
%1 = address_of result   # promote to heap, get Pointer
call_method obj TryParse %1
```

**`out result`** (existing variable, no declaration):
```
%0 = address_of result   # promote existing var, get Pointer
call_method obj TryParse %0
```

**`ref x`** (existing variable):
```
%0 = address_of x        # promote existing var, get Pointer
call_method obj Swap %0
```

**`in x`** — identical to `ref x`. Read-only enforcement is a compile-time concern, not ours.

**Where the changes live:**

- `lower_declaration_expression` in `csharp/expressions.py`: emits `ADDRESS_OF` instead of `LOAD_VAR` for `out Type name`.
- **C#-specific argument unwrapper** `extract_csharp_call_args` in `csharp/expressions.py`: wraps the common `extract_call_args_unwrap`, adding handling for `out`/`ref`/`in` keyword children on argument nodes. When detected, emits `ADDRESS_OF` on the inner identifier instead of `ctx.lower_expr`. This avoids modifying the shared common function used by all 15 frontends.
- All C# call sites (`lower_invocation`, `lower_object_creation`) switch to using `extract_csharp_call_args`.

### Callee Parameter Detection

`lower_csharp_params` detects `out`/`ref`/`in` modifier on parameter nodes and records the param name in `ctx.byref_params: set[str]`.

```python
modifier = next(
    (c for c in child.children if c.type == NT.MODIFIER
     and ctx.node_text(c) in ("out", "ref", "in")),
    None,
)
if modifier:
    ctx.byref_params.add(pname)
```

**Lifecycle:** `ctx.byref_params` is cleared at the top of `lower_csharp_params` before processing the parameter list. This means each function gets a fresh set. Nested lambdas/local functions call `lower_csharp_params` for their own parameter list, which clears and repopulates the set — so a lambda inside a method with byref params does NOT inherit the outer method's byref set.

### Callee Body — Intercepting Reads and Writes

Inside a method body, reads/writes of byref params emit dereference instructions.

**Write** — `result = 42` where `result` is `out`/`ref`:
```
%0 = const 42
%1 = load_var result       # load the Pointer
store_field %1 "*" %0      # write through it
```

**Read** — `return result` where `result` is `ref`/`in`:
```
%0 = load_var result       # load the Pointer
%1 = load_field %0 "*"    # dereference
return %1
```

**Implementation:** Two helper functions in `csharp/expressions.py`:

- `emit_byref_load(ctx, name)` — if `name in ctx.byref_params`, emit `LOAD_VAR` + `LOAD_FIELD "*"`, else emit plain `LOAD_VAR`.
- `emit_byref_store(ctx, name, val_reg)` — if `name in ctx.byref_params`, emit `LOAD_VAR` + `STORE_FIELD "*"`, else emit plain `STORE_VAR`.

**Intercept points:**

- **Reads**: Register a C#-specific identifier handler `lower_csharp_identifier` in the C# expr_dispatch table (replacing the common `lower_identifier` for `IDENTIFIER` nodes). This calls `emit_byref_load` for byref params, falls through to regular `LOAD_VAR` otherwise.
- **Writes**: `lower_csharp_store_target` already handles C# assignment targets — modify its `IDENTIFIER` branch to call `emit_byref_store` instead of emitting raw `STORE_VAR`.

**Byref param as method receiver:** `result.ToString()` where `result` is a byref param — the C# identifier handler dereferences it (producing the inner value), which is then used as the receiver for `CALL_METHOD`. This works naturally via `emit_byref_load`.

**Passing byref param to another call:** `Foo(result)` — the identifier handler dereferences, passing the inner value. If the callee also takes `ref`, the caller writes `Foo(ref result)`, which hits the `ref` argument path and passes the Pointer through without dereferencing.

## Scope

**In scope:**
- C# `out`, `ref`, `in` parameter modifiers in method signatures and call sites
- Both `out Type name` (declaration) and `out name` (existing variable) forms
- Frontend-only changes: C#-specific argument unwrapper, `lower_csharp_params`, `lower_csharp_identifier`, `lower_csharp_store_target`
- `byref_params` set on `TreeSitterEmitContext`, cleared per function in `lower_csharp_params`
- Reuse `ADDRESS_OF`, `Pointer`, `LOAD_FIELD "*"`, `STORE_FIELD "*"`

**Out of scope:**
- Other languages (C++ `&` refs, PHP `&$param`, Pascal `var` params) — separate issues
- `LOAD_INDIRECT`/`STORE_INDIRECT` opcodes — red-dragon-aiu
- `ref return` / `ref local` (C# 7.0) — red-dragon-4cn
- Runtime enforcement of `in` read-only semantics

## Testing

**Existing xfail tests to pass:** All 4 in `TestCSharpOutVarExecution` tagged `red-dragon-ia8`:
- `test_try_parse_pattern_out_int` — callee assigns `result = 42`, caller reads 42
- `test_try_parse_pattern_out_var` — callee assigns `result = 100`, caller reads 100
- `test_multiple_out_params` — callee assigns `tax` and `total`, caller reads both
- `test_out_var_used_in_if_condition` — callee assigns `value = 99`, caller uses in if body

**New tests needed:**
- Unit tests: IR output for `out`/`ref`/`in` params (verify ADDRESS_OF, LOAD_FIELD "*", STORE_FIELD "*" emitted)
- Integration tests: `ref` parameter (swap pattern), `in` parameter (read-only pass)
- Integration test: mixed regular + out + ref params in same method
- Integration test: `out existingVar` (no declaration_expression)
- Integration test: byref param used as method receiver (`outParam.ToString()`)
- Integration test: byref param re-assigned multiple times in callee

## Files to Modify

- `interpreter/frontends/csharp/expressions.py` — `lower_declaration_expression`, `extract_csharp_call_args`, `lower_csharp_identifier`, `emit_byref_load`, `emit_byref_store`, `lower_csharp_store_target`
- `interpreter/frontends/csharp/frontend.py` — register `lower_csharp_identifier` in expr_dispatch, switch call sites to `extract_csharp_call_args`
- `interpreter/frontends/csharp/node_types.py` — add constants if needed (MODIFIER already exists)
- `interpreter/frontends/context.py` — add `byref_params: set[str]` to `TreeSitterEmitContext`
- `tests/unit/test_csharp_frontend.py` — unit tests for IR output
- `tests/integration/test_csharp_frontend_execution.py` — remove xfail, add ref/in/edge-case tests
