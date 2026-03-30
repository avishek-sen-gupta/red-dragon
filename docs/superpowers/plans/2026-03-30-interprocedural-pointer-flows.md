# Interprocedural Pointer Flow Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix interprocedural analysis to produce correct flows for C pointer-passing programs by handling `STORE_INDIRECT`, `LOAD_INDIRECT`, and `ADDRESS_OF` instructions.

**Architecture:** New `DereferenceEndpoint` type added to the `FlowEndpoint` union. Summary extraction extended with `_build_deref_write_flows()` and `LOAD_INDIRECT` handling in return flows. Propagation extended with `ADDRESS_OF` tracing and `DereferenceEndpoint` substitution (collapses to `VariableEndpoint` at call sites).

**Tech Stack:** Python 3.13+, dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-30-interprocedural-pointer-flows-design.md`

---

### Task 1: Add `DereferenceEndpoint` Type with Tests

**Files:**
- Modify: `interpreter/interprocedural/types.py:70-99`
- Modify: `tests/unit/test_interprocedural_types.py`

- [ ] **Step 1: Write failing tests for DereferenceEndpoint**

Append to `tests/unit/test_interprocedural_types.py`, inside the existing `TestFlowEndpoints` class (after the `test_flow_endpoint_isinstance_checks` method at line ~209):

```python
    def test_dereference_endpoint_construction(self):
        base = VariableEndpoint(name="p", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=4)
        de = DereferenceEndpoint(base=base, location=loc)
        assert de.base.name == "p"
        assert de.location == loc

    def test_dereference_endpoint_hashable(self):
        base = VariableEndpoint(name="p", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=4)
        de1 = DereferenceEndpoint(base=base, location=loc)
        de2 = DereferenceEndpoint(base=base, location=loc)
        s = {de1, de2}
        assert len(s) == 1

    def test_dereference_endpoint_equality(self):
        base = VariableEndpoint(name="p", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=4)
        de1 = DereferenceEndpoint(base=base, location=loc)
        de2 = DereferenceEndpoint(base=base, location=loc)
        assert de1 == de2

    def test_dereference_endpoint_inequality_different_base(self):
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=4)
        de1 = DereferenceEndpoint(
            base=VariableEndpoint(name="p", definition=NO_DEFINITION), location=loc
        )
        de2 = DereferenceEndpoint(
            base=VariableEndpoint(name="q", definition=NO_DEFINITION), location=loc
        )
        assert de1 != de2

    def test_dereference_endpoint_in_flow_endpoint_union(self):
        base = VariableEndpoint(name="p", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("entry"), instruction_index=4)
        de: FlowEndpoint = DereferenceEndpoint(base=base, location=loc)
        assert isinstance(
            de, VariableEndpoint | FieldEndpoint | ReturnEndpoint | DereferenceEndpoint
        )
```

Also add `DereferenceEndpoint` to the imports at the top of the file:

```python
from interpreter.interprocedural.types import (
    ...
    DereferenceEndpoint,
    ...
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_types.py::TestFlowEndpoints::test_dereference_endpoint_construction -v`
Expected: FAIL — `ImportError: cannot import name 'DereferenceEndpoint'`

- [ ] **Step 3: Implement DereferenceEndpoint**

In `interpreter/interprocedural/types.py`, add after `ReturnEndpoint` (line 97) and before the `FlowEndpoint` union (line 99):

```python
@dataclass(frozen=True)
class DereferenceEndpoint:
    """A pointer dereference (*ptr) — read or write through a pointer variable."""

    base: VariableEndpoint
    location: InstructionLocation

    def __hash__(self) -> int:
        return hash((self.base, self.location))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DereferenceEndpoint):
            return NotImplemented
        return self.base == other.base and self.location == other.location
```

Update the `FlowEndpoint` union:

```python
FlowEndpoint = Union[VariableEndpoint, FieldEndpoint, ReturnEndpoint, DereferenceEndpoint]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_types.py -v`
Expected: All tests PASS (existing + 5 new)

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/interprocedural/types.py tests/unit/test_interprocedural_types.py
git commit -m "Add DereferenceEndpoint to interprocedural FlowEndpoint union

New frozen dataclass representing pointer dereference (*ptr) operations,
for both read and write through pointer variables. Extends FlowEndpoint
union used by summary extraction and propagation."
```

---

### Task 2: Add `_build_deref_write_flows()` for STORE_INDIRECT

**Files:**
- Modify: `interpreter/interprocedural/summaries.py`
- Create: `tests/unit/test_interprocedural_summaries.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_interprocedural_summaries.py`:

```python
"""Unit tests for interprocedural summary extraction — pointer dereference flows."""

from __future__ import annotations

from interpreter.cfg_types import BasicBlock, CFG
from interpreter.constants import PARAM_PREFIX
from interpreter.dataflow import Definition
from interpreter.ir import CodeLabel
from interpreter.register import Register, NO_REGISTER
from interpreter.var_name import VarName
from interpreter.instructions import (
    Const,
    DeclVar,
    LoadVar,
    Return_,
    StoreIndirect,
    Symbolic,
)
from interpreter.interprocedural.summaries import build_summary
from interpreter.interprocedural.types import (
    CallContext,
    DereferenceEndpoint,
    FunctionEntry,
    ROOT_CONTEXT,
    VariableEndpoint,
)


def _build_set_val_cfg() -> tuple[CFG, FunctionEntry]:
    """Build CFG for: void set_val(int *p) { *p = 99; }

    IR:
      SYMBOLIC %0 param:p
      DECL_VAR p, %0
      CONST %1, 99
      LOAD_VAR %2, p
      STORE_INDIRECT %2, %1   # *p = 99
      CONST %3, 0
      RETURN %3
    """
    instructions = [
        Symbolic(result_reg=Register("%0"), hint=f"{PARAM_PREFIX}p"),
        DeclVar(name=VarName("p"), value_reg=Register("%0")),
        Const(result_reg=Register("%1"), operands=["99"]),
        LoadVar(result_reg=Register("%2"), name=VarName("p")),
        StoreIndirect(ptr_reg=Register("%2"), value_reg=Register("%1")),
        Const(result_reg=Register("%3"), operands=["0"]),
        Return_(value_reg=Register("%3")),
    ]
    block = BasicBlock(
        label=CodeLabel("func_set_val_0"),
        instructions=instructions,
        successors=[],
        predecessors=[],
    )
    cfg = CFG(
        blocks={CodeLabel("func_set_val_0"): block},
        entry=CodeLabel("func_set_val_0"),
    )
    entry = FunctionEntry(label=CodeLabel("func_set_val_0"), params=("p",))
    return cfg, entry


class TestStoreIndirectSummary:
    def test_set_val_produces_deref_write_flow(self):
        """*p = 99 should produce VariableEndpoint(p) -> DereferenceEndpoint(p)."""
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        assert len(summary.flows) > 0, "Expected at least one flow for *p = 99"

    def test_set_val_flow_source_is_param_p(self):
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        sources = {src for src, _ in summary.flows}
        source_names = {s.name for s in sources if isinstance(s, VariableEndpoint)}
        assert "p" in source_names, f"Expected param 'p' as flow source, got {source_names}"

    def test_set_val_flow_destination_is_deref_endpoint(self):
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        destinations = {dst for _, dst in summary.flows}
        deref_dsts = [d for d in destinations if isinstance(d, DereferenceEndpoint)]
        assert len(deref_dsts) > 0, f"Expected DereferenceEndpoint destination, got {destinations}"

    def test_set_val_deref_endpoint_base_is_param_p(self):
        cfg, entry = _build_set_val_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        deref_dsts = [
            dst for _, dst in summary.flows if isinstance(dst, DereferenceEndpoint)
        ]
        assert len(deref_dsts) > 0
        assert deref_dsts[0].base.name == "p"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_summaries.py -v`
Expected: FAIL — `test_set_val_produces_deref_write_flow` fails with `assert 0 > 0`

- [ ] **Step 3: Implement `_build_deref_write_flows()`**

In `interpreter/interprocedural/summaries.py`:

Add imports:
```python
from interpreter.instructions import (
    DeclVar,
    StoreVar,
    Symbolic,
    Return_,
    StoreField,
    LoadField,
    LoadVar,
    StoreIndirect,
    LoadIndirect,
)
from interpreter.interprocedural.types import (
    ...
    DereferenceEndpoint,
)
```

Add new helper function after `_find_store_fields()` (around line 158):

```python
def _find_store_indirects(cfg: CFG) -> list[tuple[CodeLabel, int, str, str]]:
    """Find all STORE_INDIRECT instructions.

    Returns list of (block_label, instruction_index, ptr_reg, value_reg).
    """
    return [
        (label, idx, str(t.ptr_reg), str(t.value_reg))
        for label, block in cfg.blocks.items()
        for idx, inst in enumerate(block.instructions)
        if isinstance((t := inst), StoreIndirect)
    ]
```

Add new flow builder after `_build_field_write_flows()` (around line 394):

```python
def _build_deref_write_flows(
    cfg: CFG,
    dataflow: DataflowResult,
    param_names: frozenset[VarName],
) -> list[tuple[FlowEndpoint, FlowEndpoint]]:
    """Build flows from params to STORE_INDIRECT instructions (pointer dereference writes)."""
    store_indirects = _find_store_indirects(cfg)
    flows: list[tuple[FlowEndpoint, FlowEndpoint]] = []

    for si_label, si_idx, si_ptr_reg, si_val_reg in store_indirects:
        location = InstructionLocation(block_label=si_label, instruction_index=si_idx)

        # Find which named variable the pointer register was loaded from
        ptr_var = _find_register_source_var(si_ptr_reg, cfg)
        if ptr_var is None or ptr_var not in param_names:
            continue

        ptr_endpoint = _make_var_endpoint(ptr_var, dataflow)
        deref_endpoint = DereferenceEndpoint(base=ptr_endpoint, location=location)

        # Always: param controls the dereference write target
        flows.append((ptr_endpoint, deref_endpoint))

        # If value also traces to a param, add that flow too
        val_var = _find_register_source_var(si_val_reg, cfg)
        if val_var is not None and val_var in param_names and val_var != ptr_var:
            flows.append((_make_var_endpoint(val_var, dataflow), deref_endpoint))
        elif val_var is not None and val_var not in param_names:
            # Check transitive deps
            param_deps = _trace_register_to_params(
                val_var,
                dataflow.dependency_graph,
                dataflow.raw_dependency_graph,
                param_names,
            )
            flows.extend(
                (_make_var_endpoint(p, dataflow), deref_endpoint)
                for p in param_deps
                if p != ptr_var
            )

    return flows
```

Update `build_summary()` to call the new function (around line 415):

```python
    return_flows = _build_return_flows(sub_cfg, dataflow, param_names, function_entry)
    field_write_flows = _build_field_write_flows(sub_cfg, dataflow, param_names)
    deref_write_flows = _build_deref_write_flows(sub_cfg, dataflow, param_names)

    all_flows = frozenset(return_flows + field_write_flows + deref_write_flows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_summaries.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/interprocedural/summaries.py tests/unit/test_interprocedural_summaries.py
git commit -m "Handle STORE_INDIRECT in interprocedural summary extraction

Add _build_deref_write_flows() that scans for STORE_INDIRECT instructions
and produces VariableEndpoint(ptr_param) -> DereferenceEndpoint(ptr_param)
flows. Fixes the core issue where *p = val produced 0 flows."
```

---

### Task 3: Handle `LOAD_INDIRECT` in Return Flows

**Files:**
- Modify: `interpreter/interprocedural/summaries.py:270-318`
- Modify: `tests/unit/test_interprocedural_summaries.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_interprocedural_summaries.py`:

```python
def _build_deref_return_cfg() -> tuple[CFG, FunctionEntry]:
    """Build CFG for: int deref(int *p) { return *p; }

    IR:
      SYMBOLIC %0 param:p
      DECL_VAR p, %0
      LOAD_VAR %1, p
      LOAD_INDIRECT %2, %1   # %2 = *p
      RETURN %2
    """
    from interpreter.instructions import LoadIndirect

    instructions = [
        Symbolic(result_reg=Register("%0"), hint=f"{PARAM_PREFIX}p"),
        DeclVar(name=VarName("p"), value_reg=Register("%0")),
        LoadVar(result_reg=Register("%1"), name=VarName("p")),
        LoadIndirect(result_reg=Register("%2"), ptr_reg=Register("%1")),
        Return_(value_reg=Register("%2")),
    ]
    block = BasicBlock(
        label=CodeLabel("func_deref_0"),
        instructions=instructions,
        successors=[],
        predecessors=[],
    )
    cfg = CFG(
        blocks={CodeLabel("func_deref_0"): block},
        entry=CodeLabel("func_deref_0"),
    )
    entry = FunctionEntry(label=CodeLabel("func_deref_0"), params=("p",))
    return cfg, entry


class TestLoadIndirectReturnFlow:
    def test_deref_return_produces_flow(self):
        """return *p should produce DereferenceEndpoint(p) -> ReturnEndpoint."""
        cfg, entry = _build_deref_return_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        assert len(summary.flows) > 0, "Expected at least one flow for return *p"

    def test_deref_return_source_is_deref_endpoint(self):
        cfg, entry = _build_deref_return_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        sources = {src for src, _ in summary.flows}
        deref_srcs = [s for s in sources if isinstance(s, DereferenceEndpoint)]
        assert len(deref_srcs) > 0, f"Expected DereferenceEndpoint source, got {sources}"
        assert deref_srcs[0].base.name == "p"

    def test_deref_return_destination_is_return_endpoint(self):
        from interpreter.interprocedural.types import ReturnEndpoint

        cfg, entry = _build_deref_return_cfg()
        summary = build_summary(cfg, entry, ROOT_CONTEXT)
        destinations = {dst for _, dst in summary.flows}
        ret_dsts = [d for d in destinations if isinstance(d, ReturnEndpoint)]
        assert len(ret_dsts) > 0, f"Expected ReturnEndpoint destination, got {destinations}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_summaries.py::TestLoadIndirectReturnFlow -v`
Expected: FAIL — `assert 0 > 0` (no flows produced)

- [ ] **Step 3: Extend `_build_return_flows()` for LOAD_INDIRECT**

In `interpreter/interprocedural/summaries.py`, in `_build_return_flows()` (line 270), add a new check in the `else` branch (line 310-316) where the return operand comes from a computation. The current code uses `_trace_register_to_source_vars` which walks backward through operands. We need to also check if the return operand was produced by `LOAD_INDIRECT`:

Add after line 309 (after the field-to-return flow check), before the `else` on line 310:

Actually, the cleanest approach is to add a new block before the existing `_trace_register_to_source_vars` fallback. In the return flow builder, after line 288 (`source_var = _find_register_source_var(ret_operand, cfg)`), add a check for LOAD_INDIRECT:

```python
        # Check if return operand was produced by LOAD_INDIRECT (dereference read)
        deref_source = _find_load_indirect_source(ret_operand, cfg)
        if deref_source is not None:
            ptr_var = _find_register_source_var(deref_source, cfg)
            if ptr_var is not None and ptr_var in param_names:
                deref_loc = _find_instruction_location(ret_operand, cfg, LoadIndirect)
                if deref_loc is not None:
                    deref_endpoint = DereferenceEndpoint(
                        base=_make_var_endpoint(ptr_var, dataflow),
                        location=deref_loc,
                    )
                    flows.append((deref_endpoint, ret_endpoint))
                    continue
```

Add two helper functions before `_build_return_flows()`:

```python
def _find_load_indirect_source(register: str, cfg: CFG) -> str | None:
    """If register was produced by LOAD_INDIRECT, return the ptr_reg. Else None."""
    for block in cfg.blocks.values():
        for inst in block.instructions:
            if isinstance(inst, LoadIndirect) and str(inst.result_reg) == register:
                return str(inst.ptr_reg)
    return None


def _find_instruction_location(
    result_register: str, cfg: CFG, inst_type: type
) -> InstructionLocation | None:
    """Find the location of an instruction that produces a given register."""
    for label, block in cfg.blocks.items():
        for idx, inst in enumerate(block.instructions):
            if isinstance(inst, inst_type) and str(inst.result_reg) == result_register:
                return InstructionLocation(block_label=label, instruction_index=idx)
    return None
```

**Important:** The `continue` in the LOAD_INDIRECT check ensures we don't fall through to the existing LOAD_VAR-based tracing, which would fail to find the source variable (since LOAD_INDIRECT doesn't produce a named variable).

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_summaries.py -v`
Expected: All 7 tests PASS (4 from Task 2 + 3 new)

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/interprocedural/summaries.py tests/unit/test_interprocedural_summaries.py
git commit -m "Handle LOAD_INDIRECT in interprocedural return flow extraction

When a return operand was produced by LOAD_INDIRECT (pointer dereference
read), create DereferenceEndpoint(ptr_param) -> ReturnEndpoint flow.
Enables tracking of 'return *p' patterns."
```

---

### Task 4: Handle `ADDRESS_OF` in Argument Tracing + `DereferenceEndpoint` Substitution

**Files:**
- Modify: `interpreter/interprocedural/propagation.py:150-205`
- Create: `tests/unit/test_interprocedural_propagation.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_interprocedural_propagation.py`:

```python
"""Unit tests for interprocedural propagation — ADDRESS_OF tracing and DereferenceEndpoint substitution."""

from __future__ import annotations

from interpreter.cfg_types import BasicBlock, CFG
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.instructions import (
    AddressOf,
    CallFunction,
    Const,
    DeclVar,
    LoadVar,
)
from interpreter.interprocedural.propagation import (
    _trace_reg_to_var,
    _substitute_endpoint,
    apply_summary_at_call_site,
)
from interpreter.interprocedural.types import (
    CallSite,
    DereferenceEndpoint,
    FunctionEntry,
    FunctionSummary,
    InstructionLocation,
    NO_DEFINITION,
    ROOT_CONTEXT,
    VariableEndpoint,
)


def _build_caller_cfg_with_address_of() -> CFG:
    """Build CFG for caller: int x = 10; set_val(&x);

    IR:
      CONST %5, 10
      DECL_VAR x, %5
      ADDRESS_OF %6, x
      CALL_FUNCTION %7, set_val, %6
    """
    instructions = [
        Const(result_reg=Register("%5"), operands=["10"]),
        DeclVar(name=VarName("x"), value_reg=Register("%5")),
        AddressOf(result_reg=Register("%6"), var_name=VarName("x")),
        CallFunction(
            result_reg=Register("%7"),
            func_name="set_val",
            args=[Register("%6")],
        ),
    ]
    block = BasicBlock(
        label=CodeLabel("func_main_0"),
        instructions=instructions,
        successors=[],
        predecessors=[],
    )
    return CFG(
        blocks={CodeLabel("func_main_0"): block},
        entry=CodeLabel("func_main_0"),
    )


class TestTraceRegToVarAddressOf:
    def test_address_of_traces_to_var_name(self):
        """ADDRESS_OF %6, x -> _trace_reg_to_var('%6') should return 'x'."""
        cfg = _build_caller_cfg_with_address_of()
        result = _trace_reg_to_var("%6", cfg, "func_main_0")
        assert result == "x", f"Expected 'x', got {result!r}"

    def test_load_var_still_works(self):
        """Existing LOAD_VAR tracing should still work."""
        instructions = [
            LoadVar(result_reg=Register("%1"), name=VarName("y")),
        ]
        block = BasicBlock(
            label=CodeLabel("b"), instructions=instructions, successors=[], predecessors=[]
        )
        cfg = CFG(blocks={CodeLabel("b"): block}, entry=CodeLabel("b"))
        result = _trace_reg_to_var("%1", cfg, "b")
        assert result == "y"


class TestSubstituteDereferenceEndpoint:
    def test_deref_endpoint_collapses_to_variable(self):
        """DereferenceEndpoint(p) with p -> &x should collapse to VariableEndpoint(x)."""
        cfg = _build_caller_cfg_with_address_of()
        callee = FunctionEntry(label=CodeLabel("func_set_val_0"), params=("p",))
        caller = FunctionEntry(label=CodeLabel("func_main_0"), params=())
        call_loc = InstructionLocation(
            block_label=CodeLabel("func_main_0"), instruction_index=3
        )
        call_site = CallSite(
            caller=caller,
            location=call_loc,
            callees=frozenset({callee}),
            arg_operands=("%6",),
        )
        deref_ep = DereferenceEndpoint(
            base=VariableEndpoint(name="p", definition=NO_DEFINITION),
            location=InstructionLocation(
                block_label=CodeLabel("func_set_val_0"), instruction_index=4
            ),
        )
        result = _substitute_endpoint(
            deref_ep, {"p": "%6"}, callee, call_site, cfg
        )
        assert isinstance(result, VariableEndpoint)
        assert result.name == "x", f"Expected 'x', got {result.name!r}"


class TestApplySummaryWithPointers:
    def test_end_to_end_set_val(self):
        """Summary VariableEndpoint(p) -> DereferenceEndpoint(p) at call site set_val(&x)
        should produce VariableEndpoint(x) -> VariableEndpoint(x)."""
        cfg = _build_caller_cfg_with_address_of()
        callee = FunctionEntry(label=CodeLabel("func_set_val_0"), params=("p",))
        caller = FunctionEntry(label=CodeLabel("func_main_0"), params=())
        call_loc = InstructionLocation(
            block_label=CodeLabel("func_main_0"), instruction_index=3
        )
        call_site = CallSite(
            caller=caller,
            location=call_loc,
            callees=frozenset({callee}),
            arg_operands=("%6",),
        )
        summary = FunctionSummary(
            function=callee,
            context=ROOT_CONTEXT,
            flows=frozenset({
                (
                    VariableEndpoint(name="p", definition=NO_DEFINITION),
                    DereferenceEndpoint(
                        base=VariableEndpoint(name="p", definition=NO_DEFINITION),
                        location=InstructionLocation(
                            block_label=CodeLabel("func_set_val_0"),
                            instruction_index=4,
                        ),
                    ),
                ),
            }),
        )
        propagated = apply_summary_at_call_site(call_site, summary, callee, cfg)
        assert len(propagated) == 1
        (src, dst) = next(iter(propagated))
        assert isinstance(src, VariableEndpoint)
        assert isinstance(dst, VariableEndpoint)
        assert src.name == "x"
        assert dst.name == "x"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_propagation.py -v`
Expected: FAIL — `test_address_of_traces_to_var_name` fails with `assert '%6' == 'x'` (falls back to register name)

- [ ] **Step 3: Extend `_trace_reg_to_var()` for ADDRESS_OF**

In `interpreter/interprocedural/propagation.py`:

Add import:
```python
from interpreter.instructions import LoadVar, DeclVar, StoreVar, AddressOf
```

In `_trace_reg_to_var()` (line 151), add after the `DeclVar`/`StoreVar` scan (line 170) and before the `return reg` fallback (line 171):

```python
    # Scan for ADDRESS_OF that produces this register
    for inst in block.instructions:
        t = inst
        if isinstance(t, AddressOf) and str(t.result_reg) == reg:
            return str(t.var_name)
```

- [ ] **Step 4: Extend `_substitute_endpoint()` for DereferenceEndpoint**

In `interpreter/interprocedural/propagation.py`:

Add import:
```python
from interpreter.interprocedural.types import (
    ...
    DereferenceEndpoint,
)
```

In `_substitute_endpoint()` (line 174), add before the `raise TypeError` at line 205:

```python
    if isinstance(endpoint, DereferenceEndpoint):
        new_base = _substitute_endpoint(
            endpoint.base, param_to_actual, callee, call_site, cfg
        )
        assert isinstance(new_base, VariableEndpoint)
        # Dereferencing a pointer-to-x = accessing x itself
        return VariableEndpoint(name=new_base.name, definition=NO_DEFINITION)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_propagation.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
bd backup
git add interpreter/interprocedural/propagation.py tests/unit/test_interprocedural_propagation.py
git commit -m "Handle ADDRESS_OF and DereferenceEndpoint in interprocedural propagation

Extend _trace_reg_to_var() to trace ADDRESS_OF registers back to their
named variable. Add DereferenceEndpoint case to _substitute_endpoint()
that collapses deref-of-pointer-to-x into VariableEndpoint(x) at call
sites. Completes the pointer flow propagation pipeline."
```

---

### Task 5: Integration Test — C Pointer-Passing End-to-End

**Files:**
- Modify: `tests/integration/test_interprocedural_integration.py`

- [ ] **Step 1: Write the integration test**

Add to `tests/integration/test_interprocedural_integration.py`:

```python
class TestCPointerPassing:
    """C: pointer parameter modified by callee — the ntnx bug."""

    SOURCE = """\
void set_val(int *p) {
    *p = 99;
}

int main() {
    int x = 10;
    set_val(&x);
    return x;
}
"""

    def test_call_graph_resolves_set_val(self):
        result = _analyze_source(self.SOURCE, Language.C)
        callee_labels = {
            str(c.label)
            for site in result.call_graph.call_sites
            for c in site.callees
        }
        assert any(
            "set_val" in label for label in callee_labels
        ), f"Expected set_val in callees, got {callee_labels}"

    def test_set_val_summary_has_flows(self):
        result = _analyze_source(self.SOURCE, Language.C)
        set_val_summaries = [
            s for s in result.summaries.values() if "set_val" in s.function.label
        ]
        assert len(set_val_summaries) > 0, "Expected summary for set_val"
        assert len(set_val_summaries[0].flows) > 0, (
            "Expected non-empty flows for set_val (STORE_INDIRECT should produce deref flows)"
        )

    def test_set_val_summary_has_deref_endpoint(self):
        result = _analyze_source(self.SOURCE, Language.C)
        set_val_summaries = [
            s for s in result.summaries.values() if "set_val" in s.function.label
        ]
        assert len(set_val_summaries) > 0
        deref_dsts = [
            dst
            for _, dst in set_val_summaries[0].flows
            if isinstance(dst, DereferenceEndpoint)
        ]
        assert len(deref_dsts) > 0, "Expected DereferenceEndpoint in set_val flows"

    def test_whole_program_graph_is_nonempty(self):
        result = _analyze_source(self.SOURCE, Language.C)
        assert len(result.whole_program_graph) > 0, (
            "Expected non-empty whole-program graph for pointer-passing program"
        )

    def test_x_appears_in_whole_program_graph(self):
        result = _analyze_source(self.SOURCE, Language.C)
        all_names = set()
        for src, dsts in result.whole_program_graph.items():
            if isinstance(src, VariableEndpoint):
                all_names.add(src.name)
            for dst in dsts:
                if isinstance(dst, VariableEndpoint):
                    all_names.add(dst.name)
        assert "x" in all_names, f"Expected 'x' in whole-program graph, got {all_names}"
```

Also add `DereferenceEndpoint` to the imports at the top of the file.

- [ ] **Step 2: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/integration/test_interprocedural_integration.py::TestCPointerPassing -v`
Expected: All 5 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest tests/ -q`
Expected: All 13,141+ tests PASS

- [ ] **Step 4: Commit**

```bash
bd backup
git add tests/integration/test_interprocedural_integration.py
git commit -m "Add C pointer-passing integration test for interprocedural analysis

End-to-end test for red-dragon-ntnx: verifies call graph resolution,
set_val summary has DereferenceEndpoint flows, and whole-program graph
contains x as a modified variable."
```

---

### Task 6: Final Verification and Cleanup

- [ ] **Step 1: Run formatting**

```bash
poetry run python -m black .
```

- [ ] **Step 2: Run import linter**

```bash
poetry run lint-imports
```

- [ ] **Step 3: Run full test suite**

```bash
poetry run python -m pytest tests/ -q
```

Expected: All 13,141+ tests PASS, 0 failures.

- [ ] **Step 4: Close Beads issue**

```bash
bd close red-dragon-ntnx --reason "Interprocedural pointer flow analysis fixed — DereferenceEndpoint type, STORE_INDIRECT/LOAD_INDIRECT summary extraction, ADDRESS_OF argument tracing. C pointer-passing programs now produce correct flows."
```

- [ ] **Step 5: Commit any formatting changes and push**

```bash
bd backup
git add -A
git commit -m "Format and verify interprocedural pointer flows complete"
git push
```
