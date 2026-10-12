# Run-unit State in Program Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the run unit's RETURN-CODE and the FUNCTION RANDOM state out of `VMState` and into a 6-byte region that a synthetic COBOL start-up module allocates.

**Architecture:** The COBOL compile paths add a generated start-up module to every link. Its top-level code allocates the run-unit region and declares `__cobol_run_unit`. Lowering publishes RETURN-CODE and steps RANDOM by plain region reads and writes. The read-back finds the region through the outermost frame. The VM and the linker do not change.

**Tech Stack:** Python 3.13, pytest, red-dragon IR (`AllocRegion`, `LoadRegion`, `WriteRegion`, `DeclVar`, `LoadVar`, `CallFunction`).

**Spec:** `docs/superpowers/specs/2026-10-12-run-unit-state-in-memory-design.md`

## Global Constraints

- The run-unit region is 6 bytes: RETURN-CODE at offset 0 (2 bytes, big-endian two's complement); the RANDOM state at offset 2 (4 bytes, big-endian unsigned).
- The variable is `__cobol_run_unit`, declared by the start-up module and read by COBOL lowering and the read-back only.
- RANDOM: modulus 2^31 − 1, multiplier 16807. State 0 means "not started". Seed s starts at state s mod 2,147,483,646 + 1. A negative seed is treated as 0, with a warning. The value is state / (2^31 − 1).
- No change to the linker, the VM's instructions or its handlers.
- red-dragon's fp-lint gate is a total ratchet (`fp-baseline.json`). New code adds no violations. Fix the violations in any small file that is touched.
- Pyright: new modules carry no `# pyright: standard` pragma and are strict-clean.

## Review Focus

- **STOP RUN inside a subprogram:** the callee's frame must still reach `__cobol_run_unit`, which lives in the outermost frame.
- **Region order:** the run-unit region is now the first region allocated. Any test or forge code that takes "the first region" as WORKING-STORAGE breaks.
- **Callers outside `compile_cobol`:** `compile_directory` for COBOL needs the start-up module too.
- **Symbolic RANDOM:** a symbolic state or seed must not write the region.
- **Forge:** jackal reads the step RC through `read_return_code`, and cicada runs many programs through `compile_program`. Both suites must stay green after the submodule bump.

---

### Task 1: The start-up module allocates the run-unit region in every COBOL link

**Files:**
- Create: `interpreter/cobol/run_unit.py` (the layout and the variable; lowering-clean, imports no VM)
- Create: `interpreter/project/cobol_start_up.py` (builds the module and adds it to a link)
- Modify: `interpreter/project/cobol_compile.py` (`compile_cobol`: always link; add the start-up module)
- Modify: `interpreter/project/compiler.py:394` (`compile_directory`: add the start-up module for COBOL)
- Modify: `cobol_memory/region_id.py` (add `RUN_UNIT`)
- Modify: `tests/integration/cobol_helpers.py:160` (`first_region` skips the run-unit region)
- Modify: `tests/integration/test_cobol_programs.py:51` (`_first_region` delegates to `first_region`)
- Modify: `tests/integration/test_cobol_return_code.py:56` (use `ws_region(vm, "RCISO")`)
- Test: `tests/unit/project/test_cobol_start_up.py`, `tests/integration/test_cobol_run_unit.py`

**Interfaces:**
- Produces:
  - `interpreter.cobol.run_unit.RUN_UNIT_VAR: VarName` (`__cobol_run_unit`)
  - `RUN_UNIT_LAYOUT: DataLayout`, with fields `RUN_UNIT_RETURN_CODE` (offset 0, length 2) and `RANDOM_STATE` (offset 2, length 4)
  - `interpreter.project.cobol_start_up.START_UP_PATH: Path`
  - `start_up_module() -> ModuleUnit`
  - `with_start_up(modules, import_graph) -> tuple[dict[Path, ModuleUnit], dict[Path, list[Path]]]`

- [ ] **Step 1: Write the failing tests**

`tests/unit/project/test_cobol_start_up.py`:

```python
"""The COBOL start-up module: what it allocates and where it sits in a link."""

from pathlib import Path

from interpreter.cobol.run_unit import RANDOM_STATE, RUN_UNIT_LAYOUT, RUN_UNIT_RETURN_CODE, RUN_UNIT_VAR
from interpreter.instructions import AllocRegion, Const, DeclVar
from interpreter.project.cobol_start_up import START_UP_PATH, start_up_module, with_start_up
from interpreter.project.types import NO_MODULE_UNIT
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_start_up_module_allocates_the_run_unit_region_and_declares_it():
    module = start_up_module()
    size, alloc, decl = module.ir
    assert isinstance(size, Const) and size.value == 6
    assert isinstance(alloc, AllocRegion) and alloc.size_reg == size.result_reg
    assert isinstance(decl, DeclVar) and decl.name == RUN_UNIT_VAR
    assert decl.value_reg == alloc.result_reg
    assert module.path == START_UP_PATH
    assert RUN_UNIT_LAYOUT.total_bytes == 6
    rc = RUN_UNIT_LAYOUT.lookup_or_raise(RUN_UNIT_RETURN_CODE)
    state = RUN_UNIT_LAYOUT.lookup_or_raise(RANDOM_STATE)
    assert (rc.offset, rc.byte_length, state.offset, state.byte_length) == (0, 2, 2, 4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_with_start_up_makes_every_module_depend_on_it():
    a, b = Path("A.cbl"), Path("B.cbl")
    modules, graph = with_start_up({a: NO_MODULE_UNIT, b: NO_MODULE_UNIT}, {a: [b], b: []})
    assert set(modules) == {START_UP_PATH, a, b}
    assert graph == {START_UP_PATH: [], a: [b, START_UP_PATH], b: [START_UP_PATH]}
```

`tests/integration/test_cobol_run_unit.py`:

```python
"""The run-unit region exists, zero-filled, before any program runs."""

from interpreter.address import Address
from interpreter.cobol.run_unit import RUN_UNIT_VAR
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import run_cobol, run_cobol_programs

_QUIET = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. RUQUIET.", "PROCEDURE DIVISION.", "    GOBACK."]


def _run_unit(vm) -> bytearray:
    return vm.region_get(Address(str(vm.call_stack[0].local_vars[RUN_UNIT_VAR].value)))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_single_program_run_has_the_run_unit_region():
    assert _run_unit(run_cobol(_QUIET)) == bytearray(6)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_run_has_one_run_unit_region_allocated_first():
    caller = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. RUCALLER.", "PROCEDURE DIVISION.",
              "    CALL 'RUQUIET'.", "    GOBACK."]
    vm = run_cobol_programs(caller, {"RUQUIET": _QUIET})
    first = list(vm.region_keys())[0]
    assert first == Address(str(vm.call_stack[0].local_vars[RUN_UNIT_VAR].value))
    assert _run_unit(vm) == bytearray(6)
```

`run_cobol` goes through `run()` → `compile_cobol`, and `run_cobol_programs` goes through `compile_cobol` with subprograms. So both compile paths in `compile_cobol` are covered. `compile_directory` is covered by the existing `tests/integration/test_cobol_call_by_data_name.py`, which must stay green.

- [ ] **Step 2: Run them; expect failure**

Run: `uv run python -m pytest tests/unit/project/test_cobol_start_up.py tests/integration/test_cobol_run_unit.py -q`
Expected: collection errors, `ModuleNotFoundError: interpreter.cobol.run_unit`.

- [ ] **Step 3: Implement**

`cobol_memory/region_id.py`: add `RUN_UNIT = "run_unit"` to `RegionId`.

`interpreter/cobol/run_unit.py`:

```python
"""The COBOL run unit's own storage: one region the start-up module allocates before any program runs."""

from __future__ import annotations

from cobol_asg.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.var_name import VarName

RUN_UNIT_VAR = VarName("__cobol_run_unit")
RUN_UNIT_RETURN_CODE = "RUN-UNIT-RETURN-CODE"
RANDOM_STATE = "RANDOM-STATE"

RUN_UNIT_LAYOUT = build_data_layout(
    [
        CobolField(name=RUN_UNIT_RETURN_CODE, level=1, pic="S9(4)", usage="COMP", offset=0),
        CobolField(name=RANDOM_STATE, level=1, pic="X(4)", offset=2),
    ]
)
```

If `build_data_layout` does not set `total_bytes` on the root for two level-01 items, compute the size as `max(f.offset + f.byte_length)` over the two fields in `cobol_start_up.py` instead, and assert that value in the test.

`interpreter/project/cobol_start_up.py`:

```python
"""The generated start-up module every COBOL link carries: it allocates the run-unit region."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from interpreter.cobol.run_unit import RUN_UNIT_LAYOUT, RUN_UNIT_VAR
from interpreter.instructions import AllocRegion, Const, DeclVar
from interpreter.language import Language
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register

START_UP_PATH = Path("__cobol_run_unit__.cbl")


def start_up_module() -> ModuleUnit:
    size, region = Register("%0"), Register("%1")
    return ModuleUnit(
        path=START_UP_PATH,
        language=Language.COBOL,
        ir=(
            Const.int_(size, RUN_UNIT_LAYOUT.total_bytes),
            AllocRegion(result_reg=region, size_reg=size),
            DeclVar(name=RUN_UNIT_VAR, value_reg=region),
        ),
        exports=ExportTable(),
        imports=(),
    )


def with_start_up(
    modules: Mapping[Path, ModuleUnit], import_graph: Mapping[Path, Sequence[Path]]
) -> tuple[dict[Path, ModuleUnit], dict[Path, list[Path]]]:
    return (
        {START_UP_PATH: start_up_module(), **modules},
        {START_UP_PATH: [], **{p: [*deps, START_UP_PATH] for p, deps in import_graph.items()}},
    )
```

`compile_cobol` (`interpreter/project/cobol_compile.py:230-272`): delete the `if len(modules) == 1:` branch. Build the graph and add the start-up module:

```python
        import_graph: dict[Path, list[Path]] = {p: [] for p in modules}
        import_graph[main_path] = [p for p in modules if p != main_path]
        linked_modules, linked_graph = with_start_up(modules, import_graph)
        topo_order = topological_sort(linked_graph)
        linked = link_modules(
            modules=linked_modules,
            import_graph=linked_graph,
            ...
```

Every other argument and the `entry_func_label` assignment stay as they are.

`compile_directory` (`interpreter/project/compiler.py:394`): before `topological_sort`, when `language == Language.COBOL`, set `modules, import_graph = with_start_up(modules, import_graph)`.

Ruling: this adds a `Language.COBOL` branch in `project/`. The later spec on the `Language.COBOL` branches removes it, together with the others.

Test helpers. `tests/integration/cobol_helpers.py`: `first_region(vm)` returns the first region allocated after the run unit's. It reads the run-unit address from `RUN_UNIT_VAR` in `vm.call_stack[0].local_vars`, as `Address(str(value))`, and returns the earliest other region in allocation order.

`test_cobol_programs._first_region` returns `first_region(vm)`, imported from `tests.integration.cobol_helpers`. `test_return_code_does_not_corrupt_working_storage` uses `ws_region(vm, "RCISO")`.

- [ ] **Step 4: Run tests; expect green, then the whole suite**

Run: `uv run python -m pytest tests/unit/project/test_cobol_start_up.py tests/integration/test_cobol_run_unit.py -q`, then `uv run python -m pytest tests -q -x -n auto > /tmp/t1.log; tail -5 /tmp/t1.log`
Expected: all green. A failure that indexes regions by position is a Review Focus item. Fix it by locating the region by identity, as the helpers above do, never by reordering allocations.

- [ ] **Step 5: Mutation-check.** Two mutations, each of which must make the new tests fail:
  - drop `START_UP_PATH` from the dependency lists in `with_start_up`;
  - change the `Const` size to 4.

- [ ] **Step 6: Commit**

```bash
git add cobol_memory/region_id.py interpreter/cobol/run_unit.py interpreter/project/cobol_start_up.py interpreter/project/cobol_compile.py interpreter/project/compiler.py tests/
git commit -m "feat(cobol): every COBOL link carries a start-up module that allocates the run-unit region"
```

---

### Task 2: RETURN-CODE is published into the run-unit region

**Files:**
- Modify: `interpreter/cobol/lower_program_exit.py:58-77` (`emit_publish_run_unit_return_code`)
- Modify: `interpreter/cobol/return_code_readback.py` (read the region; delete the heap scan and `_return_code_region`)
- Modify: `interpreter/cobol/byte_builtins.py:620-640,1851` (delete `_builtin_cobol_publish_return_code` and its registration)
- Modify: `interpreter/cobol/cobol_constants.py:85` (delete `PUBLISH_RETURN_CODE`)
- Modify: `interpreter/vm/vm_types.py:186-190` (delete `cobol_run_unit_return_code`)
- Modify: `tests/unit/test_byte_builtins.py:418` (drop the name from the registry list)
- Test: `tests/unit/cobol/test_return_code_readback.py` (new); `tests/integration/test_cobol_return_code.py` (unchanged assertions)

**Interfaces:**
- Consumes: `RUN_UNIT_VAR`, `RUN_UNIT_LAYOUT`, `RUN_UNIT_RETURN_CODE`, `RegionId.RUN_UNIT` (Task 1)
- Produces: `read_return_code(vm: VMState) -> int`, with the same signature; `run_unit_region(vm: VMState) -> bytearray`

- [ ] **Step 1: Write the failing tests**

`tests/unit/cobol/test_return_code_readback.py`:

```python
"""read_return_code decodes the run-unit region's RETURN-CODE field."""

from interpreter.address import Address
from interpreter.cobol.return_code_readback import read_return_code
from interpreter.cobol.run_unit import RUN_UNIT_VAR
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm_types import StackFrame, VMState
from tests.covers import NotLanguageFeature, covers


def _vm_with_run_unit(region: bytes) -> VMState:
    vm = VMState()
    vm.region_set(Address("4096"), bytearray(region))
    vm.call_stack.append(StackFrame(function_name="__main__"))
    vm.call_stack[0].local_vars[RUN_UNIT_VAR] = typed_from_runtime(4096)
    return vm


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_return_code_decodes_the_run_unit_field():
    assert read_return_code(_vm_with_run_unit(b"\x00\x0c\x00\x00\x00\x00")) == 12
    assert read_return_code(_vm_with_run_unit(b"\xff\xfe\x00\x00\x00\x00")) == -2
    assert read_return_code(_vm_with_run_unit(bytes(6))) == 0
    assert not hasattr(VMState(), "cobol_run_unit_return_code")
```

Before writing it, check the `StackFrame` constructor and the `region_set` address type in `interpreter/vm/vm_types.py`, and build the VM the way existing unit tests do. `grep -rn "StackFrame(" tests/unit | head` shows the form.

- [ ] **Step 2: Run; expect failure**

Run: `uv run python -m pytest tests/unit/cobol/test_return_code_readback.py -q`
Expected: FAIL. The read-back ignores the region and scans the heap, and the VM still has the field.

- [ ] **Step 3: Implement**

`lower_program_exit.emit_publish_run_unit_return_code`:

```python
def emit_publish_run_unit_return_code(ctx: EmitContext, value_reg: Register, *, span: SourceSpan | None) -> None:
    """Write this program's RETURN-CODE into the run-unit region on the way out; the last program to end wins."""
    fl = RUN_UNIT_LAYOUT.lookup_or_raise(RUN_UNIT_RETURN_CODE)
    region_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=region_reg, name=RUN_UNIT_VAR), span=span)
    ctx._emit_write_region(
        region_reg=region_reg,
        offset_reg=ctx.const_to_reg(fl.offset, span=span),
        value_reg=value_reg,
        length=fl.byte_length,
        extent=whole_field_extent(fl, RegionId.RUN_UNIT),
        span=span,
    )
```

`return_code_readback.py`: replace the body with the region read, and delete the heap-scan fallback and its helper:

```python
def run_unit_region(vm: VMState) -> bytearray:
    """The run unit's region, found through the variable the start-up module declared."""
    return vm.region_get(Address(str(vm.call_stack[0].local_vars[RUN_UNIT_VAR].value)))


def read_return_code(vm: VMState) -> int:
    """The run unit's RETURN-CODE: the value the last program to end wrote into the run-unit region."""
    fl = RUN_UNIT_LAYOUT.lookup_or_raise(RUN_UNIT_RETURN_CODE)
    raw = bytes(run_unit_region(vm)[fl.offset : fl.offset + fl.byte_length])
    return int.from_bytes(raw, "big", signed=True)
```

If `region_get` is typed `bytearray | None`, use `match` with a `case bytearray()` arm and raise on the other, as jackal's `le_abend` does. No `is None` test. Delete the builtin, its constant, its registration, its name in the registry test, and the `VMState` field with its comment.

- [ ] **Step 4: Run; expect green**

Run: `uv run python -m pytest tests/unit/cobol/test_return_code_readback.py tests/integration/test_cobol_return_code.py tests/unit/test_byte_builtins.py -q`, then the whole suite as in Task 1.
Expected: all green. `test_stop_run_inside_a_subprogram_decides_the_run_unit_return_code` and `test_read_return_code_reports_the_entry_program_not_a_subprogram` pin the "last writer" rule.

- [ ] **Step 5: Mutation-check.** Two mutations, each of which must make tests fail:
  - write at offset 2 instead of `fl.offset`;
  - drop the publish from the `STOP RUN` path in `lower_arithmetic.py:2587`.

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(cobol): RETURN-CODE is published into the run-unit region; VMState loses cobol_run_unit_return_code"
```

---

### Task 3: FUNCTION RANDOM follows IBM, with its state in the run-unit region

**Files:**
- Modify: `interpreter/cobol/run_unit.py` (add the pure generator: `next_state`, `value_of`)
- Modify: `interpreter/cobol/byte_builtins.py:1312-1344,1888` (replace `_builtin_random` with `_builtin_random_next_state` and `_builtin_random_value`)
- Modify: `interpreter/cobol/cobol_constants.py:128` (`RANDOM` becomes `RANDOM_NEXT_STATE = "__random_next_state"` and `RANDOM_VALUE = "__random_value"`)
- Modify: `interpreter/cobol/lower_arithmetic.py:402,486-518` (drop `RANDOM` from `_INTRINSIC_FUNCTIONS`; lower it in `lower_function_operand`)
- Modify: `interpreter/vm/vm_types.py:181-184` (delete `cobol_random`, `cobol_random_seed`)
- Modify: `tests/unit/test_byte_builtins.py:469,2474-2518` (registry names; replace `TestRandom`)
- Test: `tests/unit/cobol/test_run_unit_random.py` (new); `tests/integration/test_cobol_run_unit.py` (add RANDOM tests)

**Interfaces:**
- Consumes: `RUN_UNIT_VAR`, `RUN_UNIT_LAYOUT`, `RANDOM_STATE` (Task 1)
- Produces, in `interpreter.cobol.run_unit`:
  - `advanced(state: int) -> int`: the next state of the current sequence, which starts at seed 0 when the state is 0;
  - `restarted(seed: int) -> int`: the first state of a new sequence at that seed;
  - `value_of(state: int) -> float`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/cobol/test_run_unit_random.py`:

```python
"""FUNCTION RANDOM per Enterprise COBOL 6.5 LR ch. 83: seed 0 by default, same seed same sequence, values in (0, 1)."""

from interpreter.cobol.run_unit import advanced, restarted, value_of
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_M = 2**31 - 1


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_the_sequence_starts_at_seed_zero_and_is_the_same_for_the_same_seed():
    unseeded = [advanced(0)]
    unseeded.append(advanced(unseeded[-1]))
    seeded_zero = [restarted(0)]
    seeded_zero.append(advanced(seeded_zero[-1]))
    assert unseeded == seeded_zero == [16807, 16807 * 16807 % _M]
    assert restarted(42) == restarted(42) == 43 * 16807 % _M
    assert restarted(2_147_483_646) == restarted(0)
    assert restarted(-5) == restarted(0)
    assert value_of(restarted(0)) == 16807 / _M
    assert 0 < value_of(_M - 1) < 1 and 0 < value_of(1) < 1
```

Replace `TestRandom` in `tests/unit/test_byte_builtins.py` with one class covering both builtins:
- `__random_next_state([state_bytes])` returns `list(advanced(state).to_bytes(4, "big"))`;
- with a seed argument (an int or a numeric string) it returns `restarted(seed)`'s bytes;
- a symbolic state or seed returns `_UNCOMPUTABLE`;
- `__random_value([state_bytes])` returns `value_of(state)`;
- both are registered, and `__random` is not.

Add to `tests/integration/test_cobol_run_unit.py`:

```python
@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_random_is_one_sequence_for_the_run_unit_and_reproducible():
    """A seed set in the caller continues in the callee; two runs agree."""
    callee = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. RNNEXT.", "DATA DIVISION.",
              "WORKING-STORAGE SECTION.", "01 WS-R PIC V9(9).", "PROCEDURE DIVISION.",
              "    COMPUTE WS-R = FUNCTION RANDOM.", "    GOBACK."]
    caller = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. RNSEED.", "DATA DIVISION.",
              "WORKING-STORAGE SECTION.", "01 WS-R PIC V9(9).", "PROCEDURE DIVISION.",
              "    COMPUTE WS-R = FUNCTION RANDOM(42).", "    CALL 'RNNEXT'.", "    GOBACK."]
    first = run_cobol_programs(caller, {"RNNEXT": callee})
    second = run_cobol_programs(caller, {"RNNEXT": callee})
    state_after_two = advanced(restarted(42))
    assert _run_unit(first)[2:6] == bytearray(state_after_two.to_bytes(4, "big"))
    assert ws_region(first, "RNSEED") == ws_region(second, "RNSEED")
    assert ws_region(first, "RNNEXT") == ws_region(second, "RNNEXT")
```

Also add a test that a symbolic seed leaves the region untouched. Do it at the builtin level: `__random_next_state` returns `_UNCOMPUTABLE`, and the `WRITE_REGION` handler's symbolic-value no-op is existing behaviour.

- [ ] **Step 2: Run; expect failure**

Run: `uv run python -m pytest tests/unit/cobol/test_run_unit_random.py tests/integration/test_cobol_run_unit.py tests/unit/test_byte_builtins.py -q`
Expected: ImportError on `advanced`, then the RANDOM integration test fails.

- [ ] **Step 3: Implement**

In `interpreter/cobol/run_unit.py`:

```python
_MODULUS = 2**31 - 1
_MULTIPLIER = 16807
_DISTINCT_SEEDS = _MODULUS - 1

logger = logging.getLogger(__name__)


def restarted(seed: int) -> int:
    if seed < 0:
        logger.warning("FUNCTION RANDOM seed %d is negative; IBM requires zero or positive -- using 0", seed)
    return _step(max(seed, 0) % _DISTINCT_SEEDS + 1)


def advanced(state: int) -> int:
    return _step(state) if state else restarted(0)


def value_of(state: int) -> float:
    return state / _MODULUS


def _step(state: int) -> int:
    return state * _MULTIPLIER % _MODULUS
```

In `byte_builtins.py`, both builtins ignore `vm`. They decode the state with `int.from_bytes(bytes(args[0].value), "big")`. They return `_UNCOMPUTABLE` when `_is_symbolic` holds for the state, or for the seed when one is given. They coerce the seed with `_coerce_intrinsic_int`, and branch on its result with `match` (`case int() as seed`, `case _`) rather than `is None`. They return the state as `list(next.to_bytes(4, "big"))`.

In `lower_arithmetic.lower_function_operand`, before the `_INTRINSIC_FUNCTIONS` lookup, handle `RANDOM`:

```python
    if operand.name.upper() == "RANDOM":
        return _lower_random(ctx, operand, materialised, span=span)
```

```python
def _lower_random(ctx: EmitContext, operand: FunctionCallOperand, materialised: MaterialisedSectionedLayout, *, span: SourceSpan | None) -> Register:
    """FUNCTION RANDOM: load the run unit's state, step it, store it back, and return its value."""
    fl = RUN_UNIT_LAYOUT.lookup_or_raise(RANDOM_STATE)
    extent = whole_field_extent(fl, RegionId.RUN_UNIT)
    region_reg, state_reg, next_reg, value_reg = (ctx.fresh_reg() for _ in range(4))
    offset_reg = ctx.const_to_reg(fl.offset, span=span)
    ctx.emit_inst(LoadVar(result_reg=region_reg, name=RUN_UNIT_VAR), span=span)
    ctx._emit_load_region(result_reg=state_reg, region_reg=region_reg, offset_reg=offset_reg, length=fl.byte_length, extent=extent, span=span)
    seed_regs = tuple(_lower_function_arg_to_string(ctx, arg, materialised, span=span) for arg in operand.args[:1])
    ctx.emit_inst(CallFunction(result_reg=next_reg, func_name=FuncName(BuiltinName.RANDOM_NEXT_STATE), args=(state_reg, *seed_regs)), span=span)
    ctx._emit_write_region(region_reg=region_reg, offset_reg=offset_reg, value_reg=next_reg, length=fl.byte_length, extent=extent, span=span)
    ctx.emit_inst(CallFunction(result_reg=value_reg, func_name=FuncName(BuiltinName.RANDOM_VALUE), args=(next_reg,)), span=span)
    return value_reg
```

`arithmetic_scale.py:66` lists `"RANDOM"` among the functions with a fractional result. Keep that entry. Delete `cobol_random` and `cobol_random_seed` from `VMState`.

- [ ] **Step 4: Run; expect green, then the whole suite**

Run: the Step 2 command, then the whole suite as in Task 1.

- [ ] **Step 5: Mutation-check.** Two mutations, each of which must make tests fail:
  - `advanced` restarting at seed 1 when the state is 0;
  - `_lower_random` dropping the `WRITE_REGION`, after which the callee repeats the caller's value.

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(cobol): FUNCTION RANDOM follows IBM -- seed 0 by default, one run-unit sequence held in the run-unit region; VMState loses its RANDOM fields"
```

---

### Task 4: Living docs, push, and the forge

**Files:**
- Modify: `docs/notes-on-vm-design.md` (its sections on `cobol_run_unit_return_code` and the RANDOM state)
- Forge: `vendor/red-dragon` submodule bump

- [ ] **Step 1:** Update the sections of `docs/notes-on-vm-design.md` on these fields: the start-up module and the run-unit region now hold this state, not the VM.
- [ ] **Step 1a:** Close red-dragon-clpn, the accepted deviation for the old generator.
- [ ] **Step 2:** Run red-dragon's full gate: `uv run pyright`, `uv run lint-imports`, `uv run python -m pytest tests -q -n auto`. Commit the docs and `bd export -o issues/issues.jsonl`. Push red-dragon `main`.
- [ ] **Step 3:** In the forge, `git -C vendor/red-dragon pull origin main`. Run `. ./bridge-env.sh`, then `make test-all`. jackal's step RC comes from `read_return_code`; cicada and squall compile through `compile_program`. Fix any forge code or test that takes the first region as WORKING-STORAGE: `cicada/tests/integration/cobol_helpers.py:52` `first_region`, the same way as red-dragon's helper. Commit the submodule bump with its fixes, and push.
