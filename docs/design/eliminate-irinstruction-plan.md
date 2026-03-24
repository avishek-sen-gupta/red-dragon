# Eliminate IRInstruction — Full Register/Label Type Safety

## Goal

Remove `IRInstruction` entirely. The `Instruction` union of frozen dataclasses
becomes the sole instruction representation. All register-holding fields carry
`Register` objects. All label-holding fields carry `CodeLabel` objects. No raw
strings for registers anywhere. The `Register.__eq__(str)` compatibility bridge
is removed.

## End State

- `IRInstruction` deleted from `ir.py`
- `Opcode` enum deleted (instruction type is the discriminant; `isinstance` replaces opcode switches)
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

## Current State (after phases 1–3 of the original plan)

- 30 typed instruction classes exist in `interpreter/instructions.py`
- All 28 VM handler functions use `to_typed()` for field access
- 67 `operands[N]` accesses in infrastructure migrated to typed fields
- Typed instructions carry IRInstruction-compatible interface (`operands` property, `opcode` property)
- Frontends: `common/` migrated to `emit_inst()` (190 calls), all other frontends still use flat `emit(Opcode.X, ...)`
- Register operand fields are `str`, not `Register`
- Instruction lists are `list[IRInstruction]` everywhere
- `emit_inst()` appends typed instructions directly to `list[IRInstruction]` (duck-typing)

## Layers

### Layer 1: Register fields in instruction classes

**Scope:** `interpreter/instructions.py`, `interpreter/ir.py` (SpreadArguments)

Changes:
- All `_reg: str = ""` fields → `_reg: Register = NO_REGISTER`
- `left: str`, `right: str`, `operand: str` → `Register`
- `args: tuple[str | SpreadArguments, ...]` → `tuple[Register | SpreadArguments, ...]`
- `value_reg: str | None` (Return_, Throw_) → `Register | None`
- `SpreadArguments.register: str` → `Register`
- `operands` properties: `str()` Register values (temporary compat bridge)
- `to_typed()` converters: wrap operand strings as `Register(...)`
- `to_flat()` converters: `str()` Register values back

**Test gate:** All existing tests pass unchanged. Round-trip tests pass.

**Why safe:** `Register.__eq__(str)` handles comparison. `str(Register)` returns name.
Consumers that `str()` wrap continue to work. Consumers that use bare field values
work via `Register.__eq__`.

### Layer 2: `map_registers()` / `map_labels()` on InstructionBase

**Scope:** `interpreter/instructions.py`, `interpreter/register.py`

Changes:
- Add `Register.rebase(offset: int) -> Register` method
- Add `InstructionBase.map_registers(fn: Callable[[Register], Register]) -> Self`
  - Introspects fields via `dataclasses.fields()`
  - Applies `fn` to all `Register` fields, `Register | None` fields, and
    `tuple[Register | SpreadArguments, ...]` fields (mapping Register elements only)
  - Returns new instance via `dataclasses.replace()`
- Add `InstructionBase.map_labels(fn: Callable[[CodeLabel], CodeLabel]) -> Self`
  - Same pattern for `CodeLabel` fields and `tuple[CodeLabel, ...]` fields

**Test gate:** Unit tests for map_registers/map_labels on each instruction type.

### Layer 3: Migrate consumers to typed field access

**Scope:** All non-frontend interpreter code that reads instructions.

Changes per file:
- `interpreter/vm/executor.py`: dispatch changes from `dict[Opcode, handler]` to `dict[type, handler]`
- `interpreter/handlers/*`: remove `to_typed()` calls — `inst` IS the typed instruction.
  Remove `inst.operands[N]` access. Handler signatures: `inst: IRInstruction` → `inst: Instruction`.
- `interpreter/types/type_inference.py`: remove `inst.operands` length guards, use typed fields.
  `register_types: dict[str, TypeExpr]` → `dict[Register, TypeExpr]`.
- `interpreter/dataflow.py`: typed field access, `Register` in type annotations.
- `interpreter/interprocedural/*`: typed field access, remove `to_typed()`.
- `interpreter/cfg.py`: `isinstance(inst, Label_)` instead of `inst.opcode == Opcode.LABEL`.
  `isinstance(inst, Branch)` instead of `inst.opcode == Opcode.BRANCH`. Etc.
- `interpreter/run.py`: same `isinstance` pattern.
- `interpreter/project/linker.py`: use `map_registers(rebase)` + `map_labels(namespace)`
  instead of operand-by-operand iteration. Construct typed instructions directly
  instead of `IRInstruction(...)`.
- `interpreter/project/compiler.py`: typed field access.
- `interpreter/registry.py`: typed field access, `isinstance` checks.
- `interpreter/llm/*`: replace `inst.operands[0] = x` mutation with
  `instructions[i] = dataclasses.replace(inst, value=x)`.
- `interpreter/cobol/emit_context.py`: typed field access.
- `interpreter/cobol/ir_encoders.py`: construct typed instructions instead of `IRInstruction(...)`.
- `interpreter/cfg_types.py`, `interpreter/frontend.py`, etc.: `list[IRInstruction]` → `list[Instruction]`.
- `interpreter/ir_stats.py`: use `type(inst).__name__` or `inst.opcode` property (kept as read-only).

**Test gate:** All tests pass. No `inst.operands` access remaining outside `instructions.py`.
No `to_typed()` calls remaining. No `IRInstruction(...)` construction outside `ir.py`.

### Layer 4: Migrate producers (frontends)

**Scope:** All frontend code.

Changes:
- `lower_expr() -> str` → `-> Register` in context.py, _base.py
- All ~350 expression handler return type annotations: `-> str` → `-> Register`
- Migrate remaining flat `emit(Opcode.X, ...)` calls in `_base.py`, `context.py`,
  `csharp/expressions.py`, `rust/declarations.py` → `emit_inst(TypedInstruction(...))`
- Remove all `str()` wrapping in instruction constructors — pass `Register` directly
- Remove `emit()` method from `context.py` and `_base.py`
- `instructions: list[IRInstruction]` → `list[Instruction]` in context.py, _base.py

**Test gate:** No `emit(Opcode.` calls remaining. No `str()` wrapping on Register values
in instruction constructors. All frontends produce typed instructions directly.

### Layer 5: Remove the bridge

**Scope:** `interpreter/ir.py`, `interpreter/instructions.py`, `interpreter/register.py`

Changes:
- Delete `IRInstruction` class from `ir.py`
- Delete `to_typed()` / `to_flat()` from `instructions.py`
- Delete `_TO_TYPED` and `_TO_FLAT` dispatch tables
- Delete `operands` properties from all typed instruction classes
- Delete `opcode` properties from all typed instruction classes (or keep as derived; TBD)
- Delete `Opcode` enum from `ir.py` (or keep as derived string labels for debugging; TBD)
- Remove `Register.__eq__(str)` — Register only equals Register
- Remove `Register.startswith()` — callers use `reg.name.startswith()`
- Remove `Register.__get_pydantic_core_schema__()` if no longer needed
- Fix any code that relied on the string compatibility bridge
- Clean up imports: remove `Opcode` imports across the codebase

**Test gate:** `IRInstruction` not imported anywhere. `to_typed` not called anywhere.
`operands` not accessed anywhere. All tests pass.

## Ordering Constraints

- Layer 1 before everything else (foundation)
- Layer 2 before Layer 3 (linker needs map_registers/map_labels)
- Layer 3 before Layer 5 (consumers must not use IRInstruction before it's deleted)
- Layer 4 before Layer 5 (producers must not create IRInstruction before it's deleted)
- Layer 3 and Layer 4 are independent of each other and can be interleaved

## Risk Mitigation

Each layer is a self-contained commit (or series of commits) with passing tests.
The `Register.__eq__(str)` bridge remains until Layer 5, making Layers 1–4
individually safe. If any layer introduces regressions, it can be reverted
independently.

## Files Affected (approximate counts)

| Layer | Files | Sites |
|-------|-------|-------|
| 1 | 2 (instructions.py, ir.py) | ~60 field changes + converter updates |
| 2 | 2 (instructions.py, register.py) | 2 new methods + 1 new Register method |
| 3 | ~20 (handlers, vm, types, cfg, dataflow, interprocedural, project, registry, llm, cobol) | ~250 sites |
| 4 | ~48 (all frontend files + context.py + _base.py) | ~2200 sites |
| 5 | ~3 (ir.py, instructions.py, register.py) + cleanup across ~30 files | ~100 import/reference removals |
