# Interprocedural Pointer Flow Analysis — Design Spec

**Date:** 2026-03-30
**Status:** Approved
**Issue:** red-dragon-ntnx
**Scope:** ~5 files, new endpoint type + summary/propagation extensions

## Problem

Interprocedural analysis produces 0 flows for C pointer-passing programs. The summary extractor only recognizes `STORE_FIELD`/`LOAD_FIELD` instructions, completely ignoring `STORE_INDIRECT`/`LOAD_INDIRECT` (pointer dereference writes/reads). Additionally, `ADDRESS_OF` is not handled in argument tracing during call-site propagation.

**Reproducer:**
```c
void set_val(int *p) { *p = 99; }
int main() { int x = 10; set_val(&x); return x; }
```

IR for `set_val`:
```
SYMBOLIC %0 param:p → DECL_VAR p, %0 → CONST %1, 99 → LOAD_VAR %2, p → STORE_INDIRECT %2, %1
```

IR for call site:
```
ADDRESS_OF %6, x → CALL_FUNCTION %7, set_val, %6
```

**Root causes:**
1. `_build_field_write_flows()` in `summaries.py` only scans for `StoreField`, ignoring `StoreIndirect`
2. `_build_return_flows()` in `summaries.py` doesn't recognize `LoadIndirect` as a value source
3. `_trace_reg_to_var()` in `propagation.py` only recognizes `LoadVar`/`DeclVar`/`StoreVar`, not `AddressOf`
4. `_substitute_endpoint()` in `propagation.py` has no case for dereference endpoints

## Design

### New Type: `DereferenceEndpoint`

Added to `interpreter/interprocedural/types.py`:

```python
@dataclass(frozen=True)
class DereferenceEndpoint:
    """A pointer dereference (*ptr) — read or write through a pointer variable."""
    base: VariableEndpoint
    location: InstructionLocation

FlowEndpoint = Union[VariableEndpoint, FieldEndpoint, ReturnEndpoint, DereferenceEndpoint]
```

### Summary Extraction: `STORE_INDIRECT`

New function `_build_deref_write_flows()` in `summaries.py`:

- Scan for `StoreIndirect` instructions
- For each, trace `ptr_reg` back to a named variable via `_find_register_source_var()`
- If the pointer variable is a param `p`:
  - Always emit: `VariableEndpoint(p) → DereferenceEndpoint(p)` (param controls deref write target)
  - If `value_reg` also traces to a param `q`: additionally emit `VariableEndpoint(q) → DereferenceEndpoint(p)` (param value flows through pointer)
- Called alongside `_build_field_write_flows()` in `build_summary()`

### Summary Extraction: `LOAD_INDIRECT`

Extend `_build_return_flows()` in `summaries.py`:

- When tracing a return operand backward, if it was produced by `LoadIndirect`:
  - Trace `LoadIndirect.ptr_reg` back to a param `p`
  - Emit: `DereferenceEndpoint(p) → ReturnEndpoint` (value at *p flows to return)

### Argument Tracing: `ADDRESS_OF`

Extend `_trace_reg_to_var()` in `propagation.py`:

- After existing `LoadVar` and `DeclVar`/`StoreVar` scans, add:
- If the register was produced by `AddressOf`, return `str(inst.var_name)`
- This maps `%6` (from `ADDRESS_OF x`) back to `"x"`

### Endpoint Substitution: `DereferenceEndpoint`

Extend `_substitute_endpoint()` in `propagation.py`:

```python
if isinstance(endpoint, DereferenceEndpoint):
    new_base = _substitute_endpoint(endpoint.base, param_to_actual, callee, call_site, cfg)
    assert isinstance(new_base, VariableEndpoint)
    # Dereferencing a pointer-to-x = accessing x itself
    return VariableEndpoint(name=new_base.name, definition=NO_DEFINITION)
```

Key insight: at the call site, `DereferenceEndpoint(p)` where `p` was passed as `&x` collapses to `VariableEndpoint(x)`. The dereference and the address-of cancel out.

### End-to-End Trace

For `void set_val(int *p) { *p = 99; }` called as `set_val(&x)`:

1. **Summary:** `VariableEndpoint("p") → DereferenceEndpoint(base=VariableEndpoint("p"))`
2. **Call site:** `p` maps to `%6`, `_trace_reg_to_var(%6)` finds `ADDRESS_OF x` → `"x"`
3. **Substitution:** Source `VariableEndpoint("p")` → `VariableEndpoint("x")`. Destination `DereferenceEndpoint(p)` → base becomes `VariableEndpoint("x")` → collapses to `VariableEndpoint("x")`
4. **Propagated flow:** `VariableEndpoint("x") → VariableEndpoint("x")` (x is modified through the call)
5. **Whole-program graph:** `x → x` self-edge indicating modification

### Files Touched

| File | Change |
|---|---|
| `interpreter/interprocedural/types.py` | Add `DereferenceEndpoint`, update `FlowEndpoint` union |
| `interpreter/interprocedural/summaries.py` | Add `_build_deref_write_flows()`, extend `_build_return_flows()` for `LoadIndirect`, import `StoreIndirect`/`LoadIndirect`/`AddressOf` |
| `interpreter/interprocedural/propagation.py` | Extend `_trace_reg_to_var()` for `AddressOf`, extend `_substitute_endpoint()` for `DereferenceEndpoint`, import `AddressOf`/`DereferenceEndpoint` |
| `tests/unit/test_interprocedural_types.py` | Unit tests for `DereferenceEndpoint` |
| `tests/unit/test_interprocedural_summaries.py` | Unit tests for `_build_deref_write_flows()` and LOAD_INDIRECT return flows |
| `tests/integration/test_interprocedural_integration.py` | C pointer-passing integration test |

## Non-Goals

- Multi-level pointers (`**p`)
- Pointer arithmetic (`p + offset`)
- Pointer aliasing analysis
- Changes to `queries.py` (works on graph structure, agnostic to endpoint types)
- Changes to `call_graph.py` (call resolution works correctly with `func_symbol_table`)
