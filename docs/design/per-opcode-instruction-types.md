# Per-Opcode Instruction Types — Design

Replace `IRInstruction.operands: list[Any]` with per-opcode typed dataclasses.

## Current state

```python
class IRInstruction(BaseModel):
    opcode: Opcode
    result_reg: Register = NO_REGISTER
    operands: list[Any] = []          # ← the problem
    label: CodeLabel = NO_LABEL
    branch_targets: list[CodeLabel] = []
    source_location: SourceLocation = NO_SOURCE_LOCATION
```

Every opcode stuffs different things into `operands` positionally.
Handlers destructure with `inst.operands[0]`, `inst.operands[1]`, etc.
No type safety, no documentation, silent misuse.

## Target state

A discriminated union of frozen dataclasses, one per opcode.
All share `result_reg`, `label`, `branch_targets`, `source_location` via a base.

```python
Instruction = (
    Const | LoadVar | DeclVar | StoreVar |
    Binop | Unop |
    CallFunction | CallMethod | CallUnknown |
    LoadField | StoreField | LoadFieldIndirect |
    LoadIndex | StoreIndex |
    LoadIndirect | StoreIndirect |
    NewObject | NewArray |
    Branch | BranchIf |
    Label_ |
    Return_ | Throw_ |
    TryPush | TryPop |
    Symbolic |
    AddressOf |
    AllocRegion | LoadRegion | WriteRegion |
    SetContinuation | ResumeContinuation
)
```

## Per-opcode schemas

Derived from handler destructuring and frontend emit sites.

### Variables & Constants

| Type | Fields | Notes |
|------|--------|-------|
| `Const` | `result_reg: Register, value: str` | Literal string (`"42"`, `"True"`, `"None"`, `'"hello"'`, func labels) |
| `LoadVar` | `result_reg: Register, name: str` | |
| `DeclVar` | `name: str, value_reg: str` | No result_reg |
| `StoreVar` | `name: str, value_reg: str` | No result_reg |
| `Symbolic` | `result_reg: Register, hint: str` | Parameter placeholders, unknowns |

### Arithmetic

| Type | Fields | Notes |
|------|--------|-------|
| `Binop` | `result_reg: Register, operator: str, left: str, right: str` | `left`/`right` are register refs |
| `Unop` | `result_reg: Register, operator: str, operand: str` | |

### Calls

| Type | Fields | Notes |
|------|--------|-------|
| `CallFunction` | `result_reg: Register, func_name: str, args: list[str \| SpreadArguments]` | |
| `CallMethod` | `result_reg: Register, obj_reg: str, method_name: str, args: list[str \| SpreadArguments]` | |
| `CallUnknown` | `result_reg: Register, target_reg: str, args: list[str \| SpreadArguments]` | Dynamic dispatch |

### Memory — Fields

| Type | Fields | Notes |
|------|--------|-------|
| `LoadField` | `result_reg: Register, obj_reg: str, field_name: str` | |
| `StoreField` | `obj_reg: str, field_name: str, value_reg: str` | No result_reg |
| `LoadFieldIndirect` | `result_reg: Register, obj_reg: str, name_reg: str` | Field name from register |

### Memory — Indexing

| Type | Fields | Notes |
|------|--------|-------|
| `LoadIndex` | `result_reg: Register, arr_reg: str, index_reg: str` | |
| `StoreIndex` | `arr_reg: str, index_reg: str, value_reg: str` | No result_reg |

### Memory — Pointers

| Type | Fields | Notes |
|------|--------|-------|
| `LoadIndirect` | `result_reg: Register, ptr_reg: str` | Dereference |
| `StoreIndirect` | `ptr_reg: str, value_reg: str` | No result_reg |
| `AddressOf` | `result_reg: Register, var_name: str` | `&var` |

### Objects

| Type | Fields | Notes |
|------|--------|-------|
| `NewObject` | `result_reg: Register, type_hint: str` | |
| `NewArray` | `result_reg: Register, type_hint: str, size_reg: str` | `type_hint` = "list", "tuple", "dict", class name |

### Control Flow

| Type | Fields | Notes |
|------|--------|-------|
| `Branch` | `label: CodeLabel` | Unconditional jump (target in `label` field) |
| `BranchIf` | `cond_reg: str, branch_targets: list[CodeLabel]` | `[true_label, false_label]` |
| `Label_` | `label: CodeLabel` | Block entry point |
| `Return_` | `value_reg: str \| None` | Optional return value |
| `Throw_` | `value_reg: str \| None` | Optional exception value |

### Exceptions

| Type | Fields | Notes |
|------|--------|-------|
| `TryPush` | `catch_labels: list[CodeLabel], finally_label: CodeLabel, end_label: CodeLabel` | |
| `TryPop` | *(no fields)* | |

### Regions (COBOL byte-addressable memory)

| Type | Fields | Notes |
|------|--------|-------|
| `AllocRegion` | `result_reg: Register, size_reg: str` | |
| `LoadRegion` | `result_reg: Register, region_reg: str, offset_reg: str` | |
| `WriteRegion` | `region_reg: str, offset_reg: str, length: int, value_reg: str` | `length` is literal int |

### Continuations (COBOL PERFORM)

| Type | Fields | Notes |
|------|--------|-------|
| `SetContinuation` | `name: str, target_label: CodeLabel` | |
| `ResumeContinuation` | `name: str` | |

## Shared base

```python
@dataclass(frozen=True)
class InstructionBase:
    source_location: SourceLocation = NO_SOURCE_LOCATION
```

Each type includes only the fields it uses. `result_reg` is only on types
that produce values. `label` is only on Label_ and Branch. `branch_targets`
is only on BranchIf.

## Migration strategy

### Phase 1: Parallel types with adapter (non-breaking)
1. Define all 30 typed instruction dataclasses in `interpreter/instructions.py`
2. Add `IRInstruction.to_typed() -> Instruction` — converts from flat to typed
3. Add `Instruction.to_ir() -> IRInstruction` — converts back to flat
4. Test round-trip: every instruction in the test suite survives `to_typed().to_ir()`

### Phase 2: Migrate consumers (handler by handler)
5. Each handler receives typed instruction directly (pattern match)
6. One handler file at a time, smallest first: variables → arithmetic → memory → calls → control_flow → regions
7. After each handler migrates, run full test suite

### Phase 3: Migrate producers (frontend by frontend)
8. `emit()` methods accept typed instructions directly
9. One frontend at a time: common → python → javascript → java → ...
10. COBOL emit_context last (most complex)

### Phase 4: Remove flat IRInstruction
11. `operands: list[Any]` gone
12. `opcode: Opcode` gone (discriminated by type)
13. CFG, dataflow, type inference all operate on `Instruction` union

## Open questions

1. ~~**Register refs in operand fields**: Should `left: str` in Binop become `left: Register`?~~ **Resolved: Yes.** All register-holding fields will become `Register`. See `docs/design/eliminate-irinstruction-plan.md`.

2. ~~**Pydantic or plain dataclass?** IRInstruction is currently a Pydantic BaseModel for serialization.~~ **Resolved:** IRInstruction will be deleted entirely. Typed instructions are plain frozen dataclasses. Serialization moves to explicit methods if needed.

3. **`__str__` format**: Each typed instruction needs a `__str__` that matches the current `IRInstruction.__str__` output for test compatibility and debugging. **Status:** Implemented via `to_flat()` delegation. Will become standalone after IRInstruction removal.

4. **Naming conflicts**: `Return`, `Label` are Python builtins/keywords. Use `Return_`, `Label_`. **Status:** Done.
