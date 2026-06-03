# COBOL Program Singleton Design

**Date:** 2026-06-04
**Status:** Draft
**Related issues:** red-dragon-8rbw (WS persistence), red-dragon-8dpn (CANCEL follow-on)

## Problem

WORKING-STORAGE is not persistent across subprogram calls. Each call to a COBOL subprogram
re-executes `ALLOC_REGION` for WS, orphaning the previous region and losing all mutations.
The root cause: the WS region handle lives in the call frame, which is discarded on return.

## Design Goal

Model each COBOL program as a singleton class instance. WS fields are instance state on a
persistent heap object — exactly how GnuCOBOL treats WORKING-STORAGE as `static` locals
attached to each program's C function. LINKAGE and LOCAL-STORAGE semantics are unchanged.

The mechanism reuses existing general VM machinery (HeapObject, STORE_FIELD, LOAD_FIELD,
BoundFuncRef) with no COBOL-specific additions to the VM.

---

## Components

### 1. Bridge fix — emit `program_id`

`AsgSerializer.java` currently omits the PROGRAM-ID. Add:

```java
IdentificationDivision id = pu.getIdentificationDivision();
if (id != null && id.getProgramIdParagraph() != null) {
    asg.addProperty("program_id", id.getProgramIdParagraph().getName());
} else {
    asg.addProperty("program_id", cu.getName()); // fallback: filename stem
}
```

`cu.getName()` returns the filename stem (e.g. `"Subprog"` for `subprog.cbl`), not the
PROGRAM-ID. The `IdentificationDivision` path is authoritative.

### 2. `CobolASG` — add `program_id` field

```python
@dataclass(frozen=True)
class CobolASG:
    program_id: str = ""
    # ... existing fields unchanged
```

`from_dict()` reads `data.get("program_id", "")`.

### 3. Singleton HeapObject

Each COBOL program owns a `HeapObject` on the VM heap with two fields:

| Field         | Type          | Purpose                                      |
|---------------|---------------|----------------------------------------------|
| `ws_handle`   | `Address`     | Address of the persistent WS byte region     |
| `run`         | `BoundFuncRef`| Entry point for the procedure division       |

The singleton is stored in the bottom call frame via `STORE_VAR __prog_PROGRAMID` and is
findable from any frame via the existing scope chain walk. It is also accessible directly
from `vm._heap` at a well-known address derived from the program name, but scope chain
lookup is the standard path.

### 4. Uniform program lowering — every program lowers identically

`CobolFrontend.lower()` emits two sections for every program:

#### 4a. Init block (top-level, inside `entry:`)

Runs once — during the prologue before any procedure division executes.

```
; Inside entry: block
NEW_OBJECT   %ptr,    PROGRAMID
ALLOC_REGION %ws_reg, <ws_size>        ; with VALUE-clause byte initialisations
STORE_FIELD  %ptr,    ws_handle, %ws_reg
STORE_FIELD  %ptr,    run, BoundFuncRef(func_PROGRAMID_0)
STORE_VAR    __prog_PROGRAMID, %ptr
Branch       __after_PROGRAMID_0       ; skip over procedure body
```

#### 4b. Procedure division function (only reachable via dispatch)

```
func_PROGRAMID_0:
    LOAD_VAR   %singleton, __prog_PROGRAMID
    LOAD_FIELD %ws_reg,    %singleton, ws_handle
    STORE_VAR  __ws_region, %ws_reg            ; standard local var, unchanged downstream
    LOAD_VAR   %params_reg, __params_region    ; LINKAGE (injected by __init_params__)
    ... procedure division IR (unchanged) ...
    Return_

__after_PROGRAMID_0:
    ; empty — fall-through to next module's init or end
```

LOCAL-STORAGE still emits `ALLOC_REGION` on every call entry (per-call semantics unchanged).

### 5. `__init_params__` — LINKAGE setup

`_handle_call_with_memory` no longer injects magic vars. Instead it dispatches to an
`__init_params__` closure stored as a field on the singleton.

`__init_params__` accesses `self_ptr` via `LOAD_VAR __prog_PROGRAMID` scope chain lookup
at runtime (the init block runs in the bottom frame so the standard closure capture
mechanism does not fire; scope chain lookup reaches the bottom frame from any depth). It takes
`(params_region_addr, results_region_addr)` as arguments:

```
__init_params__(params_region_addr, results_region_addr):
    STORE_VAR __params_region,  params_region_addr   ; LINKAGE binding
    STORE_VAR __results_region, results_region_addr
    ; BY REFERENCE: done — callee aliases caller's region directly
    ; BY CONTENT:   ALLOC_REGION fresh region, copy bytes (future work)
    Branch func_PROGRAMID_0
```

The `run` and `__init_params__` fields are both stored on the singleton in the init block:

```
STORE_FIELD %ptr, run,             BoundFuncRef(func_PROGRAMID_0)
STORE_FIELD %ptr, __init_params__, BoundFuncRef(func_init_params_PROGRAMID_0)
```

### 6. `_handle_call_with_memory` changes

The handler becomes fully generic — no COBOL-specific knowledge:

1. Look up `VarName("__prog_" + program_id.upper())` in scope chain → `singleton_ptr`
2. `LOAD_FIELD __init_params__` from singleton → `BoundFuncRef` (closure)
3. Dispatch to it with `(params_region_addr, results_region_addr)` as arguments
4. `__init_params__` sets up `__params_region`/`__results_region` and jumps to
   `func_PROGRAMID_0`, which loads `ws_handle` and runs the procedure division

The previous scope-chain walk for `BoundFuncRef` by `func_name` is replaced by this
singleton lookup.

### 7. Linker — no changes required

The linker already strips `entry:` labels from dependency modules and keeps all other
instructions. The COBOL init block (emitted after `Label_("entry")`) survives the strip
intact and becomes top-level code that runs before the entry module — exactly the correct
behaviour.

Function bodies (`func_PROGRAMID_0:`) are separate CFG blocks only reachable via label
dispatch, so they do not execute inline.

### 8. Entry point for `run()`

`run()` is language-agnostic and unchanged. COBOL callers pass:

```python
EntryPoint.function(lambda f: str(f.name) == program_id)
```

`CobolFrontend` exposes `program_id` after `lower()` has been called. For single-file
execution, the caller passes the program_id from the compiled frontend.

---

## Data flow — end-to-end CALL example

```
Caller (MAIN):
    CALL 'SUBPROG' USING WS-PARAM
    → emits: CallWithMemory(func_name="SUBPROG", params_reg=%ws_reg, results_reg=%ws_reg)

_handle_call_with_memory:
    1. Look up __prog_SUBPROG → singleton HeapObject
    2. LOAD_FIELD __init_params__ → BoundFuncRef
    3. Dispatch with (params_region_addr, results_region_addr)

__init_params__ (closure):
    STORE_VAR __params_region, params_region_addr
    STORE_VAR __results_region, results_region_addr
    Branch func_SUBPROG_0

func_SUBPROG_0:
    LOAD_VAR   %singleton, __prog_SUBPROG
    LOAD_FIELD %ws_reg, %singleton, ws_handle   ← persistent WS, survives all calls
    STORE_VAR  __ws_region, %ws_reg
    ... procedure division accesses WS and LINKAGE normally ...
    Return_                                      ← frame pops, WS survives on heap
```

---

## REDEFINES compatibility

WS remains a flat byte region (`bytearray`). REDEFINES fields share the same byte offset
in the same region — unchanged. The singleton model adds persistence; it does not change
the region model.

---

## What does NOT change

- LOCAL-STORAGE: `ALLOC_REGION` per call (fresh per-call semantics preserved)
- LINKAGE field access: `READ_REGION`/`WRITE_REGION` at byte offsets (unchanged)
- All WS field access IR downstream of `STORE_VAR __ws_region` (unchanged)
- `run()` signature and implementation (unchanged)
- Linker (unchanged)
- VM opcodes (no new opcodes)

---

## Known limitations / follow-ons

- **CANCEL verb** (`red-dragon-8dpn`): `CANCEL 'SUBPROG'` must re-allocate the WS region
  and store the new handle into `singleton.ws_handle`. Requires a `reset` method on the
  singleton. Deferred.
- **BY CONTENT parameter passing**: `__init_params__` currently aliases the caller's region
  (BY REFERENCE semantics). BY CONTENT requires copying bytes into a fresh region. Deferred.
- **Cross-section MOVE (LS → WS)**: pre-existing gap, unrelated to this design.
