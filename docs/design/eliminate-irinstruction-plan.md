# Eliminate IRInstruction — Full Register/Label Type Safety

## Goal

Remove `IRInstruction` entirely. The `Instruction` union of frozen dataclasses
becomes the sole instruction representation. All register-holding fields carry
`Register` objects. All label-holding fields carry `CodeLabel` objects. No raw
strings for registers anywhere. The `Register.__eq__(str)` compatibility bridge
is removed.

## End State

- `IRInstruction` deleted from `ir.py`
- `Opcode` enum retained as read-only marker on typed instructions (not used for dispatch)
- `to_typed()` / `to_flat()` deleted
- `operands` properties deleted from typed instruction classes
- All instruction lists are `list[Instruction]`
- All register fields are `Register` (not `str`)
- All label fields are `CodeLabel` (already the case)
- `Register.__eq__(str)` removed — `Register` only equals `Register`
- `Register.startswith()` removed — use `reg.name.startswith()`
- `SpreadArguments.register` is `Register` (not `str`)
- Typed instructions are frozen; transformations return new instances
- `InstructionBase` provides `map_registers(fn)` and `map_labels(fn)` for generic transforms
- Each typed instruction has standalone `__str__` matching the current flat format

## Current State (after Layers 1–5G, as of 2026-03-25)

**Migration complete.** The `IRInstruction` Pydantic class has been replaced with a factory
function of the same name that returns typed `InstructionBase` subclasses. The compatibility
bridge (`Register.__eq__(str)`, `to_flat()`, `emit()`) has been removed.

**What was done:**
- 31 typed instruction classes in `interpreter/instructions.py`, all frozen dataclasses
- All register-holding fields are `Register` (Layer 1)
- `SpreadArguments.register` is `Register`
- `InstructionBase.map_registers(fn)` and `map_labels(fn)` (Layer 2)
- `Register.rebase(offset)` method
- All consumers use `isinstance` checks and typed field access (Layer 3)
- All frontends use `emit_inst()` with typed instructions (Layer 4)
- `to_flat()` deleted; `__str__` is standalone on `InstructionBase` (Layer 5C-E)
- `emit()` method deleted from all contexts (Layer 5C-E)
- `Register.__eq__(str)` removed; Register only equals Register (Layer 5F)
- `IRInstruction` class replaced with factory function; `to_typed()` renamed to `_to_typed()` (Layer 5G)

**Remaining:**
- `IRInstruction` factory function still exists (~50 construction sites in tests and COBOL `inline_ir`). Converting these to direct typed instruction construction is tracked as follow-up.
- `_to_typed()` and `_as_register()` remain as internal helpers used only by the factory.
- `operands` properties remain on typed instruction classes, used by `__str__` for rendering. These are read-only derived views, not the old `list[Any]` field.
- `Opcode` enum remains as a read-only marker on typed instructions (not used for dispatch).

## Layers

### Layer 1: Register fields in instruction classes ✓

**Issue:** red-dragon-e2pj (CLOSED)

All register-holding operand fields changed from `str` to `Register`. `operands` properties
emit `str()` values for backward compat. `to_typed()` converters wrap operands as `Register(...)`.
`to_flat()` converters `str()` values back. Also fixed boundary issues in `vm.py` (`_resolve_reg`)
and `dataflow.py` (`_is_temporary_register`).

**Discovery:** COBOL `ir_encoders.py` places literal ints in call operands, forcing `_as_register()`
workaround. Filed as red-dragon-pyww. Also: `StoreIndex.value_reg` accepts `SpreadArguments`
at runtime (from JS frontend) despite being typed as `Register`.

### Layer 2: `map_registers()` / `map_labels()` on InstructionBase ✓

**Issue:** red-dragon-p72n (CLOSED)

`Register.rebase(offset)`, `InstructionBase.map_registers(fn)`, `InstructionBase.map_labels(fn)`
all implemented. Handles `Register`, `Register | None`, `tuple[Register | SpreadArguments, ...]`,
`CodeLabel`, `tuple[CodeLabel, ...]` fields. Python 3.13 `types.UnionType` handled.

**Discovery:** `map_registers` needed a fix to skip non-Register literals in args tuples
(strings/ints from COBOL IR that `_as_register` leaves as-is).

### Layer 3: Migrate consumers to typed field access

#### Layer 3a: Handlers + executor dispatch — DEFERRED

**Issue:** red-dragon-ufnx (CLOSED — deferred)

Executor dispatch was already clean (0 markers). Only 4 `operands[]` accesses remain in
`arithmetic.py` (3) and `variables.py` (1). These cannot be replaced with typed field access
until the COBOL literal operand issue is fixed (red-dragon-pyww), because typed fields return
`Register` objects but the handlers need raw ints/strings from the `operands` list.

#### Layer 3b: Type inference ✓

**Issue:** red-dragon-x37k (CLOSED)

Much larger than estimated (~30 → actual ~80 sites). Dispatch table changed from
`dict[Opcode, handler]` to `dict[type, handler]`. All 16 handler functions updated
with specific typed instruction signatures. `to_typed()` calls removed from handlers,
centralized at dispatch point for IRInstruction normalization.

**Discovery:** `dict[str, TypeExpr]` annotations stay as `str` — they store variable
names, not register references.

#### Layer 3c: CFG + dataflow + interprocedural ✓

**Issue:** red-dragon-3h0y (CLOSED)

20 `opcode==` comparisons replaced with `isinstance` across cfg.py, dataflow.py,
interprocedural/{summaries,call_graph,propagation}.py. Also updated viz/panels/dataflow_graph_panel.py
and tests/unit/test_cfg.py.

**Discovery:** cfg.py added `_normalize_structural()` helper that converts structural opcodes
to typed form at `build_cfg` entry. This introduces a `to_typed()` call at a normalization
point — cannot be removed until all instruction lists are pure typed.

#### Layer 3d: Project infrastructure ✓

**Issue:** red-dragon-30vm (CLOSED)

Linker uses `map_registers(rebase)` + `map_labels(namespace)` instead of operand-by-operand
iteration. `isinstance` checks in linker and compiler. Dead `_rebase_operand` helper removed.

**Discovery:** Linker still calls `to_typed()` + `to_flat()` in `_transform_instruction()`
because the instruction list is mixed-type. The `to_flat()` call at the end reconverts to
IRInstruction for downstream compatibility. Both calls can be removed once all instruction
lists are pure typed.

#### Layer 3e: LLM + COBOL + registry + misc ✓

**Issue:** red-dragon-2la9 (CLOSED)

128 sites migrated (much larger than estimated ~40). COBOL `ir_encoders.py` dominated
with 106 `IRInstruction` constructions → typed instructions. LLM frontend mutation
→ `dataclasses.replace()`. `run.py` uses `isinstance` checks.

**Discovery:** `registry.py` left 3 `opcode==` comparisons unfixed because instruction
list is mixed-type. Filed as red-dragon-b6m4.

### Layer 4a: `lower_expr() -> Register` signature change ✓

**Issue:** red-dragon-8e1x (CLOSED)

~316 expression handler signatures changed from `-> str` to `-> Register` across 33 files.
Methods returning variable names, operators, type strings correctly excluded.

### Layer 4: Migrate producers (frontends) ✓

All 15 tree-sitter frontends + `_base.py` + `context.py` + COBOL `emit_context.py` migrated.
~1,300 `emit(Opcode.X, ...)` calls converted to `emit_inst(TypedInstruction(...))`.

**17 issues all CLOSED:** 9qh8, 2pd7, fa8o, i0vm, 98uv, 8tm0, fpmm, eh2q, 4soe,
io2z, zgu9, s2d9, cwbt, nv63, wd6g, um47, di1g.

**Remaining:** 59 `emit(Opcode.` calls in COBOL-specific frontend files (red-dragon-oczk).
The `emit()` method itself stays until these are converted.

### Layer 5: Remove the bridge

**Issue:** red-dragon-ee66
**Depends on:** All prerequisite issues below must be resolved first.

#### Prerequisites (must resolve before Layer 5)

| Issue | Description | Why blocking |
|-------|-------------|-------------|
| pyww | Fix COBOL ir_encoders literal operands; remove `_as_register()` | Literal ints in Register-typed fields violate type safety; `_as_register()` is a workaround |
| oczk | Migrate 59 COBOL frontend `emit(Opcode.)` calls | Can't delete `emit()` method while callers exist |
| b6m4 | Migrate 3 registry.py `opcode==` comparisons | Mixed-type list needs normalization |
| j1o6 | Fix `_resolve_reg` annotation + `dataflow.py` `str()` coercion | Boundary cleanup before removing `Register.__eq__(str)` |

#### Layer 5 scope

**Scope:** `interpreter/ir.py`, `interpreter/instructions.py`, `interpreter/register.py`,
`interpreter/frontends/_base.py`, `interpreter/frontends/context.py`,
`interpreter/cobol/emit_context.py`, + import cleanup across ~30 files

Deletions:
- `IRInstruction` class from `ir.py`
- `to_typed()` / `to_flat()` + `_TO_TYPED` / `_TO_FLAT` dispatch tables from `instructions.py`
- `_as_register()` helper from `instructions.py`
- `operands` properties from all 31 typed instruction classes
- `emit()` method from `_base.py`, `context.py`, `cobol/emit_context.py`
- `Register.__eq__(str)` from `register.py`
- `Register.startswith()` from `register.py`
- `Register.__get_pydantic_core_schema__()` if no longer needed
- `_normalize_structural()` from `cfg.py` (no longer needed when lists are pure typed)
- Normalization `to_typed()` calls at dispatch points in `type_inference.py`, `cfg.py`, `linker.py`
- `to_flat()` call in `linker.py` `_transform_instruction()`

Additions:
- Standalone `__str__` on each typed instruction class, matching the current
  `IRInstruction.__str__` flat format (e.g., `CONST %r0 "42"`). This replaces
  the current delegation through `to_flat()`. Zero test churn.

Opcode decision (resolved):
- `Opcode` enum **stays** in `ir.py` as a read-only marker
- `opcode` property remains on each typed instruction class
- **Not used for dispatch** — `isinstance`/`type()` dict is the primary discriminant
- Useful for serialization, debugging labels, and IR dumps
- Remove `Opcode` imports from files that used it for dispatch
- Keep `Opcode` imports only where used for display/serialization

Cleanup:
- Remove stale `Opcode` imports across the codebase
- `list[IRInstruction]` → `list[Instruction]` in any remaining type annotations
- 4 handler `operands[]` accesses → typed field access (unblocked once pyww is resolved)

**Test gate:** `IRInstruction` not imported anywhere. `to_typed` not called anywhere.
`to_flat` not called anywhere. `operands` not accessed anywhere outside `instructions.py`.
`Register.__eq__` only compares `Register` to `Register`. No `emit(Opcode.` calls anywhere.
All tests pass.

## Ordering Constraints

```
Layer 1 ✓ → Layer 2 ✓ → Layer 3a (deferred), 3d ✓
Layer 1 ✓ → Layer 3b ✓, 3c ✓, 3e ✓
Layer 1 ✓ → Layer 4a ✓ → Layer 4 (all 17) ✓

Prerequisites: pyww, oczk, b6m4, j1o6 → Layer 5 (remove bridge)
```

## Risk Mitigation

Each sub-issue is a self-contained commit with passing tests.
The `Register.__eq__(str)` bridge remains until Layer 5, making all preceding
layers individually safe. If any sub-issue introduces regressions, it can be
reverted independently.

## Sub-issue Summary

| ID | Layer | Description | Status |
|----|-------|-------------|--------|
| e2pj | 1 | Register fields in instruction classes | ✓ CLOSED |
| p72n | 2 | map_registers/map_labels on InstructionBase | ✓ CLOSED |
| ufnx | 3a | Handlers + executor dispatch | DEFERRED (blocked by pyww) |
| x37k | 3b | Type inference | ✓ CLOSED |
| 3h0y | 3c | CFG + dataflow + interprocedural | ✓ CLOSED |
| 30vm | 3d | Project infrastructure (linker/compiler) | ✓ CLOSED |
| 2la9 | 3e | LLM + COBOL + registry + misc | ✓ CLOSED |
| 8e1x | 4a | lower_expr() -> Register signature | ✓ CLOSED |
| 9qh8 | 4-base | _base.py + context.py emit migration | ✓ CLOSED |
| 2pd7 | 4-c | C frontend emit migration | ✓ CLOSED |
| fa8o | 4-lua | Lua frontend emit migration | ✓ CLOSED |
| i0vm | 4-ts | TypeScript frontend emit migration | ✓ CLOSED |
| 98uv | 4-cpp | C++ frontend emit migration | ✓ CLOSED |
| 8tm0 | 4-scala | Scala frontend emit migration | ✓ CLOSED |
| fpmm | 4-go | Go frontend emit migration | ✓ CLOSED |
| eh2q | 4-python | Python frontend emit migration | ✓ CLOSED |
| 4soe | 4-js | JavaScript frontend emit migration | ✓ CLOSED |
| io2z | 4-pascal | Pascal frontend emit migration | ✓ CLOSED |
| zgu9 | 4-php | PHP frontend emit migration | ✓ CLOSED |
| s2d9 | 4-csharp | C# frontend emit migration | ✓ CLOSED |
| cwbt | 4-java | Java frontend emit migration | ✓ CLOSED |
| nv63 | 4-kotlin | Kotlin frontend emit migration | ✓ CLOSED |
| wd6g | 4-ruby | Ruby frontend emit migration | ✓ CLOSED |
| um47 | 4-rust | Rust frontend emit migration | ✓ CLOSED |
| di1g | 4-cobol | COBOL emit_context migration | ✓ CLOSED |
| pyww | prereq | COBOL ir_encoders literal operands + _as_register | ✓ CLOSED |
| oczk | prereq | 59 COBOL frontend emit() calls | ✓ CLOSED |
| b6m4 | prereq | 3 registry.py opcode== comparisons | ✓ CLOSED |
| j1o6 | prereq | vm.py/dataflow.py boundary cleanup | ✓ CLOSED |
| 2z99 | 5F | Remove Register.__eq__(str) | ✓ CLOSED |
| wqvg | 5G | Delete IRInstruction class | ✓ CLOSED |
| ee66 | 5 | Remove the compatibility bridge | ✓ CLOSED |
| 0ibe | epic | Eliminate IRInstruction | ✓ CLOSED |
