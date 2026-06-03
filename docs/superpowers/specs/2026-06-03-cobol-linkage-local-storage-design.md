# COBOL LINKAGE SECTION & LOCAL-STORAGE SECTION — Design Spec

**Date:** 2026-06-03
**Status:** Approved for implementation

---

## Overview

This spec covers full support for COBOL's LINKAGE SECTION and LOCAL-STORAGE SECTION in the RedDragon frontend and VM. The Java bridge serialisation layer is already complete (merged). This spec covers everything from the bridge JSON into the VM.

---

## Background & Constraints

- The Java bridge now emits `linkage_fields` and `local_storage_fields` as separate top-level keys alongside `data_fields` in the ASG JSON.
- `CobolASG` already deserialises these into `linkage_fields` and `local_storage_fields` lists.
- All COBOL-to-COBOL calls are assumed to be linked — the callee IR is always present. There is no fallback to opaque `CallFunction` for COBOL subprograms.
- All section disambiguation, BY REF/CONTENT/VALUE semantics, and field resolution logic lives at **lowering time**. The VM is completely generic — it has no knowledge of COBOL sections, PIC clauses, or LINKAGE semantics.

---

## What LINKAGE and LOCAL-STORAGE Mean

**LINKAGE SECTION** — declares the parameters received by a subprogram via `CALL … USING`. Fields here are not allocated by the callee; they reference memory owned by the caller. The callee reads/writes them directly in the caller's region (BY REFERENCE), or receives copies (BY CONTENT / BY VALUE).

**LOCAL-STORAGE SECTION** — per-call private scratch space. Allocated fresh and initialised from VALUE clauses on every call. Safe for recursion; no state leaks between calls. Equivalent to stack-local variables.

**WORKING-STORAGE SECTION** — persists across calls (existing behaviour unchanged). See Known Limitations.

---

## New IR Instruction: `CallWithMemory`

A new generic IR instruction added to `interpreter/instructions.py`, registered in `interpreter/ir.py` as `Opcode.CALL_WITH_MEMORY`.

```python
@dataclass(frozen=True)
class CallWithMemory(InstructionBase):
    """Call a subprogram passing two memory regions."""
    func_name: FuncName = NO_FUNC_NAME
    params_reg: Register = NO_REGISTER   # callee reads input params from here
    results_reg: Register = NO_REGISTER  # callee writes results back here
    result_reg: Register = NO_REGISTER   # scalar return value (for GIVING)
```

**Lowering rules:**
- BY REFERENCE (default): `params_reg == results_reg` — caller's own region register
- BY CONTENT / BY VALUE: `params_reg` is a fresh copy region; `results_reg` is caller's region
- Mixed USING lists: lowerer assembles a fresh params region containing copies of BY CONTENT/VALUE fields, passes caller's region as `results_reg`
- GIVING: post-call encode-and-write of `result_reg` into the caller's GIVING field (same as today)

**VM handler** (`interpreter/handlers/calls.py` → registered in `executor.py`):
- Looks up the callee IR label via `func_name` (scope chain, same as `_handle_call_function`)
- Pushes a new call frame via `StackFramePush`
- Injects `__params_region` and `__results_region` as `var_writes` into the new frame
- Sets `next_label` to the callee's entry label

The handler is fully generic — no COBOL knowledge.

---

## New File: `interpreter/cobol/sectioned_layout.py`

Contains two dataclasses:

### `SectionedLayout`
Pure data, built from `CobolASG` before any IR emission.

```python
@dataclass(frozen=True)
class SectionedLayout:
    working_storage: DataLayout
    linkage: DataLayout
    local_storage: DataLayout
```

Built by a new `build_sectioned_layout(asg: CobolASG) -> SectionedLayout` function that calls `build_data_layout` for each section.

### `MaterialisedSectionedLayout`
Built once all three region registers are known (after allocation). Owns field resolution.

```python
@dataclass(frozen=True)
class MaterialisedSectionedLayout:
    working_storage: tuple[DataLayout, Register]
    linkage: tuple[DataLayout, Register]
    local_storage: tuple[DataLayout, Register]

    def resolve(self, name: str) -> tuple[FieldLayout, Register]: ...
    def has_field(self, name: str) -> bool: ...
```

**Resolution precedence:** LOCAL-STORAGE wins over WORKING-STORAGE on name collision. A warning is emitted for any collision; no error. LINKAGE fields are resolved separately (only when the callee is resolving its own parameters).

---

## Updated: `lower_data_division.py`

New function alongside the existing `lower_data_division`:

```python
def lower_sectioned_data_division(
    ctx: EmitContext,
    layout: SectionedLayout,
) -> MaterialisedSectionedLayout:
```

- Allocates WORKING-STORAGE region normally (AllocRegion + VALUE initialisers)
- Allocates LOCAL-STORAGE region fresh (AllocRegion + VALUE initialisers) — fresh on every call because this runs at the callee's entry label
- For LINKAGE: no allocation — emits `LoadVar(__params_region)` to retrieve the region register injected by the caller's `CallWithMemory` handler
- Returns `MaterialisedSectionedLayout` with all three `(DataLayout, Register)` pairs

---

## Updated: `cobol_frontend.py`

The `lower()` method changes from:

```python
layout = build_data_layout(asg.data_fields)
region_reg = lower_data_division(ctx, layout)
lower_procedure_division(ctx, asg, layout, region_reg)
```

To:

```python
sectioned = build_sectioned_layout(asg)
materialised = lower_sectioned_data_division(ctx, sectioned)
lower_procedure_division(ctx, asg, materialised)
```

For a top-level program (not a subprogram), the LINKAGE section is empty — `lower_sectioned_data_division` will emit `LoadVar(__params_region)` only if `layout.linkage` is non-empty, so top-level programs are unaffected.

---

## Updated: `lower_call.py`

`lower_call` emits `CallWithMemory` instead of `CallFunction` for COBOL subprogram calls:

1. For each `CallUsingParam`:
   - BY REFERENCE: use caller's `materialised.working_storage[1]` (region reg) directly
   - BY CONTENT / BY VALUE: emit a region copy
2. Emit `CallWithMemory(func_name, params_reg, results_reg, result_reg)`
3. Post-call: if `stmt.giving`, encode-and-write `result_reg` into the GIVING field in `results_reg`

---

## Updated: All `lower_*` Functions

All COBOL lowering functions currently taking `layout: DataLayout, region_reg: str` are updated to take `layout: MaterialisedSectionedLayout` instead (dropping `region_reg` as a separate parameter). `EmitContext.resolve_field_ref` and `EmitContext.has_field` are updated to take `MaterialisedSectionedLayout`.

The `DispatchFn` type alias updates accordingly:
```python
DispatchFn = Callable[["EmitContext", Any, MaterialisedSectionedLayout], None]
```

---

## `str → Register` Migration

All `region_reg: str` annotations throughout `interpreter/cobol/` are replaced with `Register`. Affects 16 files. Done as a **separate commit** on the same branch before the structural changes, to keep the diff reviewable.

---

## Callee Entry Sequence

When a COBOL subprogram is called via `CallWithMemory`, its entry label executes:

1. `LoadVar(__params_region)` → binds the passed region register
2. `LoadVar(__results_region)` → binds the results region register  
3. `AllocRegion` for WORKING-STORAGE (+ VALUE initialisers)
4. `AllocRegion` for LOCAL-STORAGE (+ VALUE initialisers) — fresh each call
5. LINKAGE fields bound to `__params_region` offsets (no allocation)
6. PROCEDURE DIVISION body executes normally, field resolution via `MaterialisedSectionedLayout`

---

## Feature Audit Updates

- `SECTION_LINKAGE`: promoted from `NOT_EXTRACTED` to handled in `scripts/audit_cobol_frontend.py`
- `SECTION_LOCAL_STORAGE`: same
- Both features get `@covers` decorators on their integration tests

---

## Testing

**Unit tests:**
- `test_sectioned_layout.py`: `SectionedLayout` construction, `MaterialisedSectionedLayout.resolve()`, LOCAL-STORAGE-wins precedence, collision warning
- `test_asg_types.py`: already updated (merged)

**Integration tests** (new, in `tests/integration/test_cobol_programs.py`):
- Subprogram with LINKAGE-only (no WORKING-STORAGE): verify params received
- Subprogram with WORKING-STORAGE + LINKAGE: verify both accessible
- Subprogram with LOCAL-STORAGE: verify initialised from VALUE clause each call
- BY REFERENCE mutation: caller's field updated after callee modifies it
- BY CONTENT: caller's field unchanged after callee modifies its copy
- GIVING: scalar return value written back to caller's GIVING field
- Multi-param USING with mixed BY REF and BY CONTENT

---

## Known Limitations

1. **WORKING-STORAGE persistence across calls is not implemented.** WS is re-allocated on each call to a subprogram, wiping its state. This is a pre-existing gap — not introduced by this work. A Beads issue will be filed.

2. **Recursive subprograms** are not explicitly tested. LOCAL-STORAGE is fresh per call so recursion is safe for local state, but WS persistence limitation (above) means recursive WS mutation will not survive re-entry.

3. **BY CONTENT / BY VALUE region copy** is a simplification — a full implementation would copy only the relevant field bytes. Initial implementation copies the whole region; optimisation is deferred.

---

## Implementation Order

1. `str → Register` migration (separate commit, same branch)
2. `CallWithMemory` instruction + opcode + VM handler
3. `sectioned_layout.py` (`SectionedLayout` + `MaterialisedSectionedLayout`)
4. `lower_sectioned_data_division` in `lower_data_division.py`
5. Update all `lower_*` signatures to use `MaterialisedSectionedLayout`
6. Update `cobol_frontend.py`
7. Update `lower_call.py` to emit `CallWithMemory`
8. Integration tests + feature audit updates
9. File Beads issue for WS persistence gap
