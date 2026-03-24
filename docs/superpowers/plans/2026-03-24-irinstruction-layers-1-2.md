# IRInstruction Elimination — Layers 1 & 2 Implementation Plan

> **Status: COMPLETED** (2026-03-24). All tasks executed via subagent-driven development. See commits `4e06a96` (Layer 1), `82775c6` (Layer 2a), `f238014` (Layer 2b).

**Goal:** Make all register-holding fields in typed instruction classes carry `Register` objects (Layer 1), then add generic `map_registers()`/`map_labels()` transformation methods to `InstructionBase` (Layer 2).

**Architecture:** Layer 1 changes field types from `str` to `Register` in `instructions.py` and `SpreadArguments` in `ir.py`. The `Register.__eq__(str)` bridge keeps all existing consumers working without changes. Layer 2 adds field-introspecting transformation methods using `dataclasses.fields()` + `dataclasses.replace()`, enabling generic register/label rewrites.

**Tech Stack:** Python 3.13+, pytest, dataclasses, Poetry

**Design doc:** `docs/design/eliminate-irinstruction-plan.md`
**Issues:** red-dragon-e2pj (Layer 1), red-dragon-p72n (Layer 2)

---

## Task 1: Layer 1 — Change register field types (instructions.py)

**Files:**
- Modify: `interpreter/instructions.py` (all 31 instruction dataclasses)
- Modify: `interpreter/ir.py:14-18` (SpreadArguments)
- Test: `tests/unit/test_typed_instructions.py` (existing round-trip tests)

### Field changes

Every field that holds a register reference changes from `str` to `Register`.
Fields that hold variable names, operators, function names, type hints, or continuation names stay as `str`.

- [ ] **Step 1: Change `SpreadArguments.register` in `ir.py`**

```python
# interpreter/ir.py — SpreadArguments
@dataclass(frozen=True)
class SpreadArguments:
    """Marks a call operand as spread — the VM unpacks the heap array into individual args."""

    register: Register  # was: str

    def __str__(self) -> str:
        return f"*{self.register}"
```

Add `Register` to the imports from `interpreter.register`.

- [ ] **Step 2: Change all register fields in instruction classes**

Apply these changes to `interpreter/instructions.py`. The table below lists every field that changes:

| Class | Field | Old type | New type | Default |
|-------|-------|----------|----------|---------|
| DeclVar | value_reg | `str` | `Register` | `NO_REGISTER` |
| StoreVar | value_reg | `str` | `Register` | `NO_REGISTER` |
| Binop | left | `str` | `Register` | `NO_REGISTER` |
| Binop | right | `str` | `Register` | `NO_REGISTER` |
| Unop | operand | `str` | `Register` | `NO_REGISTER` |
| CallFunction | args | `tuple[str \| SpreadArguments, ...]` | `tuple[Register \| SpreadArguments, ...]` | `()` |
| CallMethod | obj_reg | `str` | `Register` | `NO_REGISTER` |
| CallMethod | args | `tuple[str \| SpreadArguments, ...]` | `tuple[Register \| SpreadArguments, ...]` | `()` |
| CallUnknown | target_reg | `str` | `Register` | `NO_REGISTER` |
| CallUnknown | args | `tuple[str \| SpreadArguments, ...]` | `tuple[Register \| SpreadArguments, ...]` | `()` |
| LoadField | obj_reg | `str` | `Register` | `NO_REGISTER` |
| StoreField | obj_reg | `str` | `Register` | `NO_REGISTER` |
| StoreField | value_reg | `str` | `Register` | `NO_REGISTER` |
| LoadFieldIndirect | obj_reg | `str` | `Register` | `NO_REGISTER` |
| LoadFieldIndirect | name_reg | `str` | `Register` | `NO_REGISTER` |
| LoadIndex | arr_reg | `str` | `Register` | `NO_REGISTER` |
| LoadIndex | index_reg | `str` | `Register` | `NO_REGISTER` |
| StoreIndex | arr_reg | `str` | `Register` | `NO_REGISTER` |
| StoreIndex | index_reg | `str` | `Register` | `NO_REGISTER` |
| StoreIndex | value_reg | `str` | `Register` | `NO_REGISTER` |
| LoadIndirect | ptr_reg | `str` | `Register` | `NO_REGISTER` |
| StoreIndirect | ptr_reg | `str` | `Register` | `NO_REGISTER` |
| StoreIndirect | value_reg | `str` | `Register` | `NO_REGISTER` |
| NewArray | size_reg | `str` | `Register` | `NO_REGISTER` |
| BranchIf | cond_reg | `str` | `Register` | `NO_REGISTER` |
| Return_ | value_reg | `str \| None` | `Register \| None` | `None` |
| Throw_ | value_reg | `str \| None` | `Register \| None` | `None` |
| AllocRegion | size_reg | `str` | `Register` | `NO_REGISTER` |
| LoadRegion | region_reg | `str` | `Register` | `NO_REGISTER` |
| LoadRegion | offset_reg | `str` | `Register` | `NO_REGISTER` |
| WriteRegion | region_reg | `str` | `Register` | `NO_REGISTER` |
| WriteRegion | offset_reg | `str` | `Register` | `NO_REGISTER` |
| WriteRegion | value_reg | `str` | `Register` | `NO_REGISTER` |

Fields that **stay as `str`** (not registers): `Const.value`, `LoadVar.name`, `DeclVar.name`, `StoreVar.name`, `Symbolic.hint`, `Binop.operator`, `Unop.operator`, `CallFunction.func_name`, `CallMethod.method_name`, `LoadField.field_name`, `StoreField.field_name`, `NewObject.type_hint`, `NewArray.type_hint`, `AddressOf.var_name`, `SetContinuation.name`, `ResumeContinuation.name`.

Example — `DeclVar` before:
```python
@dataclass(frozen=True)
class DeclVar(InstructionBase):
    name: str = ""
    value_reg: str = ""
    # ...
```

After:
```python
@dataclass(frozen=True)
class DeclVar(InstructionBase):
    name: str = ""
    value_reg: Register = NO_REGISTER
    # ...
```

Example — `Binop` before:
```python
@dataclass(frozen=True)
class Binop(InstructionBase):
    result_reg: Register = NO_REGISTER
    operator: str = ""
    left: str = ""
    right: str = ""
```

After:
```python
@dataclass(frozen=True)
class Binop(InstructionBase):
    result_reg: Register = NO_REGISTER
    operator: str = ""
    left: Register = NO_REGISTER
    right: Register = NO_REGISTER
```

- [ ] **Step 3: Update `operands` properties to `str()` Register values**

Every `operands` property that returns register values must wrap them with `str()` for backward compatibility. This ensures consumers reading `inst.operands[N]` still get strings.

Example — `DeclVar.operands` before:
```python
@property
def operands(self) -> list[Any]:
    return [self.name, self.value_reg]
```

After:
```python
@property
def operands(self) -> list[Any]:
    return [self.name, str(self.value_reg)]
```

Example — `Binop.operands` before:
```python
@property
def operands(self) -> list[Any]:
    return [self.operator, self.left, self.right]
```

After:
```python
@property
def operands(self) -> list[Any]:
    return [self.operator, str(self.left), str(self.right)]
```

Example — `CallFunction.operands` (args contain Register and SpreadArguments):
```python
@property
def operands(self) -> list[Any]:
    return [self.func_name, *(str(a) if isinstance(a, Register) else a for a in self.args)]
```

Example — `Return_.operands` (Register | None):
```python
@property
def operands(self) -> list[Any]:
    return [str(self.value_reg)] if self.value_reg is not None else []
```

Full list of `operands` properties that need `str()` wrapping:
- `DeclVar`: `str(self.value_reg)`
- `StoreVar`: `str(self.value_reg)`
- `Binop`: `str(self.left)`, `str(self.right)`
- `Unop`: `str(self.operand)`
- `CallFunction`: `str()` each Register in args
- `CallMethod`: `str(self.obj_reg)`, `str()` each Register in args
- `CallUnknown`: `str(self.target_reg)`, `str()` each Register in args
- `LoadField`: `str(self.obj_reg)`
- `StoreField`: `str(self.obj_reg)`, `str(self.value_reg)`
- `LoadFieldIndirect`: `str(self.obj_reg)`, `str(self.name_reg)`
- `LoadIndex`: `str(self.arr_reg)`, `str(self.index_reg)`
- `StoreIndex`: `str(self.arr_reg)`, `str(self.index_reg)`, `str(self.value_reg)`
- `LoadIndirect`: `str(self.ptr_reg)`
- `StoreIndirect`: `str(self.ptr_reg)`, `str(self.value_reg)`
- `NewArray`: `str(self.size_reg)`
- `BranchIf`: `str(self.cond_reg)`
- `Return_`: `str(self.value_reg)` when not None
- `Throw_`: `str(self.value_reg)` when not None
- `AllocRegion`: `str(self.size_reg)`
- `LoadRegion`: `str(self.region_reg)`, `str(self.offset_reg)`
- `WriteRegion`: `str(self.region_reg)`, `str(self.offset_reg)`, `str(self.value_reg)`

- [ ] **Step 4: Update `to_typed()` converters to wrap operand strings as `Register`**

Each `_to_typed` converter that reads register-valued operands must wrap them with `Register(...)`. Non-register operands (names, operators, hints) stay as-is.

Example — `_binop` before:
```python
def _binop(inst: IRInstruction) -> Binop:
    ops = inst.operands
    return Binop(
        result_reg=inst.result_reg,
        operator=str(ops[0]) if len(ops) >= 1 else "",
        left=str(ops[1]) if len(ops) >= 2 else "",
        right=str(ops[2]) if len(ops) >= 3 else "",
        source_location=inst.source_location,
    )
```

After:
```python
def _binop(inst: IRInstruction) -> Binop:
    ops = inst.operands
    return Binop(
        result_reg=inst.result_reg,
        operator=str(ops[0]) if len(ops) >= 1 else "",
        left=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        right=Register(str(ops[2])) if len(ops) >= 3 else NO_REGISTER,
        source_location=inst.source_location,
    )
```

Example — `_decl_var` before:
```python
def _decl_var(inst: IRInstruction) -> DeclVar:
    ops = inst.operands
    return DeclVar(
        name=str(ops[0]) if len(ops) >= 1 else "",
        value_reg=str(ops[1]) if len(ops) >= 2 else "",
        source_location=inst.source_location,
    )
```

After:
```python
def _decl_var(inst: IRInstruction) -> DeclVar:
    ops = inst.operands
    return DeclVar(
        name=str(ops[0]) if len(ops) >= 1 else "",
        value_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )
```

Example — `_call_function` (args contain mixed Register/SpreadArguments):
```python
def _call_function(inst: IRInstruction) -> CallFunction:
    ops = inst.operands
    raw_args = ops[1:]
    args = tuple(
        a if isinstance(a, SpreadArguments) else Register(str(a))
        for a in raw_args
    )
    return CallFunction(
        result_reg=inst.result_reg,
        func_name=str(ops[0]) if ops else "",
        args=args,
        source_location=inst.source_location,
    )
```

Example — `_return` (Register | None):
```python
def _return(inst: IRInstruction) -> Return_:
    return Return_(
        value_reg=Register(str(inst.operands[0])) if inst.operands else None,
        source_location=inst.source_location,
    )
```

Full list of converters needing `Register(...)` wrapping:
- `_decl_var`: `value_reg`
- `_store_var`: `value_reg`
- `_binop`: `left`, `right`
- `_unop`: `operand`
- `_call_function`: each non-SpreadArguments element in args
- `_call_method`: `obj_reg`, each non-SpreadArguments element in args
- `_call_unknown`: `target_reg`, each non-SpreadArguments element in args
- `_load_field`: `obj_reg`
- `_store_field`: `obj_reg`, `value_reg`
- `_load_field_indirect`: `obj_reg`, `name_reg`
- `_load_index`: `arr_reg`, `index_reg`
- `_store_index`: `arr_reg`, `index_reg`, `value_reg`
- `_load_indirect`: `ptr_reg`
- `_store_indirect`: `ptr_reg`, `value_reg`
- `_new_array`: `size_reg`
- `_branch_if`: `cond_reg`
- `_return`: `value_reg`
- `_throw`: `value_reg`
- `_alloc_region`: `size_reg`
- `_load_region`: `region_reg`, `offset_reg`
- `_write_region`: `region_reg`, `offset_reg`, `value_reg`

- [ ] **Step 5: Update `to_flat()` converters to `str()` Register values back**

Each `_flat_*` converter that passes register fields into `IRInstruction.operands` must `str()` them. Most already work because `Register.__str__` returns the name, but be explicit for the `operands=[...]` lists.

Example — `_flat_binop` before:
```python
def _flat_binop(t: Binop) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.BINOP,
        result_reg=t.result_reg,
        operands=[t.operator, t.left, t.right],
        source_location=t.source_location,
    )
```

After:
```python
def _flat_binop(t: Binop) -> IRInstruction:
    return IRInstruction(
        opcode=Opcode.BINOP,
        result_reg=t.result_reg,
        operands=[t.operator, str(t.left), str(t.right)],
        source_location=t.source_location,
    )
```

Apply the same `str()` wrapping to all register-valued fields in `to_flat` converters. The pattern is identical: any field that changed from `str` to `Register` in Step 2 gets `str()` in the `to_flat` converter.

- [ ] **Step 6: Run round-trip tests**

Run: `poetry run python -m pytest tests/unit/test_typed_instructions.py -v`
Expected: All tests PASS. The round-trip `to_typed(inst).to_flat()` must produce equivalent instructions.

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All ~12,629 tests PASS. `Register.__eq__(str)` ensures all existing comparisons work.

- [ ] **Step 8: Run verification gate**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
```

- [ ] **Step 9: Commit**

```bash
bd update e2pj --claim
bd backup
git add interpreter/instructions.py interpreter/ir.py
git commit -m "Layer 1: Register fields in instruction classes — str → Register"
bd close e2pj --reason "All register-holding fields now carry Register objects"
```

---

## Task 2: Layer 2 — `Register.rebase()` method

**Files:**
- Modify: `interpreter/register.py:9-39`
- Test: `tests/unit/test_register_rebase.py` (new)

- [ ] **Step 1: Write failing tests for `Register.rebase()`**

Create `tests/unit/test_register_rebase.py`:

```python
"""Tests for Register.rebase() — offset numeric suffix in register names."""

from interpreter.register import Register, NO_REGISTER


class TestRegisterRebase:
    def test_simple_rebase(self):
        reg = Register("%r0")
        assert reg.rebase(100) == Register("%r100")

    def test_rebase_nonzero(self):
        reg = Register("%r5")
        assert reg.rebase(10) == Register("%r15")

    def test_rebase_zero_offset(self):
        reg = Register("%r42")
        assert reg.rebase(0) == Register("%r42")

    def test_rebase_non_numeric_suffix(self):
        """Non-numeric register names are returned unchanged."""
        reg = Register("%tmp")
        assert reg.rebase(100) == Register("%tmp")

    def test_rebase_no_prefix(self):
        """Register names without % prefix still rebase."""
        reg = Register("r5")
        assert reg.rebase(10) == Register("r15")

    def test_no_register_rebase(self):
        """NO_REGISTER.rebase() returns NO_REGISTER."""
        assert NO_REGISTER.rebase(100) is NO_REGISTER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_register_rebase.py -v`
Expected: FAIL — `Register` has no `rebase` method.

- [ ] **Step 3: Implement `Register.rebase()`**

Add to `Register` class in `interpreter/register.py`:

```python
import re

def rebase(self, offset: int) -> Register:
    """Offset the numeric suffix: %r5.rebase(10) → %r15."""
    match = re.match(r"^(.*?)(\d+)$", self.name)
    if not match:
        return self
    prefix, num = match.group(1), int(match.group(2))
    return Register(f"{prefix}{num + offset}")
```

Add to `NoRegister` class:

```python
def rebase(self, offset: int) -> Register:
    return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_register_rebase.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit rebase method**

```bash
bd backup
git add interpreter/register.py tests/unit/test_register_rebase.py
git commit -m "Layer 2a: Register.rebase(offset) method"
```

---

## Task 3: Layer 2 — `InstructionBase.map_registers()` and `map_labels()`

**Files:**
- Modify: `interpreter/instructions.py:30-38` (InstructionBase class)
- Test: `tests/unit/test_map_registers_labels.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_map_registers_labels.py`:

```python
"""Tests for InstructionBase.map_registers() and map_labels()."""

from interpreter.instructions import (
    Binop, BranchIf, CallFunction, CallMethod, Const, DeclVar,
    Label_, LoadField, Return_, StoreField, StoreVar, TryPush,
    Branch, NewArray, AllocRegion, WriteRegion, LoadRegion,
    StoreIndex, LoadIndex, CallUnknown, LoadFieldIndirect,
    LoadIndirect, StoreIndirect, AddressOf, Unop, Throw_,
    SetContinuation, ResumeContinuation, TryPop, Symbolic,
    NewObject, LoadVar,
)
from interpreter.ir import CodeLabel, NO_LABEL, SpreadArguments
from interpreter.register import Register, NO_REGISTER


def _inc(reg: Register) -> Register:
    """Test helper: increment register number by 100."""
    return reg.rebase(100)


def _ns(label: CodeLabel) -> CodeLabel:
    """Test helper: namespace a label."""
    return label.namespace("mod")


class TestMapRegisters:
    def test_binop(self):
        inst = Binop(result_reg=Register("%r0"), operator="+",
                     left=Register("%r1"), right=Register("%r2"))
        mapped = inst.map_registers(_inc)
        assert mapped.result_reg == Register("%r100")
        assert mapped.left == Register("%r101")
        assert mapped.right == Register("%r102")
        assert mapped.operator == "+"  # not a register — unchanged

    def test_decl_var(self):
        inst = DeclVar(name="x", value_reg=Register("%r0"))
        mapped = inst.map_registers(_inc)
        assert mapped.value_reg == Register("%r100")
        assert mapped.name == "x"  # not a register — unchanged

    def test_call_function_with_spread(self):
        inst = CallFunction(
            result_reg=Register("%r0"), func_name="f",
            args=(Register("%r1"), SpreadArguments(register=Register("%r2")), Register("%r3")),
        )
        mapped = inst.map_registers(_inc)
        assert mapped.result_reg == Register("%r100")
        assert mapped.args[0] == Register("%r101")
        assert isinstance(mapped.args[1], SpreadArguments)
        assert mapped.args[1].register == Register("%r102")
        assert mapped.args[2] == Register("%r103")

    def test_return_with_value(self):
        inst = Return_(value_reg=Register("%r5"))
        mapped = inst.map_registers(_inc)
        assert mapped.value_reg == Register("%r105")

    def test_return_void(self):
        inst = Return_(value_reg=None)
        mapped = inst.map_registers(_inc)
        assert mapped.value_reg is None

    def test_no_register_unchanged(self):
        inst = Label_(label=CodeLabel("entry"))
        mapped = inst.map_registers(_inc)
        assert mapped.label == CodeLabel("entry")  # labels not affected

    def test_const_value_not_touched(self):
        inst = Const(result_reg=Register("%r0"), value="42")
        mapped = inst.map_registers(_inc)
        assert mapped.result_reg == Register("%r100")
        assert mapped.value == "42"  # str field — not a register

    def test_store_field(self):
        inst = StoreField(obj_reg=Register("%r0"), field_name="x",
                          value_reg=Register("%r1"))
        mapped = inst.map_registers(_inc)
        assert mapped.obj_reg == Register("%r100")
        assert mapped.value_reg == Register("%r101")
        assert mapped.field_name == "x"

    def test_write_region(self):
        inst = WriteRegion(region_reg=Register("%r0"), offset_reg=Register("%r1"),
                           length=8, value_reg=Register("%r2"))
        mapped = inst.map_registers(_inc)
        assert mapped.region_reg == Register("%r100")
        assert mapped.offset_reg == Register("%r101")
        assert mapped.value_reg == Register("%r102")
        assert mapped.length == 8  # int field — unchanged


class TestMapLabels:
    def test_label(self):
        inst = Label_(label=CodeLabel("entry"))
        mapped = inst.map_labels(_ns)
        assert mapped.label == CodeLabel("mod.entry")

    def test_branch(self):
        inst = Branch(label=CodeLabel("L_end"))
        mapped = inst.map_labels(_ns)
        assert mapped.label == CodeLabel("mod.L_end")

    def test_branch_if(self):
        inst = BranchIf(
            cond_reg=Register("%r0"),
            branch_targets=(CodeLabel("L_true"), CodeLabel("L_false")),
        )
        mapped = inst.map_labels(_ns)
        assert mapped.branch_targets == (CodeLabel("mod.L_true"), CodeLabel("mod.L_false"))
        assert mapped.cond_reg == Register("%r0")  # registers unchanged

    def test_try_push(self):
        inst = TryPush(
            catch_labels=(CodeLabel("catch_0"),),
            finally_label=CodeLabel("finally_0"),
            end_label=CodeLabel("end_try"),
        )
        mapped = inst.map_labels(_ns)
        assert mapped.catch_labels == (CodeLabel("mod.catch_0"),)
        assert mapped.finally_label == CodeLabel("mod.finally_0")
        assert mapped.end_label == CodeLabel("mod.end_try")

    def test_set_continuation(self):
        inst = SetContinuation(name="__cont", target_label=CodeLabel("L_resume"))
        mapped = inst.map_labels(_ns)
        assert mapped.target_label == CodeLabel("mod.L_resume")
        assert mapped.name == "__cont"  # str field — unchanged

    def test_no_label_unchanged(self):
        inst = Const(result_reg=Register("%r0"), value="42")
        mapped = inst.map_labels(_ns)
        assert mapped.label == NO_LABEL  # NO_LABEL.namespace() returns self

    def test_binop_no_labels(self):
        inst = Binop(result_reg=Register("%r0"), operator="+",
                     left=Register("%r1"), right=Register("%r2"))
        mapped = inst.map_labels(_ns)
        assert mapped.result_reg == Register("%r0")  # registers unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_map_registers_labels.py -v`
Expected: FAIL — `InstructionBase` has no `map_registers` or `map_labels` method.

- [ ] **Step 3: Implement `map_registers()` and `map_labels()` on `InstructionBase`**

Add to `InstructionBase` in `interpreter/instructions.py`:

```python
import dataclasses
import types
from collections.abc import Callable
from typing import Self, get_type_hints, get_origin, get_args, Union

@dataclass(frozen=True)
class InstructionBase:
    """Shared metadata carried by every instruction."""

    source_location: SourceLocation = field(default_factory=lambda: NO_SOURCE_LOCATION)

    def __str__(self) -> str:
        """Render in the same format as IRInstruction.__str__."""
        return str(to_flat(self))

    def map_registers(self, fn: Callable[[Register], Register]) -> Self:
        """Apply fn to every Register-typed field, return a new instruction."""
        changes: dict[str, object] = {}
        hints = get_type_hints(type(self))
        for f in dataclasses.fields(self):
            hint = hints.get(f.name, f.type)
            val = getattr(self, f.name)
            if isinstance(val, Register):
                changes[f.name] = fn(val)
            elif val is None and _is_optional_register(hint):
                pass  # None stays None
            elif isinstance(val, tuple) and _is_register_args_tuple(hint):
                changes[f.name] = tuple(
                    SpreadArguments(register=fn(a.register))
                    if isinstance(a, SpreadArguments)
                    else fn(a)
                    for a in val
                )
        return dataclasses.replace(self, **changes) if changes else self

    def map_labels(self, fn: Callable[[CodeLabel], CodeLabel]) -> Self:
        """Apply fn to every CodeLabel-typed field, return a new instruction."""
        changes: dict[str, object] = {}
        hints = get_type_hints(type(self))
        for f in dataclasses.fields(self):
            hint = hints.get(f.name, f.type)
            val = getattr(self, f.name)
            if isinstance(val, CodeLabel):
                changes[f.name] = fn(val)
            elif isinstance(val, tuple) and _is_label_tuple(hint):
                changes[f.name] = tuple(fn(lbl) for lbl in val)
        return dataclasses.replace(self, **changes) if changes else self


def _is_union(origin: object) -> bool:
    """Check if origin is a union type (typing.Union or types.UnionType for X | Y syntax)."""
    return origin is Union or origin is types.UnionType


def _is_optional_register(hint: object) -> bool:
    """Check if hint is Register | None."""
    origin = get_origin(hint)
    if _is_union(origin):
        args = get_args(hint)
        return Register in args and type(None) in args
    return False


def _is_register_args_tuple(hint: object) -> bool:
    """Check if hint is tuple[Register | SpreadArguments, ...]."""
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            inner = args[0]
            inner_origin = get_origin(inner)
            if _is_union(inner_origin):
                inner_args = get_args(inner)
                return Register in inner_args and SpreadArguments in inner_args
    return False


def _is_label_tuple(hint: object) -> bool:
    """Check if hint is tuple[CodeLabel, ...]."""
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        return len(args) == 2 and args[0] is CodeLabel and args[1] is Ellipsis
    return False
```

Note: The `Self` type requires `from typing import Self` (Python 3.11+, available in 3.13). The `_is_union` helper handles both `typing.Union` and Python 3.10+ `X | Y` syntax (`types.UnionType`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_map_registers_labels.py -v`
Expected: All PASS.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All tests PASS.

- [ ] **Step 6: Run verification gate**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
```

- [ ] **Step 7: Commit**

```bash
bd update p72n --claim
bd backup
git add interpreter/instructions.py interpreter/register.py tests/unit/test_register_rebase.py tests/unit/test_map_registers_labels.py
git commit -m "Layer 2: map_registers/map_labels on InstructionBase + Register.rebase"
bd close p72n --reason "map_registers, map_labels, and Register.rebase all implemented with tests"
```
