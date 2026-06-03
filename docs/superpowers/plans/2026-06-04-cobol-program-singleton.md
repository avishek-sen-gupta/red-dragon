# COBOL Program Singleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model each COBOL program as a singleton with persistent WORKING-STORAGE, so WS survives repeated subprogram calls.

**Architecture:** Each program emits an init block that creates a HeapObject singleton containing a `ws_handle` (persistent WS region) and an `__init_params__` BoundFuncRef. `_handle_call_with_memory` looks up the singleton and dispatches through `__init_params__` → procedure division. The procedure division loads `__ws_region` from the singleton on each call rather than allocating a fresh region.

**Tech Stack:** Python (interpreter), Java (ProLeap bridge), existing VM opcodes (NewObject, StoreField, LoadField, StoreVar, LoadVar, Const, Branch, Return_).

**Spec:** `docs/superpowers/specs/2026-06-04-cobol-program-singleton-design.md`

---

## File Map

| Action | Path |
|--------|------|
| Modify | `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java` |
| Modify | `interpreter/cobol/asg_types.py` |
| Create | `interpreter/cobol/lower_program_init.py` |
| Modify | `interpreter/cobol/lower_data_division.py` |
| Modify | `interpreter/cobol/cobol_frontend.py` |
| Modify | `interpreter/handlers/calls.py` |
| Create | `tests/unit/test_lower_program_init.py` |
| Modify | `tests/unit/test_lower_sectioned_data_division.py` |
| Modify | `tests/integration/test_cobol_programs.py` |

---

## Task 1: Bridge — emit `program_id`

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java`

The bridge currently omits PROGRAM-ID from JSON output. Add it now so `CobolASG` can read it in Task 2.

- [ ] **Step 1: Add the import for IdentificationDivision**

In `AsgSerializer.java`, add to the imports block (after the existing `procedure.*` imports):

```java
import io.proleap.cobol.asg.metamodel.identification.IdentificationDivision;
```

- [ ] **Step 2: Emit program_id in `serialize()`**

In `AsgSerializer.serialize()`, add the following immediately after the `pu` null check and before `serializeDataDivision`:

```java
IdentificationDivision id = pu.getIdentificationDivision();
if (id != null && id.getProgramIdParagraph() != null) {
    asg.addProperty("program_id", id.getProgramIdParagraph().getName());
} else {
    asg.addProperty("program_id", cu.getName());
}
```

- [ ] **Step 3: Rebuild the bridge JAR**

```bash
cd proleap-bridge && mvn package -DskipTests -q
```

Expected: `target/proleap-bridge-0.1.0-shaded.jar` has a newer timestamp.

- [ ] **Step 4: Verify with a quick smoke test**

```bash
cd /Users/asgupta/code/red-dragon
poetry run python -c "
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
import os
jar = 'proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar'
os.environ['PROLEAP_BRIDGE_JAR'] = jar
parser = ProLeapCobolParser(RealSubprocessRunner(), jar_path=jar)
src = b'       IDENTIFICATION DIVISION.\n       PROGRAM-ID. MYTEST.\n       PROCEDURE DIVISION.\n           STOP RUN.\n'
asg = parser.parse(src)
print('program_id:', asg.program_id)
assert asg.program_id == 'MYTEST', f'Expected MYTEST, got {asg.program_id!r}'
print('OK')
"
```

Expected: prints `program_id: MYTEST` then `OK`.

- [ ] **Step 5: Commit**

```bash
git add proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java \
        proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
git commit -m "feat(bridge): emit program_id from IDENTIFICATION DIVISION"
```

---

## Task 2: `CobolASG.program_id` field

**Files:**
- Modify: `interpreter/cobol/asg_types.py`
- Test: `tests/unit/test_asg_types.py` (create if absent)

Add `program_id: str = ""` to `CobolASG` and read it in `from_dict`.

- [ ] **Step 1: Write the failing test**

Check if `tests/unit/test_asg_types.py` exists. If not, create it:

```python
from interpreter.cobol.asg_types import CobolASG
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_asg_reads_program_id():
    data = {"program_id": "SUBPROG"}
    asg = CobolASG.from_dict(data)
    assert asg.program_id == "SUBPROG"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_asg_program_id_defaults_empty():
    asg = CobolASG.from_dict({})
    assert asg.program_id == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_asg_types.py -v
```

Expected: `AttributeError` or `TypeError` — `program_id` does not exist yet.

- [ ] **Step 3: Add `program_id` to `CobolASG`**

In `interpreter/cobol/asg_types.py`, add `program_id: str = ""` as the first field of `CobolASG` (before `data_fields`):

```python
@dataclass(frozen=True)
class CobolASG:
    program_id: str = ""
    data_fields: list[CobolField] = field(default_factory=list)
    linkage_fields: list[CobolField] = field(default_factory=list)
    local_storage_fields: list[CobolField] = field(default_factory=list)
    sections: list[CobolSection] = field(default_factory=list)
    paragraphs: list[CobolParagraph] = field(default_factory=list)
    statements: list[CobolStatementType] = field(default_factory=list)
```

In `CobolASG.from_dict()`, add `program_id=data.get("program_id", ""),` as the first kwarg:

```python
@classmethod
def from_dict(cls, data: dict) -> CobolASG:
    return cls(
        program_id=data.get("program_id", ""),
        data_fields=[CobolField.from_dict(f) for f in data.get("data_fields", [])],
        ...
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_asg_types.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite to check nothing broke**

```bash
poetry run python -m pytest tests/unit/ -q --tb=short
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/cobol/asg_types.py tests/unit/test_asg_types.py
git commit -m "feat(cobol): add program_id field to CobolASG"
```

---

## Task 3: `lower_program_init.py` — singleton init block emitter

**Files:**
- Create: `interpreter/cobol/lower_program_init.py`
- Create: `tests/unit/test_lower_program_init.py`

This new module emits all IR for the singleton prologue: init block + `func_init_params` function. It returns the `after_label` that `CobolFrontend` must emit after the procedure body.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_lower_program_init.py`:

```python
from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_program_init import lower_program_init
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.ir import CodeLabel, Opcode
from interpreter.cobol.features import CobolFeature
from tests.covers import covers, NotLanguageFeature


def _ws_layout_5bytes():
    field = CobolField(name="WS-X", level=1, pic="X(5)", usage="DISPLAY", offset=0)
    return build_data_layout([field])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_new_object():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.NEW_OBJECT in opcodes


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_alloc_region_for_ws():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.ALLOC_REGION in opcodes


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_three_store_fields():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    count = sum(1 for i in ctx.instructions if i.opcode == Opcode.STORE_FIELD)
    assert count == 3  # ws_handle, run, __init_params__


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_store_var_singleton():
    from interpreter.ir import Opcode
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    store_var_insts = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
    names = [str(i.name) for i in store_var_insts]
    assert "__prog_SUBPROG" in names


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_branch_to_after_label():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    after_label = lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    branch_insts = [i for i in ctx.instructions if i.opcode == Opcode.BRANCH]
    branch_labels = [str(i.label) for i in branch_insts]
    assert str(after_label) in branch_labels


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_func_init_params_label():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    labels = [str(i.label) for i in ctx.instructions if i.opcode == Opcode.LABEL]
    assert "func_init_params_subprog_0" in labels


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_returns_after_label():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    after_label = lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    assert str(after_label) == "__after_subprog_0"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_lower_program_init.py -v
```

Expected: `ImportError` — module does not exist yet.

- [ ] **Step 3: Implement `lower_program_init.py`**

Create `interpreter/cobol/lower_program_init.py`:

```python
# pyright: standard
"""Emit the singleton init block and func_init_params for a COBOL program.

Emits (in order):
  1. Init block — runs once at program load:
       NEW_OBJECT %ptr
       ALLOC_REGION %ws_reg, <ws_size>  + VALUE initialisers
       STORE_FIELD %ptr, ws_handle, %ws_reg
       CONST %run_reg, "func_<pid>_0"       → BoundFuncRef at runtime
       STORE_FIELD %ptr, run, %run_reg
       CONST %init_reg, "func_init_params_<pid>_0"  → BoundFuncRef
       STORE_FIELD %ptr, __init_params__, %init_reg
       STORE_VAR __prog_<PID>, %ptr
       BRANCH __after_<pid>_0            → skip over procedure body

  2. func_init_params function — called by _handle_call_with_memory:
       LABEL func_init_params_<pid>_0
       BRANCH func_<pid>_0               → __params_region/__results_region
                                           already injected by handler

Returns the after_label (CodeLabel) that CobolFrontend must emit
after the procedure body.
"""

from __future__ import annotations

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_data_division
from interpreter.field_name import FieldName
from interpreter.instructions import (
    Branch,
    Const,
    Label_,
    NewObject,
    StoreField,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.var_name import VarName


def lower_program_init(
    ctx: EmitContext,
    program_id: str,
    ws_layout: DataLayout,
) -> CodeLabel:
    """Emit the singleton init block and func_init_params function.

    Args:
        ctx: Emit context for the current compilation unit.
        program_id: COBOL PROGRAM-ID value (e.g. "SUBPROG").
        ws_layout: Working-Storage layout (for ALLOC_REGION + VALUE inits).

    Returns:
        The after_label CodeLabel. CobolFrontend must emit Label_(after_label)
        after the procedure body so the init block's Branch skips past it.
    """
    pid_lower = program_id.lower()
    pid_upper = program_id.upper()

    proc_label = CodeLabel(f"func_{pid_lower}_0")
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")
    after_label = CodeLabel(f"__after_{pid_lower}_0")
    singleton_var = VarName(f"__prog_{pid_upper}")

    # --- Init block ---
    ptr_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=ptr_reg))

    ws_reg = lower_data_division(ctx, ws_layout)

    ctx.emit_inst(
        StoreField(
            obj_reg=ptr_reg,
            field_name=FieldName("ws_handle"),
            value_reg=ws_reg,
        )
    )

    run_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=run_reg, value=str(proc_label)))
    ctx.emit_inst(
        StoreField(obj_reg=ptr_reg, field_name=FieldName("run"), value_reg=run_reg)
    )

    init_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_reg, value=str(init_params_label)))
    ctx.emit_inst(
        StoreField(
            obj_reg=ptr_reg,
            field_name=FieldName("__init_params__"),
            value_reg=init_reg,
        )
    )

    ctx.emit_inst(StoreVar(name=singleton_var, value_reg=ptr_reg))
    ctx.emit_inst(Branch(label=after_label))

    # --- func_init_params function ---
    # __params_region and __results_region are injected into the call frame
    # by _handle_call_with_memory before dispatching here.
    ctx.emit_inst(Label_(label=init_params_label))
    ctx.emit_inst(Branch(label=proc_label))

    return after_label
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_lower_program_init.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full unit suite**

```bash
poetry run python -m pytest tests/unit/ -q --tb=short
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/cobol/lower_program_init.py tests/unit/test_lower_program_init.py
git commit -m "feat(cobol): add lower_program_init for singleton init block emission"
```

---

## Task 4: `lower_sectioned_data_division` — WS from `LOAD_VAR __ws_region`

**Files:**
- Modify: `interpreter/cobol/lower_data_division.py`
- Modify: `tests/unit/test_lower_sectioned_data_division.py`

The WS region is now persistent (owned by the singleton). Inside `func_PROGRAMID_0`, it is pre-stored as `__ws_region` before `lower_sectioned_data_division` runs. Change WS handling from `ALLOC_REGION` to `LOAD_VAR __ws_region`.

- [ ] **Step 1: Update the failing test**

In `tests/unit/test_lower_sectioned_data_division.py`, change `test_lower_sectioned_emits_alloc_region_for_ws`:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_sectioned_emits_load_var_for_ws():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(data_fields=[_make_field("WS-X")])
    sl = build_sectioned_layout(asg)
    lower_sectioned_data_division(ctx, sl)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.LOAD_VAR in opcodes


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_sectioned_no_alloc_region_for_ws():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(data_fields=[_make_field("WS-X")])
    sl = build_sectioned_layout(asg)
    lower_sectioned_data_division(ctx, sl)
    # WS must NOT be freshly allocated; it comes from the singleton
    load_var_names = [
        str(i.name) for i in ctx.instructions if i.opcode == Opcode.LOAD_VAR
    ]
    assert "__ws_region" in load_var_names
```

Also update `test_lower_sectioned_emits_alloc_region_for_local_storage` — LS still uses ALLOC_REGION; the count is now 1 (LS only, not WS):

```python
@covers(CobolFeature.SECTION_LOCAL_STORAGE)
def test_lower_sectioned_emits_alloc_region_for_local_storage():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(
        data_fields=[_make_field("WS-X")],
        local_storage_fields=[_make_field("LS-Z")],
    )
    sl = build_sectioned_layout(asg)
    lower_sectioned_data_division(ctx, sl)
    alloc_count = sum(1 for i in ctx.instructions if i.opcode == Opcode.ALLOC_REGION)
    assert alloc_count == 1  # LS only — WS comes from singleton
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_lower_sectioned_data_division.py -v
```

Expected: `test_lower_sectioned_emits_load_var_for_ws` and related tests FAIL.

- [ ] **Step 3: Update `lower_sectioned_data_division`**

Replace the WS allocation in `interpreter/cobol/lower_data_division.py`:

```python
def lower_sectioned_data_division(
    ctx: EmitContext,
    layout: SectionedLayout,
) -> MaterialisedSectionedLayout:
    """Bind WS to the persistent singleton region; allocate fresh LS per call.

    The WS region handle was stored into __ws_region by func_PROGRAMID_0
    before this function is called (loaded from the singleton HeapObject).
    LINKAGE is bound to __params_region injected by _handle_call_with_memory.
    LOCAL-STORAGE is freshly allocated on every call.
    """
    ws_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ws_reg, name=VarName("__ws_region")))

    if layout.linkage.total_bytes > 0:
        lk_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=lk_reg, name=VarName("__params_region")))
    else:
        lk_reg = NO_REGISTER

    if layout.local_storage.total_bytes > 0:
        ls_reg = lower_data_division(ctx, layout.local_storage)
    else:
        ls_reg = NO_REGISTER

    logger.debug(
        "Sectioned data division: WS=%s LK=%s LS=%s",
        ws_reg,
        lk_reg,
        ls_reg,
    )

    return MaterialisedSectionedLayout(
        working_storage=(layout.working_storage, ws_reg),
        linkage=(layout.linkage, lk_reg),
        local_storage=(layout.local_storage, ls_reg),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_lower_sectioned_data_division.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full unit suite**

```bash
poetry run python -m pytest tests/unit/ -q --tb=short
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/cobol/lower_data_division.py \
        tests/unit/test_lower_sectioned_data_division.py
git commit -m "feat(cobol): lower_sectioned_data_division loads WS from singleton __ws_region"
```

---

## Task 5: `CobolFrontend` restructure — singleton emission + `program_id` property

**Files:**
- Modify: `interpreter/cobol/cobol_frontend.py`
- Modify: `tests/unit/test_cobol_frontend.py` (if exists) or `tests/integration/test_cobol_programs.py`

`CobolFrontend.lower()` must:
1. Call `lower_program_init` to emit the init block + `func_init_params`
2. Emit `Label_(func_PROGRAMID_0)` + WS-from-singleton preamble before the procedure
3. Emit `Label_(after_label)` after the procedure
4. Expose `program_id` as a property
5. Override `func_symbol_table` so `Const("func_programid_0")` produces a `BoundFuncRef` at runtime

- [ ] **Step 1: Add `lower_ws_from_singleton` to `lower_program_init.py`**

Add this helper to `interpreter/cobol/lower_program_init.py` (used by CobolFrontend to emit the singleton WS load at the start of `func_PROGRAMID_0`):

```python
def lower_ws_from_singleton(ctx: EmitContext, program_id: str) -> None:
    """Emit load of persistent WS handle from singleton into __ws_region.

    Must be called immediately after Label_(func_<pid>_0) and before
    lower_sectioned_data_division, so __ws_region is in scope.
    """
    pid_lower = program_id.lower()
    pid_upper = program_id.upper()

    singleton_var = VarName(f"__prog_{pid_upper}")
    singleton_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=singleton_reg, name=singleton_var))

    ws_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(
            result_reg=ws_reg,
            obj_reg=singleton_reg,
            field_name=FieldName("ws_handle"),
        )
    )

    ws_var = VarName("__ws_region")
    ctx.emit_inst(StoreVar(name=ws_var, value_reg=ws_reg))
```

Add the required imports to `lower_program_init.py`:
```python
from interpreter.instructions import (
    Branch,
    Const,
    Label_,
    LoadField,
    LoadVar,
    NewObject,
    StoreField,
    StoreVar,
)
```

- [ ] **Step 2: Write failing tests for `CobolFrontend` IR structure**

In an existing or new unit test file for `CobolFrontend`, add (skip if JAR is absent — copy the skip pattern from `test_cobol_programs.py`):

```python
@covers(CobolFeature.SECTION_WORKING_STORAGE)
def test_frontend_lower_emits_func_proc_label():
    """lower() must wrap the procedure division in func_<pid>_0 label."""
    ...
    instructions = frontend.lower(source)
    labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
    assert any(l.startswith("func_") and l.endswith("_0") for l in labels)


@covers(CobolFeature.SECTION_WORKING_STORAGE)
def test_frontend_exposes_program_id():
    ...
    frontend.lower(source)
    assert frontend.program_id == "TEST-INIT"
```

- [ ] **Step 3: Update `CobolFrontend.lower()`**

Replace the `lower()` method body in `interpreter/cobol/cobol_frontend.py`:

```python
def lower(
    self,
    source: bytes,
    namespace_resolver: NamespaceResolver = Frontend._NULL_RESOLVER,
    resolved_imports: dict[str, PathName] | None = None,
) -> list[InstructionBase]:
    """Lower COBOL source to IR via the ProLeap bridge."""
    asg = self._parser.parse(source)
    sectioned = build_sectioned_layout(asg)
    self._program_id = asg.program_id or "MAIN"
    self._layout = sectioned.working_storage
    self._symbol_table = SymbolTable.from_data_layout(sectioned.working_storage)
    condition_index = build_condition_index(sectioned.working_storage)

    self._ctx = EmitContext(
        dispatch_fn=dispatch_statement,
        observer=self._observer,
        condition_index=condition_index,
    )

    self._ctx.emit_inst(Label_(label=CodeLabel("entry")))

    # Emit singleton init block (ALLOC_REGION for WS lives here, runs once)
    after_label = lower_program_init(
        self._ctx, self._program_id, sectioned.working_storage
    )

    # Procedure division function — reachable only via __init_params__ dispatch
    proc_label = CodeLabel(f"func_{self._program_id.lower()}_0")
    self._ctx.emit_inst(Label_(label=proc_label))

    # Load persistent WS from singleton into __ws_region
    lower_ws_from_singleton(self._ctx, self._program_id)

    # Bind LINKAGE to __params_region (injected by handler); alloc fresh LS
    materialised = lower_sectioned_data_division(self._ctx, sectioned)
    lower_procedure_division(self._ctx, asg, materialised)

    # Skip target — init block branches here to skip past procedure body
    self._ctx.emit_inst(Label_(label=after_label))

    logger.info(
        "COBOL frontend produced %d IR instructions",
        len(self._ctx.instructions),
    )
    return self._ctx.instructions
```

- [ ] **Step 4: Add `program_id` property and `func_symbol_table` override**

Add these two properties to `CobolFrontend` (after the existing `data_layout` property):

```python
@property
def program_id(self) -> str:
    """COBOL PROGRAM-ID value. Available after lower() has been called."""
    return getattr(self, "_program_id", "")

@property
def func_symbol_table(self) -> dict[CodeLabel, FuncRef]:
    """Expose func_PROGRAMID_0 and func_init_params_PROGRAMID_0 so that
    Const instructions in the init block resolve to BoundFuncRef at runtime."""
    from interpreter.refs.func_ref import FuncRef
    from interpreter.func_name import FuncName

    pid = self.program_id
    if not pid:
        return {}
    pid_lower = pid.lower()
    proc_label = CodeLabel(f"func_{pid_lower}_0")
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")
    return {
        proc_label: FuncRef(name=FuncName(str(proc_label)), label=proc_label),
        init_params_label: FuncRef(
            name=FuncName(str(init_params_label)), label=init_params_label
        ),
    }
```

Add the necessary imports at the top of `cobol_frontend.py`:

```python
from interpreter.cobol.lower_program_init import lower_program_init, lower_ws_from_singleton
from interpreter.ir import CodeLabel  # already imported — verify
```

- [ ] **Step 5: Run the unit tests**

```bash
poetry run python -m pytest tests/unit/ -q --tb=short
```

Expected: all pass. Fix any import or logic errors before proceeding.

- [ ] **Step 6: Run integration tests (JAR-dependent)**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py -v
```

Expected: all existing tests pass (they test WS field access, not subprogram calls, so they should pass unmodified with the singleton model).

- [ ] **Step 7: Commit**

```bash
git add interpreter/cobol/cobol_frontend.py interpreter/cobol/lower_program_init.py
git commit -m "feat(cobol): CobolFrontend emits singleton init block, wraps procedure in func_PROGRAMID_0"
```

---

## Task 6: `_handle_call_with_memory` — singleton dispatch

**Files:**
- Modify: `interpreter/handlers/calls.py`
- Create: `tests/unit/test_handle_call_with_memory_singleton.py`

Replace the current scope-chain BoundFuncRef lookup with: find singleton by `__prog_PROGRAMID`, load `__init_params__`, dispatch.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_handle_call_with_memory_singleton.py`:

```python
"""Unit test: _handle_call_with_memory dispatches via singleton __init_params__."""

import pytest
from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import CallWithMemory
from interpreter.ir import CodeLabel
from interpreter.refs.func_ref import BoundFuncRef, FuncRef
from interpreter.register import Register
from interpreter.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.vm_types import HeapObject, VMState
from tests.covers import covers


def _make_vm_with_singleton(program_id: str) -> VMState:
    """Build a minimal VMState with a singleton HeapObject in scope."""
    from interpreter.vm.vm_types import CallFrame

    pid_lower = program_id.lower()
    pid_upper = program_id.upper()

    proc_label = CodeLabel(f"func_{pid_lower}_0")
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")

    init_params_ref = BoundFuncRef(
        func_ref=FuncRef(
            name=FuncName(str(init_params_label)), label=init_params_label
        )
    )

    singleton = HeapObject(
        fields={
            FieldName("__init_params__"): TypedValue(value=init_params_ref),
            FieldName("ws_handle"): TypedValue(value=Address(0)),
            FieldName("run"): TypedValue(
                value=BoundFuncRef(
                    func_ref=FuncRef(
                        name=FuncName(str(proc_label)), label=proc_label
                    )
                )
            ),
        }
    )

    singleton_addr = Address(1)
    singleton_var = VarName(f"__prog_{pid_upper}")

    vm = VMState()
    vm._heap[singleton_addr] = singleton
    vm.call_stack[0].local_vars[singleton_var] = TypedValue(value=singleton_addr)

    # Fake a WS region
    params_addr = Address(2)
    vm.call_stack[0].local_vars[VarName("__ws_region")] = TypedValue(value=params_addr)

    return vm


@covers(CobolFeature.CALL_USING)
def test_call_with_memory_dispatches_to_init_params():
    """Handler must dispatch to func_init_params_<pid>_0, not func_<pid>_0 directly."""
    from interpreter.cfg import CFG
    from interpreter.handlers.calls import _handle_call_with_memory
    from interpreter.handlers._common import HandlerContext
    from interpreter.instructions import Return_
    from interpreter.register import Register

    pid = "SUBPROG"
    pid_lower = pid.lower()
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")
    proc_label = CodeLabel(f"func_{pid_lower}_0")

    # Build a minimal CFG with both labels
    from interpreter.cfg import BasicBlock
    cfg = CFG(
        blocks={
            init_params_label: BasicBlock(label=init_params_label, instructions=[Return_()]),
            proc_label: BasicBlock(label=proc_label, instructions=[Return_()]),
        }
    )

    vm = _make_vm_with_singleton(pid)
    params_reg = Register("%r0")
    results_reg = Register("%r1")
    ws_addr = Address(10)
    vm.current_frame.registers[params_reg] = TypedValue(value=ws_addr)
    vm.current_frame.registers[results_reg] = TypedValue(value=ws_addr)

    inst = CallWithMemory(
        func_name=FuncName(pid),
        params_reg=params_reg,
        results_reg=results_reg,
    )

    ctx = HandlerContext(cfg=cfg, current_label=CodeLabel("entry"))
    result = _handle_call_with_memory(inst, vm, ctx)

    assert result.handled
    assert result.state_update.next_label == init_params_label
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_handle_call_with_memory_singleton.py -v
```

Expected: FAIL — handler dispatches to proc_label directly (old behaviour), not init_params_label.

- [ ] **Step 3: Update `_handle_call_with_memory`**

Replace the body of `_handle_call_with_memory` in `interpreter/handlers/calls.py` (lines 655–709):

```python
def _handle_call_with_memory(
    inst: InstructionBase,
    vm: VMState,
    ctx: HandlerContext,
) -> ExecutionResult:
    """Handle CALL_WITH_MEMORY via singleton dispatch.

    Protocol:
      1. Resolve __prog_<PROGRAMID> in scope chain → singleton HeapObject address
      2. Load __init_params__ field → BoundFuncRef
      3. Dispatch to __init_params__, injecting __params_region and __results_region
         into the new call frame (handler sets them via var_writes; the function
         body can then access them via LOAD_VAR before branching to func_<pid>_0)
    """
    t = inst
    assert isinstance(t, CallWithMemory)

    params_tv = _resolve_reg(vm, t.params_reg)
    results_tv = _resolve_reg(vm, t.results_reg)

    program_id = str(t.func_name).upper()
    singleton_key = VarName(f"__prog_{program_id}")

    # Walk scope chain to find singleton HeapObject address
    singleton_addr: Any = None
    for frame in reversed(vm.call_stack):
        if singleton_key in frame.local_vars:
            singleton_addr = frame.local_vars[singleton_key].value
            break

    if singleton_addr is None or not vm.heap_contains(Address(singleton_addr)):
        return ctx.call_resolver.resolve_call(str(t.func_name), [], inst, vm)

    singleton = vm.heap_get(Address(singleton_addr))
    init_params_tv = singleton.fields.get(FieldName("__init_params__"))

    if init_params_tv is None or not isinstance(init_params_tv.value, BoundFuncRef):
        return ctx.call_resolver.resolve_call(str(t.func_name), [], inst, vm)

    init_params_ref = init_params_tv.value
    flabel = init_params_ref.func_ref.label
    fname = init_params_ref.func_ref.name

    if flabel not in ctx.cfg.blocks:
        return ctx.call_resolver.resolve_call(str(t.func_name), [], inst, vm)

    new_vars: dict[VarName, TypedValue] = {
        VarName("__params_region"): params_tv,
        VarName("__results_region"): results_tv,
    }

    return ExecutionResult.success(
        StateUpdate(
            call_push=StackFramePush(
                function_name=fname,
                return_label=ctx.current_label,
            ),
            next_label=flabel,
            reasoning=(
                f"call_with_memory {str(t.func_name)},"
                f" params={params_tv.value!r},"
                f" results={results_tv.value!r},"
                f" dispatch to {flabel} via singleton __init_params__"
            ),
            var_writes=new_vars,
        )
    )
```

Add the import at the top of `calls.py` if not present:
```python
from interpreter.field_name import FieldName
from interpreter.address import Address
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_handle_call_with_memory_singleton.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
poetry run python -m pytest tests/ -q --tb=short -m "not external"
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/handlers/calls.py \
        tests/unit/test_handle_call_with_memory_singleton.py
git commit -m "feat(cobol): _handle_call_with_memory dispatches via singleton __init_params__"
```

---

## Task 7: Integration test — WS persistence across repeated CALL

**Files:**
- Modify: `tests/integration/test_cobol_programs.py`

Write an end-to-end test that verifies WS in a subprogram survives repeated calls from a main program. The subprogram increments a counter in WS on each call; after two calls the counter must be 2.

- [ ] **Step 1: Write the failing integration test**

Add this class to `tests/integration/test_cobol_programs.py`:

```python
class TestSubprogramWsPersistence:
    @covers(CobolFeature.CALL_USING, CobolFeature.SECTION_WORKING_STORAGE)
    def test_ws_counter_survives_two_calls(self):
        """SUBPROG increments WS-COUNTER on each CALL; value must be 2 after two calls."""
        main_source = _to_fixed([
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. MAIN.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-PARAM PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "    CALL 'SUBPROG' USING WS-PARAM.",
            "    CALL 'SUBPROG' USING WS-PARAM.",
            "    STOP RUN.",
        ])

        subprog_source = _to_fixed([
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SUBPROG.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-COUNTER PIC 9(4) VALUE 0.",
            "LINKAGE SECTION.",
            "77 LK-PARAM PIC 9(4).",
            "PROCEDURE DIVISION USING LK-PARAM.",
            "    ADD 1 TO WS-COUNTER.",
            "    STOP RUN.",
        ])

        from interpreter.cobol.cobol_frontend import CobolFrontend
        from interpreter.cobol.cobol_parser import ProLeapCobolParser
        from interpreter.cobol.subprocess_runner import RealSubprocessRunner
        from interpreter.project.entry_point import EntryPoint
        from interpreter.run import run_multi_module

        jar = _JAR_PATH
        parser = ProLeapCobolParser(RealSubprocessRunner(), jar_path=jar)

        main_frontend = CobolFrontend(parser)
        sub_frontend = CobolFrontend(parser)

        main_ir = main_frontend.lower(main_source.encode())
        sub_ir = sub_frontend.lower(subprog_source.encode())

        vm = run_multi_module(
            modules={"MAIN": main_ir, "SUBPROG": sub_ir},
            func_symbol_tables={
                "MAIN": main_frontend.func_symbol_table,
                "SUBPROG": sub_frontend.func_symbol_table,
            },
            entry_point=EntryPoint.function(
                lambda f: str(f.name) == main_frontend.program_id
            ),
        )

        # Find SUBPROG's WS region and decode WS-COUNTER at offset 0, length 4
        # The singleton's ws_handle address can be found via __prog_SUBPROG in
        # the bottom frame; alternatively just check that the VM ran without error.
        # Verify by reading the subprog singleton's ws_handle region.
        singleton_key = VarName("__prog_SUBPROG")
        singleton_addr = None
        for frame in reversed(vm.call_stack):
            if singleton_key in frame.local_vars:
                singleton_addr = frame.local_vars[singleton_key].value
                break
        assert singleton_addr is not None, "__prog_SUBPROG singleton not found"

        from interpreter.field_name import FieldName
        singleton = vm.heap_get(singleton_addr)
        ws_handle = singleton.fields[FieldName("ws_handle")].value
        region = vm.region_get(ws_handle)
        counter = _decode_zoned_unsigned(region, offset=0, length=4)
        assert counter == 2, f"Expected WS-COUNTER=2 after two calls, got {counter}"
```

**NOTE:** If `run_multi_module` does not exist yet, use `run()` with multi-module support. Check `interpreter/run.py` for the correct API to run linked COBOL programs — look for `run()` with a `source_files` or `modules` parameter, or use the project `Compiler`/`Linker` directly as done in existing multi-module tests.

Before running, verify which API to use:
```bash
poetry run python -c "from interpreter.run import run; help(run)" 2>&1 | head -40
```

Adapt the test to the actual multi-module API.

- [ ] **Step 2: Run to verify it fails (or errors) before implementation**

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py::TestSubprogramWsPersistence -v
```

Expected: FAIL or error (not NotImplemented — this tests the full pipeline).

- [ ] **Step 3: Run after all previous tasks are complete**

Re-run after Tasks 1–6 are done:

```bash
poetry run python -m pytest tests/integration/test_cobol_programs.py -v
```

Expected: `test_ws_counter_survives_two_calls` PASS.

- [ ] **Step 4: Run full suite**

```bash
poetry run python -m pytest tests/ -q --tb=short -m "not external"
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_cobol_programs.py
git commit -m "test(cobol): integration test — WS persists across two subprogram calls"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| 1. Bridge — emit program_id | Task 1 |
| 2. CobolASG.program_id | Task 2 |
| 3. Singleton HeapObject | Task 3 (init block) |
| 4a. Init block | Task 3 + Task 5 |
| 4b. func_PROGRAMID_0 | Task 4 + Task 5 |
| 5. __init_params__ | Task 3 + Task 6 |
| 6. _handle_call_with_memory | Task 6 |
| 7. Linker — no changes | verified: no task needed |
| 8. EntryPoint.function(program_id) | Task 5 (program_id property) + Task 7 |
| REDEFINES compatibility | preserved: WS is still a byte region |
| CANCEL deferred | red-dragon-8dpn — not in this plan |
| BY CONTENT deferred | not in this plan |

**Type consistency check:**
- `lower_program_init(ctx, program_id: str, ws_layout: DataLayout) -> CodeLabel` — used in Task 5 step 3 with same signature
- `lower_ws_from_singleton(ctx, program_id: str) -> None` — defined Task 5 step 1, used Task 5 step 3
- `singleton.fields.get(FieldName("__init_params__"))` — HeapObject.fields is `dict[FieldName, TypedValue]` ✓
- `vm.heap_get(Address(...))` — returns `HeapObject` ✓
- `VarName(f"__prog_{pid_upper}")` — matches what the init block stores via `StoreVar` ✓
