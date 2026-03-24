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

**Issue:** red-dragon-e2pj
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

**Issue:** red-dragon-p72n
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

All non-frontend interpreter code that reads instructions. Decomposed into
5 independently-committable sub-issues.

#### Layer 3a: Handlers + executor dispatch (~100 sites)

**Issue:** red-dragon-ufnx
**Depends on:** Layer 2
**Scope:** `interpreter/vm/executor.py`, `interpreter/handlers/*.py` (7 files)

Changes:
- `interpreter/vm/executor.py`: dispatch from `dict[Opcode, handler]` → `dict[type, handler]`
- All 7 handler files: remove `to_typed()` calls — `inst` IS the typed instruction.
  Remove `inst.operands[N]` access. Handler signatures: `inst: IRInstruction` →
  specific typed instruction (e.g., `inst: Binop`).

**Test gate:** All tests pass. No `to_typed()` calls in handlers. Dispatch uses `type()`.

#### Layer 3b: Type inference (~30 sites)

**Issue:** red-dragon-x37k
**Depends on:** Layer 1
**Scope:** `interpreter/types/type_inference.py`

Changes:
- Remove 16 `to_typed()` calls, use typed fields directly
- `register_types: dict[str, TypeExpr]` → `dict[Register, TypeExpr]`
- Remove `inst.operands` length guards

**Test gate:** All tests pass. No `to_typed()` in type_inference.py.

#### Layer 3c: CFG + dataflow + interprocedural (~50 sites)

**Issue:** red-dragon-3h0y
**Depends on:** Layer 1
**Scope:** `interpreter/cfg.py`, `interpreter/dataflow.py`, `interpreter/interprocedural/*`

Changes:
- `interpreter/cfg.py`: `inst.opcode == Opcode.LABEL` → `isinstance(inst, Label_)`.
  `inst.opcode == Opcode.BRANCH` → `isinstance(inst, Branch)`. Etc.
- `interpreter/dataflow.py`: typed field access, `Register` in type annotations.
- `interpreter/interprocedural/*`: typed field access, remove `to_typed()`.

**Test gate:** All tests pass. No `to_typed()` or opcode comparisons in these files.

#### Layer 3d: Project infrastructure (~30 sites)

**Issue:** red-dragon-30vm
**Depends on:** Layer 2 (needs `map_registers`/`map_labels`)
**Scope:** `interpreter/project/linker.py`, `interpreter/project/compiler.py`

Changes:
- `interpreter/project/linker.py`: operand-by-operand iteration →
  `map_registers(rebase)` + `map_labels(namespace)`. Construct typed instructions
  directly instead of `IRInstruction(...)`.
- `interpreter/project/compiler.py`: typed field access.

**Test gate:** All tests pass. No `IRInstruction(...)` construction in linker/compiler.

#### Layer 3e: LLM + COBOL + registry + misc (~40 sites)

**Issue:** red-dragon-2la9
**Depends on:** Layer 1
**Scope:** `interpreter/llm/*`, `interpreter/cobol/ir_encoders.py`,
`interpreter/registry.py`, `interpreter/run.py`, `interpreter/ir_stats.py`,
`interpreter/cfg_types.py`, `interpreter/frontend.py`

Changes:
- `interpreter/llm/*`: replace `inst.operands[0] = x` mutation with
  `instructions[i] = dataclasses.replace(inst, value=x)`.
- `interpreter/cobol/ir_encoders.py`: construct typed instructions instead of `IRInstruction(...)`.
- `interpreter/registry.py`: typed field access, `isinstance` checks.
- `interpreter/run.py`: `isinstance` pattern.
- `interpreter/ir_stats.py`: use `type(inst).__name__` or `inst.opcode` property.
- `interpreter/cfg_types.py`, `interpreter/frontend.py`: `list[IRInstruction]` → `list[Instruction]`.

**Test gate:** All tests pass. No `IRInstruction(...)` construction in these files.

### Layer 4a: `lower_expr() -> Register` signature change

**Issue:** red-dragon-8e1x
**Depends on:** Layer 1
**Scope:** `interpreter/frontends/_base.py`, `interpreter/frontends/context.py`,
all 15 frontend directories, `interpreter/frontends/typescript.py`

Changes:
- Change `lower_expr()` return type in `_base.py` from `-> str` to `-> Register`
- Change all ~350 expression handler return annotations across all frontends
- Single atomic commit — mechanical find-and-replace

**Why safe:** `Register.__eq__(str)` bridge handles all downstream comparisons.
All call sites that receive the return value continue to work unchanged.

**Test gate:** All tests pass. No `lower_expr` signatures returning `str`.

### Layer 4: Migrate producers (frontends)

All frontend `emit(Opcode.X, ...)` calls → `emit_inst(TypedInstruction(...))`.
Decomposed into 19 independently-committable sub-issues. Each frontend migrates
its own calls without removing the `emit()` method (removed in Layer 5).

All 19 sub-issues depend on Layer 4a.

#### Layer 4 sub-issues

| Sub-issue | Target | Sites | Issue |
|-----------|--------|-------|-------|
| 4-base | `_base.py` + `context.py` | 45 | red-dragon-9qh8 |
| 4-c | `frontends/c/` | 46 | red-dragon-2pd7 |
| 4-lua | `frontends/lua/` | 49 | red-dragon-fa8o |
| 4-ts | `frontends/typescript.py` | 42 | red-dragon-i0vm |
| 4-cpp | `frontends/cpp/` | 54 | red-dragon-98uv |
| 4-scala | `frontends/scala/` | 70 | red-dragon-8tm0 |
| 4-go | `frontends/go/` | 83 | red-dragon-fpmm |
| 4-python | `frontends/python/` | 84 | red-dragon-eh2q |
| 4-js | `frontends/javascript/` | 91 | red-dragon-4soe |
| 4-pascal | `frontends/pascal/` | 99 | red-dragon-io2z |
| 4-php | `frontends/php/` | 103 | red-dragon-zgu9 |
| 4-csharp | `frontends/csharp/` | 105 | red-dragon-s2d9 |
| 4-java | `frontends/java/` | 111 | red-dragon-cwbt |
| 4-kotlin | `frontends/kotlin/` | 119 | red-dragon-nv63 |
| 4-ruby | `frontends/ruby/` | 120 | red-dragon-wd6g |
| 4-rust | `frontends/rust/` | 127 | red-dragon-um47 |
| 4-cobol | `cobol/emit_context.py` | 9 | red-dragon-di1g |

Each sub-issue:
- Converts all `emit(Opcode.X, ...)` calls to `emit_inst(TypedInstruction(...))`
- Passes `Register` objects directly to instruction constructors (no `str()` wrapping)
- One commit per frontend
- All 17 sub-issues are independent of each other — any ordering works

**Test gate per sub-issue:** All tests pass. No `emit(Opcode.` calls in the target files.

**Test gate for Layer 4 overall:** No `emit(Opcode.` calls remaining anywhere.
All frontends produce typed instructions directly.

### Layer 5: Remove the bridge

**Issue:** red-dragon-ee66
**Depends on:** All of Layer 3 (3a–3e) and all of Layer 4 (19 sub-issues)
**Scope:** `interpreter/ir.py`, `interpreter/instructions.py`, `interpreter/register.py`,
`interpreter/frontends/_base.py`, `interpreter/frontends/context.py`, + import cleanup across ~30 files

Deletions:
- `IRInstruction` class from `ir.py`
- `to_typed()` / `to_flat()` + `_TO_TYPED` / `_TO_FLAT` dispatch tables from `instructions.py`
- `operands` properties from all 31 typed instruction classes
- `emit()` method from `_base.py` and `context.py`
- `Register.__eq__(str)` from `register.py`
- `Register.startswith()` from `register.py`
- `Register.__get_pydantic_core_schema__()` if no longer needed

Additions:
- Standalone `__str__` on each typed instruction class, matching the current
  `IRInstruction.__str__` flat format (e.g., `CONST %r0 "42"`). This replaces
  the current delegation through `to_flat()`. Zero test churn.

Opcode decision (resolved):
- `Opcode` enum **stays** in `ir.py` as a read-only marker
- `opcode` property remains on each typed instruction class
- **Not used for dispatch** — `isinstance`/`type()` dict is the primary discriminant
- Useful for serialization, debugging labels, and IR dumps
- Remove `Opcode` imports from files that used it for dispatch (handlers, cfg, executor, etc.)
- Keep `Opcode` imports only where used for display/serialization

Cleanup:
- Remove stale `Opcode` imports across the codebase
- `list[IRInstruction]` → `list[Instruction]` in any remaining type annotations

**Test gate:** `IRInstruction` not imported anywhere. `to_typed` not called anywhere.
`operands` not accessed anywhere outside `instructions.py`. `Register.__eq__` only
compares `Register` to `Register`. All tests pass.

## Ordering Constraints

```
Layer 1 (Register fields)
├── Layer 2 (map_registers/map_labels)
│   ├── Layer 3a (handlers + executor dispatch)
│   └── Layer 3d (project infrastructure)
├── Layer 3b (type inference)
├── Layer 3c (CFG + dataflow + interprocedural)
├── Layer 3e (LLM + COBOL + registry + misc)
└── Layer 4a (lower_expr() -> Register signature)
    ├── 4-base, 4-c, 4-cpp, 4-csharp, 4-go, 4-java, 4-js
    ├── 4-kotlin, 4-lua, 4-pascal, 4-php, 4-python
    ├── 4-ruby, 4-rust, 4-scala, 4-ts, 4-cobol
    └── (all 17 independent of each other)

Layer 3 (all 5) + Layer 4 (all 17) → Layer 5 (remove bridge)
```

Parallelism opportunities:
- After Layer 1: Layers 2, 3b, 3c, 3e, and 4a can all start
- After Layer 2: Layers 3a and 3d can start
- After Layer 4a: all 17 frontend sub-issues are independent
- Layer 3 and Layer 4 tracks are fully independent of each other

## Risk Mitigation

Each sub-issue is a self-contained commit with passing tests.
The `Register.__eq__(str)` bridge remains until Layer 5, making all preceding
layers individually safe. If any sub-issue introduces regressions, it can be
reverted independently.

## Files Affected (approximate counts)

| Layer | Files | Sites |
|-------|-------|-------|
| 1 | 2 (instructions.py, ir.py) | ~60 field changes + converter updates |
| 2 | 2 (instructions.py, register.py) | 2 new methods + 1 new Register method |
| 3a | 8 (executor.py + 7 handler files) | ~100 sites |
| 3b | 1 (type_inference.py) | ~30 sites |
| 3c | ~5 (cfg.py, dataflow.py, interprocedural/*) | ~50 sites |
| 3d | 2 (linker.py, compiler.py) | ~30 sites |
| 3e | ~7 (llm/*, cobol/ir_encoders.py, registry.py, run.py, ir_stats.py, cfg_types.py, frontend.py) | ~40 sites |
| 4a | ~48 (all frontend files + _base.py + context.py) | ~350 signature changes |
| 4 (all) | ~48 (all frontend files + _base.py + context.py + cobol) | ~1,357 emit() conversions |
| 5 | ~3 (ir.py, instructions.py, register.py) + cleanup across ~30 files | ~100 import removals + 31 `__str__` methods |

## Sub-issue Summary

| ID | Layer | Description | Depends on | Sites |
|----|-------|-------------|------------|-------|
| e2pj | 1 | Register fields in instruction classes | — | ~60 |
| p72n | 2 | map_registers/map_labels on InstructionBase | L1 | 3 methods |
| ufnx | 3a | Handlers + executor dispatch | L2 | ~100 |
| x37k | 3b | Type inference | L1 | ~30 |
| 3h0y | 3c | CFG + dataflow + interprocedural | L1 | ~50 |
| 30vm | 3d | Project infrastructure (linker/compiler) | L2 | ~30 |
| 2la9 | 3e | LLM + COBOL + registry + misc | L1 | ~40 |
| 8e1x | 4a | lower_expr() -> Register signature | L1 | ~350 |
| 9qh8 | 4-base | _base.py + context.py emit migration | L4a | 45 |
| 2pd7 | 4-c | C frontend emit migration | L4a | 46 |
| fa8o | 4-lua | Lua frontend emit migration | L4a | 49 |
| i0vm | 4-ts | TypeScript frontend emit migration | L4a | 42 |
| 98uv | 4-cpp | C++ frontend emit migration | L4a | 54 |
| 8tm0 | 4-scala | Scala frontend emit migration | L4a | 70 |
| fpmm | 4-go | Go frontend emit migration | L4a | 83 |
| eh2q | 4-python | Python frontend emit migration | L4a | 84 |
| 4soe | 4-js | JavaScript frontend emit migration | L4a | 91 |
| io2z | 4-pascal | Pascal frontend emit migration | L4a | 99 |
| zgu9 | 4-php | PHP frontend emit migration | L4a | 103 |
| s2d9 | 4-csharp | C# frontend emit migration | L4a | 105 |
| cwbt | 4-java | Java frontend emit migration | L4a | 111 |
| nv63 | 4-kotlin | Kotlin frontend emit migration | L4a | 119 |
| wd6g | 4-ruby | Ruby frontend emit migration | L4a | 120 |
| um47 | 4-rust | Rust frontend emit migration | L4a | 127 |
| di1g | 4-cobol | COBOL emit_context migration | L4a | 9 |
| ee66 | 5 | Remove the compatibility bridge | L3 all + L4 all | ~100 |
