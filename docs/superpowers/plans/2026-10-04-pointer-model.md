# COBOL Pointer Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real COBOL pointers — `ADDRESS OF`, `NULL`, `USAGE POINTER`, `SET ADDRESS OF`, `SET … UP/DOWN BY`, pointer relations — with OMITTED parameters bound to NULL (red-dragon-ooil).

**Architecture:** Region handles become the integer base addresses of their segments in the flat address space (ADR-151), so every pointer operation is plain IR arithmetic on region registers. A NULL page below 4096 is governed by an injected `NullAccess` strategy. Pointer width follows the `LP` compile option, resolved into an `AddressingMode` that supplies the POINTER field type at ASG ingestion. The ProLeap bridge serialises `ADDRESS OF` and `NULL` as structured operands.

**Tech Stack:** Python 3.13 (uv, pytest, Black, Pyright, python-fp-lint ratchet), Java 17 + Maven (`proleap-bridge`).

**Spec:** `docs/superpowers/specs/2026-10-04-pointer-model-design.md`

## Global Constraints

- All work in `~/code/red-dragon`; the forge only gets the submodule bump and its own test/consumer fixes (Task 7).
- TDD: every task writes its failing test first and watches it fail.
- `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar` for every pytest run that parses COBOL; `make jar-force` after any Java change.
- The pre-commit fp-lint hook is a total-count ratchet: a task may not raise the violation count. Check each touched file with `uvx --from git+https://github.com/avishek-sen-gupta/python-fp-lint python-fp-lint check --config fp.json <files>` before and after. Do not use `match` with a guard (`case x if …`): the reassignment checker silently skips such files.
- Talisman flags the substrings `pass`, `key`, `secret`, `token` in changed lines: word code, docstrings and commit messages around them (no `key=` sort arguments — sort tuples instead).
- Default addressing mode `LP.LP32`; default null-access strategy `WarnAndIgnore`; first allocated address 4096; address 0 is NULL.
- `SET ADDRESS OF` applies to LINKAGE 01 and 77 items only.
- Out of scope: PROCEDURE-POINTER, FUNCTION-POINTER, CICS GETMAIN/ADDRESS, emulated z/OS control blocks, LINKAGE records not named by PROCEDURE DIVISION USING (they keep their zero-filled placeholder).
- Commit after each task with the full red-dragon suite green; push at the end of each task.

## Rulings made while planning

- **Ruling:** `AddressingMode` supplies only the pointer field's type (`S9(9) COMP-5` / `S9(18) COMP-5`); the largest storable address is that type's signed range, enforced because pointer stores encode with `INT_TO_BINARY_BYTES`, whose `int.to_bytes(..., signed=True)` raises `OverflowError` above it — the spec's separate "largest address" accessor would be unused. Cost if wrong: one property added later.
- **Ruling:** ALLOC'd regions are keyed in `VMState` by `Address(str(base))`, so the existing `Address(str(handle))` lookups in cicada, squall and the test helpers keep working; harness-named regions (`rgn_commarea`, `rgn_parm`) keep their names and are reached by address through the segment table. Cost if wrong: a second lookup path in `region_get`.
- **Ruling:** `test_region_vm`'s "unknown region loads as symbolic" case becomes "a load at an unallocated address past the last segment reads zeroes" — under the approved spec a handle is an address, and an address resolves through the address space. Cost if wrong: one test restored.
- **Ruling:** a POINTER field is marked on its `FieldLayout` (`holds_address`), because its type descriptor is indistinguishable from an `S9(9) COMP-5` binary. Cost if wrong: a category instead of a flag.

## Review Focus

1. A LINKAGE item rebound by `SET ADDRESS OF` in one paragraph and read in another PERFORMed later — the read must follow the new address (Task 5 test `test_set_address_of_rebinds_linkage_for_later_paragraphs`).
2. `ADDRESS OF lk` after `SET ADDRESS OF lk TO p` must equal `p`, not the old argument's address (same Task 5 test).
3. `SET ADDRESS OF` on a subordinate (non-01/77) LINKAGE item must fail at lowering, not silently rebind its 01 (Task 5 test `test_set_address_of_a_subordinate_item_is_rejected`).
4. A POINTER field REDEFINED as `S9(9) COMP` must expose the address as a number equal to `ADDRESS OF` (the CBSTM03A pattern) (Task 5 test `test_a_pointer_redefined_as_binary_holds_the_address`).
5. A harness-created region handed over by `call_arguments` must give the callee a non-NULL `ADDRESS OF` equal to that region's base (Task 1 test `test_call_arguments_hands_over_base_addresses`).

---

### Task 1: Region handles are base addresses

**Files:**
- Modify: `interpreter/handlers/regions.py` (`_handle_alloc_region`, `_handle_write_region`, `_handle_load_region`)
- Modify: `interpreter/vm/vm_types.py` (`VMState`: `next_address`, `_bases`, `_allocate`, `read_at`, `write_at`, `write_region`; `StateUpdate.new_regions` stays `dict[str, int]`)
- Modify: `interpreter/vm/vm.py` (`apply_update` new-region loop)
- Modify: `interpreter/cobol/call_arguments.py` (`_element` region field)
- Test: `tests/unit/test_region_vm.py`, `tests/unit/test_flat_memory.py`, `tests/unit/cobol/test_call_arguments.py`
- Modify (tests that build `Address(x.value)` from a handle without `str()`): `tests/integration/test_cobol_copybook_inlining.py:71,114,183,246,326`, `tests/integration/test_cobol_programs.py:5652,5729,5996,6238,6305,6374,8737`, `tests/integration/test_cobol_call_by_data_name.py:98`, `tests/integration/test_cobol_procedure_using.py:91`, `tests/unit/project/test_all_languages_execution.py:593` — wrap the value in `str(...)`.

**Interfaces:**
- Produces: `ALLOC_REGION` writes an `int` base address to its result register. `LOAD_REGION`/`WRITE_REGION` take an `int` region operand and act at `region + offset`. `VMState.next_address -> int`; `VMState.read_at(address: int, length: int) -> bytes` and `VMState.write_at(address: int, data: bytes) -> None` are the only access paths and resolve the containing segment by bisection. `call_arguments` stores each region's base `int` in the element's `region` field.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_region_vm.py`, replace the `addr_str.startswith("rgn_")` assertion in the ALLOC test with:

```python
        handle = unwrap(vm.current_frame.registers[Register("%rgn")])
        assert (handle, vm.segment_of(Address(str(handle)))) == (
            4096,
            Segment(base=4096, size=4),
        )
```

Replace the test that loads from `"rgn_nonexistent"` with:

```python
    def test_load_at_an_unallocated_address_reads_zeroes(self):
        """A handle is an address: one past the last segment reads zeroes."""
        vm = _make_vm()
        vm.current_frame.registers[Register("%rgn")] = 9000
        vm.current_frame.registers[Register("%off0")] = 0
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg=Register("%result"),
                operands=["%rgn", "%off0", 3],
            ),
        )
        assert unwrap(vm.current_frame.registers[Register("%result")]) == [0, 0, 0]
```

Add `from interpreter.vm.segment import Segment` to its imports. In `tests/unit/cobol/test_call_arguments.py`, add:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_call_arguments_hands_over_base_addresses() -> None:
    vm = VMState()
    vm.region_set(Address("rgn_first"), bytearray(3))
    vm.region_set(Address("rgn_commarea"), bytearray(2))

    array = call_arguments(vm, [Address("rgn_commarea")])
    element = vm.heap_get(
        vm.heap_get(array.value.base).fields[FieldName("0", FieldKind.INDEX)].value.base
    )

    assert (
        element.fields[FieldName("region")].value,
        element.fields[FieldName("offset")].value,
        element.fields[FieldName("omitted")].value,
    ) == (4099, 0, False)
```

and change the existing assertion `== (1, "rgn_commarea", 0, False)` to `== (1, 4096, 0, False)`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --no-sync python -m pytest tests/unit/test_region_vm.py tests/unit/cobol/test_call_arguments.py -q -n 0`
Expected: FAIL — the handle is `'rgn_…'`, the call-argument region is a string.

- [ ] **Step 3: Implement**

`interpreter/handlers/regions.py`, ALLOC:

```python
    base = vm.next_address
    return ExecutionResult.success(
        StateUpdate(
            new_regions={str(base): int(size)},
            register_writes={t.result_reg: typed(base, UNKNOWN)},
            reasoning=f"alloc_region({size}) → {base}",
        )
    )
```

WRITE: replace `RegionWrite(region_addr=Address(region_addr), …)` with the address-carrying write — add `address: int` to `RegionWrite` in `vm_types.py` in place of `region_addr`, build `RegionWrite(address=int(region_addr) + int(offset), data=data)`, and make `apply_update` call `vm.write_at(rw.address, bytes(rw.data))`. Update `scripts/nist_ccvs_tracer.py:63` to read `rw.address`.

LOAD:

```python
    start = int(region_addr) + int(offset)
    n = int(length)
    raw = list(vm.read_at(start, n))
    data = raw + [0] * (n - len(raw))
```

(delete the `region_get`-is-None symbolic branch).

`interpreter/vm/vm_types.py` — `VMState` gains `_bases: tuple[int, ...] = ()` and `_handles: tuple[Address, ...] = ()` (parallel, ascending), and:

```python
    @property
    def next_address(self) -> int:
        return self._next_address

    def _allocate(self, addr: Address, data: bytearray) -> None:
        base = self._next_address
        self._segments = {**self._segments, addr: Segment(base=base, size=len(data))}
        self._regions = {**self._regions, addr: data}
        self._bases = (*self._bases, base)
        self._handles = (*self._handles, addr)
        self._next_address = base + len(data)

    def _segment_index(self, address: int) -> int:
        """Index of the last segment starting at or before ``address``, or -1."""
        return bisect_right(self._bases, address) - 1
```

Rewrite `read_at` / `write_at` with a fast path: when `_segment_index(address)` finds a segment that contains `[address, address + length)`, slice that segment's `bytearray` directly; otherwise fall back to the existing `_pieces` walk (which logs the crossing). Delete `write_region`. `apply_update` (`vm.py`) allocates `new_regions` with `vm.region_set(Address(name), bytearray(size))` as now.

`interpreter/cobol/call_arguments.py`, `_element`: `FieldName("region"): typed(vm.segment_of(region).base, UNKNOWN)`.

Wrap each listed test site's `Address(<handle>.value)` as `Address(str(<handle>.value))`.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run --no-sync python -m pytest tests/unit/test_region_vm.py tests/unit/test_flat_memory.py tests/unit/cobol/test_call_arguments.py -q -n 0` — Expected: PASS.
Run: `PROLEAP_BRIDGE_JAR=… uv run --no-sync python -m pytest tests -q` — Expected: all pass, 0 failed.

- [ ] **Step 5: Lint, commit, push**

Check pyright and the fp-lint count on every touched file (must not rise). Then:

```bash
git add interpreter/handlers/regions.py interpreter/vm/vm_types.py interpreter/vm/vm.py interpreter/cobol/call_arguments.py scripts/nist_ccvs_tracer.py tests/
git commit -m "feat(vm): a region handle is its segment's base address"
git push
```

---

### Task 2: The NULL page and the null-access strategy

**Files:**
- Create: `interpreter/vm/null_access.py` (protocol), `interpreter/vm/warn_and_ignore.py`, `interpreter/vm/halt_on_null.py`, `interpreter/vm/null_address_access.py` (exception)
- Modify: `interpreter/vm/vm_types.py` (`VMState.null_access`; `read_at`/`write_at` route the NULL page)
- Modify: `interpreter/run.py` (`initial_vm_state`, `run`, `run_linked` accept `null_access`)
- Test: `tests/unit/test_null_access.py`

**Interfaces:**
- Consumes: `VMState.read_at`/`write_at` (Task 1).
- Produces: `class NullAccess(Protocol): def on_read(self, address: int, length: int) -> bytes; def on_write(self, address: int, length: int) -> None`. `WarnAndIgnore()` (returns `bytes(length)`, logs `"read of {n} bytes at NULL-page address {a}"` / `"write of {n} bytes at NULL-page address {a} dropped"`). `HaltOnNull()` raises `NullAddressAccess(address, length)`. `VMState.null_access: NullAccess = WarnAndIgnore()`. `initial_vm_state(io_provider=None, null_access: NullAccess = WarnAndIgnore())`; `run(..., null_access=WarnAndIgnore())`.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_null_access.py`)

```python
"""An access below 4096 goes to the VM's null-access strategy: warned and
ignored by default, or halting the run."""

import logging

import pytest

from interpreter.address import Address
from interpreter.vm.halt_on_null import HaltOnNull
from interpreter.vm.null_address_access import NullAddressAccess
from interpreter.vm.vm_types import VMState
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_default_strategy_reads_zeroes_drops_writes_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vm = VMState()
    vm.region_set(Address("rgn_a"), bytearray(b"ab"))

    with caplog.at_level(logging.WARNING):
        read = vm.read_at(8, 3)
        vm.write_at(0, b"\x01\x02")

    assert (read, bytes(vm.region_get(Address("rgn_a")) or b""), caplog.messages) == (
        b"\x00\x00\x00",
        b"ab",
        [
            "read of 3 bytes at NULL-page address 8",
            "write of 2 bytes at NULL-page address 0 dropped",
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_halting_strategy_stops_on_a_null_page_access() -> None:
    vm = VMState(null_access=HaltOnNull())

    with pytest.raises(NullAddressAccess, match="4 bytes at NULL-page address 16"):
        vm.read_at(16, 4)
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run --no-sync python -m pytest tests/unit/test_null_access.py -q -n 0` — Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

`interpreter/vm/null_access.py`:

```python
"""NullAccess — what the VM does with a read or write below the first address."""

from __future__ import annotations

from typing import Protocol


class NullAccess(Protocol):
    def on_read(self, address: int, length: int) -> bytes: ...

    def on_write(self, address: int, length: int) -> None: ...
```

`interpreter/vm/warn_and_ignore.py`:

```python
"""WarnAndIgnore — a NULL-page read gives zeroes and a write is dropped, both logged."""

from __future__ import annotations

import logging

from interpreter.vm.null_access import NullAccess

_LOG = logging.getLogger(__name__)


class WarnAndIgnore(NullAccess):
    def on_read(self, address: int, length: int) -> bytes:
        _LOG.warning("read of %d bytes at NULL-page address %d", length, address)
        return bytes(length)

    def on_write(self, address: int, length: int) -> None:
        _LOG.warning("write of %d bytes at NULL-page address %d dropped", length, address)
```

`interpreter/vm/null_address_access.py`:

```python
"""NullAddressAccess — raised when a run halts on a NULL-page access."""

from __future__ import annotations


class NullAddressAccess(Exception):
    def __init__(self, address: int, length: int) -> None:
        super().__init__(f"{length} bytes at NULL-page address {address}")
```

`interpreter/vm/halt_on_null.py`:

```python
"""HaltOnNull — a NULL-page access stops the run, as S0C4 would."""

from __future__ import annotations

from interpreter.vm.null_access import NullAccess
from interpreter.vm.null_address_access import NullAddressAccess


class HaltOnNull(NullAccess):
    def on_read(self, address: int, length: int) -> bytes:
        raise NullAddressAccess(address, length)

    def on_write(self, address: int, length: int) -> None:
        raise NullAddressAccess(address, length)
```

`VMState`: add `null_access: NullAccess = field(default_factory=WarnAndIgnore)`; at the top of `read_at` and `write_at`, `if address < FIRST_ADDRESS: return self.null_access.on_read(address, length)` (resp. `on_write(address, len(data))` then return). `interpreter/run.py`: give `initial_vm_state` a `null_access: NullAccess = WarnAndIgnore()` parameter that sets `vm.null_access`, and thread the same parameter through `run(...)` into its `initial_vm_state(...)` call.

- [ ] **Step 4: Run tests, then the full suite** — Expected: PASS; full suite 0 failed.

- [ ] **Step 5: Lint, commit, push**

```bash
git add interpreter/vm/null_access.py interpreter/vm/warn_and_ignore.py interpreter/vm/halt_on_null.py interpreter/vm/null_address_access.py interpreter/vm/vm_types.py interpreter/run.py tests/unit/test_null_access.py
git commit -m "feat(vm): an injected strategy governs the NULL page"
git push
```

---

### Task 3: The LP addressing mode and USAGE POINTER fields

**Files:**
- Create: `cobol_asg/lp.py` (enum), `cobol_asg/addressing_mode.py` (protocol + `addressing_mode(lp)`), `cobol_asg/lp32.py`, `cobol_asg/lp64.py`
- Modify: `cobol_asg/pic_parser.py` (`parse_pic(..., pointer_type)`), `cobol_asg/asg_types.py` (`CobolField` carries `pointer_type`), the `CobolASG.from_dict` chain (accepts `addressing_mode: AddressingMode = LP32_MODE`)
- Modify: `interpreter/cobol/data_layout.py` (`FieldLayout.holds_address`, set in `_flatten_field` from `cobol_field.usage == "POINTER"`)
- Modify: `interpreter/project/cobol_compile.py` (`compile_cobol(..., lp: LP = LP.LP32)` → `compile_cobol_module` → `get_frontend`), `interpreter/frontend.py` (`get_frontend(..., addressing_mode)`), `interpreter/cobol/cobol_frontend.py` (stores it; `lower_from_ast_dict` passes it to `CobolASG.from_dict`; `_lower_asg` passes it to `EmitContext`), `interpreter/cobol/emit_context.py` (`addressing_mode` constructor parameter and attribute)
- Test: `tests/unit/test_addressing_mode.py`, `tests/integration/test_cobol_pointer_fields.py`

**Interfaces:**
- Produces: `class LP(Enum): LP32 = "LP(32)"; LP64 = "LP(64)"`. `class AddressingMode(Protocol): pointer_type: CobolTypeDescriptor`. `Lp32()` → `parse_pic("S9(9)", usage="COMP-5")`; `Lp64()` → `parse_pic("S9(18)", usage="COMP-5")`. `addressing_mode(lp: LP) -> AddressingMode`. `LP32_MODE = Lp32()`. `FieldLayout.holds_address: bool = False`. `EmitContext.addressing_mode: AddressingMode`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_addressing_mode.py`:

```python
"""Each LP setting resolves to the pointer type of its width."""

from cobol_asg.addressing_mode import addressing_mode
from cobol_asg.lp import LP
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_lp_setting_gives_a_signed_binary_pointer_of_its_width() -> None:
    assert tuple(
        (
            addressing_mode(lp).pointer_type.byte_length,
            addressing_mode(lp).pointer_type.signed,
        )
        for lp in (LP.LP32, LP.LP64)
    ) == ((4, True), (8, True))
```

`tests/integration/test_cobol_pointer_fields.py`:

```python
"""A USAGE POINTER field takes the addressing mode's width: 4 bytes under
LP(32), 8 under LP(64), so the item after it moves accordingly."""

from cobol_asg.lp import LP
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRFLD.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-P USAGE POINTER.",
    "01 WS-X PIC X(2) VALUE 'AB'.",
    "PROCEDURE DIVISION.",
    "    STOP RUN.",
]


@covers(CobolFeature.USAGE_POINTER)
def test_a_pointer_field_is_as_wide_as_the_addressing_mode() -> None:
    def tail(lp: LP) -> str:
        ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}, lp=lp), "PTRFLD"))
        return ws.rstrip(b"\x00").decode("cp037")[-2:] + str(ws.index(b"\xc1\xc2"))

    assert (tail(LP.LP32), tail(LP.LP64)) == ("AB4", "AB8")
```

Add `USAGE_POINTER = "USAGE POINTER data items"` to `CobolFeature` (`interpreter/cobol/features.py`) if absent, and give `run_cobol_programs` in `tests/integration/cobol_helpers.py` an `lp: LP = LP.LP32` parameter forwarded to `compile_cobol`.

- [ ] **Step 2: Run to see them fail** — Expected: FAIL (modules missing; WS-X at offset 0).

- [ ] **Step 3: Implement**

`cobol_asg/lp.py`:

```python
"""LP — IBM's pointer-width compile option."""

from __future__ import annotations

from enum import Enum


class LP(Enum):
    LP32 = "LP(32)"
    LP64 = "LP(64)"
```

`cobol_asg/addressing_mode.py`:

```python
"""AddressingMode — what a pointer looks like under one LP setting."""

from __future__ import annotations

from typing import Protocol

from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.lp import LP


class AddressingMode(Protocol):
    @property
    def pointer_type(self) -> CobolTypeDescriptor: ...


def addressing_mode(lp: LP) -> AddressingMode:
    from cobol_asg.lp32 import Lp32
    from cobol_asg.lp64 import Lp64

    return {LP.LP32: Lp32(), LP.LP64: Lp64()}[lp]
```

(If the import-linter or pyright flags the function-level import, move `addressing_mode` into its own module `cobol_asg/resolve_addressing_mode.py` importing both classes at top level.)

`cobol_asg/lp32.py`:

```python
"""Lp32 — 4-byte pointers, IBM's default LP(32)."""

from __future__ import annotations

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.pic_parser import parse_pic


class Lp32(AddressingMode):
    @property
    def pointer_type(self) -> CobolTypeDescriptor:
        return parse_pic("S9(9)", usage="COMP-5")


LP32_MODE = Lp32()
```

`cobol_asg/lp64.py`: the same with `"S9(18)"` and docstring `"""Lp64 — 8-byte pointers, LP(64)."""`, no module constant.

`parse_pic` gains `pointer_type: CobolTypeDescriptor = _NO_POINTER_TYPE` (a module constant equal to today's zero-digit descriptor) and returns it for `usage == "POINTER"` (replacing the `pic.upper() == "POINTER"` branch and the `not pic` branch for that usage). `CobolField` gains `pointer_type: CobolTypeDescriptor` (passed into `parse_pic` in `__post_init__`), filled by `CobolField.from_dict(data, pointer_type)`, which `CobolASG.from_dict(data, addressing_mode=LP32_MODE)` supplies as `addressing_mode.pointer_type` down every field-building call. `_flatten_field` sets `holds_address=cobol_field.usage == "POINTER"`.

`compile_cobol(..., lp: LP = LP.LP32)`: `mode = addressing_mode(lp)` once, handed to every `compile_cobol_module(..., addressing_mode=mode)` → `get_frontend(..., addressing_mode=mode)` → `CobolFrontend(..., addressing_mode=mode)`, which uses it in `CobolASG.from_dict(data, mode)` and `EmitContext(..., addressing_mode=mode)`.

- [ ] **Step 4: Run tests, then the full suite** — Expected: PASS; 0 failed.

- [ ] **Step 5: Lint, commit, push**

```bash
git add cobol_asg/ interpreter/ tests/
git commit -m "feat(cobol): the LP option sizes USAGE POINTER fields"
git push
```

---

### Task 4: The bridge serialises ADDRESS OF and NULL as operands

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` (`serializeSet`, `serializeBasis`, `serializeBasisCtx`, `canonicalFigurative`, `canonicalFigurativeCtx`, CALL USING at :1540-1585; new `isAddressOfSpecialRegister`, `addressOfSpecialRegisterOperand`, `serializeSetOperand`)
- Create: `cobol_asg/set_operand.py` (typed operand), `cobol_asg/operand_kind.py` (enum)
- Modify: `cobol_asg/cobol_statements.py` (`SetStatement.targets/values: list[SetOperand]`; `CallUsingParam.address_of: bool`)
- Modify: `interpreter/cobol/lower_arithmetic.py` `lower_set` — read `operand.name` / `operand.value` where it read strings (no behaviour change)
- Test: `tests/cobol_asg/test_bridge_pointer_operands.py`

**Interfaces:**
- Produces: bridge JSON — SET `targets`/`values` (and BY `value`) are objects `{"kind": "ref"|"address_of"|"figurative"|"lit", "name": …, "qualifiers": […], "subscripts": […], "value": …}`; a relation operand `{"kind": "address_of", "name": …, "qualifiers": […]}`; `NULL`/`NULLS` → `{"kind": "figurative", "value": "NULL"}`; a CALL USING param gains `"address_of": true` with `name` the bare identifier. Python: `class OperandKind(Enum): REF, ADDRESS_OF, FIGURATIVE, LIT`; `@dataclass(frozen=True) class SetOperand: kind: OperandKind; name: str = ""; qualifiers: tuple[str, ...] = (); subscripts: tuple[str, ...] = (); value: str = ""` with `from_dict`. `SetStatement.targets: list[SetOperand]`, `values: list[SetOperand]`. `CallUsingParam.address_of: bool = False`.

- [ ] **Step 1: Write the failing test** (`tests/cobol_asg/test_bridge_pointer_operands.py`)

```python
"""The bridge serialises ADDRESS OF and NULL as operands in SET, conditions
and CALL USING, instead of glued text."""

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import bridge_jar, to_fixed

_SOURCE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRJSON.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 P USAGE POINTER.",
    "01 X PIC X(2).",
    "LINKAGE SECTION.",
    "01 LK PIC X(2).",
    "PROCEDURE DIVISION USING LK.",
    "    SET P TO ADDRESS OF X.",
    "    SET ADDRESS OF LK TO P.",
    "    SET P TO NULL.",
    "    IF ADDRESS OF LK = NULL",
    "        CALL 'SUB' USING BY VALUE ADDRESS OF X",
    "    END-IF.",
    "    GOBACK.",
]


def _statements(node, kind):
    if isinstance(node, dict):
        yield from ([node] if node.get("type") == kind else [])
        for value in node.values():
            yield from _statements(value, kind)
    if isinstance(node, list):
        for value in node:
            yield from _statements(value, kind)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_address_of_and_null_are_structured_operands() -> None:
    out = RealSubprocessRunner().run(["java", "-jar", bridge_jar()], to_fixed(_SOURCE))
    doc = json.loads(out)
    sets = [(s["targets"], s["values"]) for s in _statements(doc, "SET")]
    relation = next(_statements(doc, "IF"))["condition"]["relation"]
    using = next(_statements(doc, "CALL"))["using"][0]

    assert (sets, relation["left"], relation["right"], using) == (
        [
            (
                [{"kind": "ref", "name": "P", "qualifiers": [], "subscripts": []}],
                [{"kind": "address_of", "name": "X", "qualifiers": [], "subscripts": []}],
            ),
            (
                [{"kind": "address_of", "name": "LK", "qualifiers": [], "subscripts": []}],
                [{"kind": "ref", "name": "P", "qualifiers": [], "subscripts": []}],
            ),
            (
                [{"kind": "ref", "name": "P", "qualifiers": [], "subscripts": []}],
                [{"kind": "figurative", "value": "NULL"}],
            ),
        ],
        {"kind": "address_of", "name": "LK", "qualifiers": [], "subscripts": []},
        {"kind": "figurative", "value": "NULL"},
        {"name": "X", "type": "VALUE", "address_of": True},
    )
```

(Match `bridge_jar`/`to_fixed`/runner usage to the existing `tests/cobol_asg/test_bridge_computed_goto.py`; if `RealSubprocessRunner().run` returns an object, read its stdout as that file does.)

- [ ] **Step 2: Run to see it fail** — `make jar-force` first; Expected: FAIL (glued text `"ADDRESSOFX"`).

- [ ] **Step 3: Implement**

Java: add, beside `isLengthOfSpecialRegister` (B:2419):

```java
    private static boolean isAddressOfSpecialRegister(org.antlr.v4.runtime.tree.ParseTree node) {
        return node instanceof CobolParser.SpecialRegisterContext
                && ((CobolParser.SpecialRegisterContext) node).ADDRESS() != null;
    }

    private static CobolParser.SpecialRegisterContext addressOfSpecialRegisterOperand(
            org.antlr.v4.runtime.ParserRuleContext operand) {
        return (CobolParser.SpecialRegisterContext)
                walkOperand(operand, StatementSerializer::isAddressOfSpecialRegister);
    }

    private static JsonObject addressOfNode(CobolParser.SpecialRegisterContext sr) {
        JsonObject node = refNodeOf(sr.identifier());
        node.addProperty("kind", "address_of");
        return node;
    }
```

where `refNodeOf(IdentifierContext)` builds `{"kind":"ref","name":leafDataName(id),"qualifiers":[…],"subscripts":[…]}` the way `serializeRef` does for a call (reuse `serializeRef` on the identifier's call when available). Add `serializeSetOperand(ParserRuleContext ctx, ValueStmt or Call)` returning, in order: `addressOfNode` if `addressOfSpecialRegisterOperand(ctx)` is non-null; `{"kind":"figurative","value":"NULL"}` if the text is `NULL`/`NULLS`; the canonical figurative if `canonicalFigurativeCtx` matches; a `ref` node for an identifier; `litNode(text)` otherwise. Use it for every SET target and value (TO and BY). In `serializeBasis` and `serializeBasisCtx`, return `addressOfNode` when the basis holds an ADDRESS OF special register, and map `NULL`/`NULLS` to `{"kind":"figurative","value":"NULL"}` in `canonicalFigurative`/`canonicalFigurativeCtx`. CALL USING: when `br.getByReferenceType()`, `ByContentType` or `ByValueType` is `ADDRESS_OF`, add `"address_of": true` and set `name` to the identifier's leaf data name.

Python: `cobol_asg/operand_kind.py`:

```python
"""OperandKind — what a SET operand is."""

from __future__ import annotations

from enum import Enum


class OperandKind(Enum):
    REF = "ref"
    ADDRESS_OF = "address_of"
    FIGURATIVE = "figurative"
    LIT = "lit"
```

`cobol_asg/set_operand.py`:

```python
"""SetOperand — one target or value of a SET statement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cobol_asg.operand_kind import OperandKind


@dataclass(frozen=True)
class SetOperand:
    kind: OperandKind
    name: str = ""
    qualifiers: tuple[str, ...] = ()
    subscripts: tuple[str, ...] = ()
    value: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, str | Sequence[str]]) -> SetOperand:
        return cls(
            kind=OperandKind(str(data["kind"])),
            name=str(data.get("name", "")),
            qualifiers=tuple(data.get("qualifiers", ())),
            subscripts=tuple(data.get("subscripts", ())),
            value=str(data.get("value", "")),
        )
```

(If fp-lint flags the `@classmethod` as `no-classmethod-utility`, follow the existing `SetStatement.from_dict` pattern in `cobol_statements.py` instead.)

`SetStatement.from_dict`: `targets=[SetOperand.from_dict(t) for t in data.get("targets", [])]`, `values=[SetOperand.from_dict(v) for v in (data.get("values", []) if set_type == "TO" else [data["value"]] if "value" in data else [])]`. `CallUsingParam.from_dict`: `address_of=data.get("address_of", False)`. In `lower_set`, read a target's `.name` and a value's `.name` (ref) or `.value` (lit/figurative) exactly where the strings were read; behaviour unchanged for refs, literals and 88-levels.

- [ ] **Step 4: Run tests, then the full suite** — Expected: PASS; 0 failed (SET-on-88, SET index and SET TO TRUE tests unchanged).

- [ ] **Step 5: Lint, commit, push**

```bash
git add proleap-bridge/src cobol_asg/ interpreter/cobol/lower_arithmetic.py tests/cobol_asg/test_bridge_pointer_operands.py
git commit -m "feat(bridge): ADDRESS OF and NULL are structured operands"
git push
```

---

### Task 5: Pointer behaviour in the lowering

**Files:**
- Create: `interpreter/cobol/lower_pointer.py` (`emit_address_of`, `emit_store_address`, `lower_pointer_set`, `lower_set_address_of`)
- Modify: `interpreter/cobol/lower_arithmetic.py` `lower_set` (dispatch pointer forms to `lower_pointer.py`)
- Modify: `interpreter/cobol/condition_lowering.py` (`_lower_expr_dict` `"address_of"` kind; `_lower_figurative` `NULL` → `const 0`)
- Modify: `interpreter/cobol/lower_call.py` `_address` (`param.address_of` → a fresh `CALL_ARGUMENT` copy holding the address)
- Test: `tests/integration/test_cobol_pointers.py`

**Interfaces:**
- Consumes: int handles (Task 1), `EmitContext.addressing_mode`, `FieldLayout.holds_address` (Task 3), `SetOperand`/`OperandKind`, `CallUsingParam.address_of` (Task 4), `LinkageBinding(name, start, length, region_reg, delta_reg)` and `materialised.linkage_binding(fl)`.
- Produces: `emit_address_of(ctx, name: str, qualifiers: Sequence[str], subscripts: Sequence[str], materialised, *, span) -> Register` (region register + field offset register, via `Binop("+")`). `emit_store_address(ctx, target_ref: ResolvedFieldRef, target_rr: Register, address: Register, *, span) -> None` (`INT_TO_BINARY_BYTES(address, pointer_type.byte_length, True)` then a region write). `lower_set_address_of(ctx, target: SetOperand, address: Register, materialised, *, span) -> None`.

- [ ] **Step 1: Write the failing tests** (`tests/integration/test_cobol_pointers.py`)

```python
"""COBOL pointers: ADDRESS OF, NULL, USAGE POINTER, SET ADDRESS OF, SET UP BY
and pointer relations."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-TABLE.",
    "   05 WS-ROW PIC X(2) OCCURS 3.",
    "01 WS-INIT PIC X(6) VALUE 'AABBCC'.",
    "PROCEDURE DIVISION.",
    "    MOVE WS-INIT TO WS-TABLE.",
    "    CALL 'PTRSUB' USING WS-TABLE.",
    "    STOP RUN.",
]

_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRSUB.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-P USAGE POINTER.",
    "01 WS-Q USAGE POINTER.",
    "01 WS-NUM REDEFINES WS-Q PIC S9(9) COMP.",
    "01 WS-SEEN PIC X(8) VALUE SPACES.",
    "01 WS-FLAGS PIC X(4) VALUE '----'.",
    "LINKAGE SECTION.",
    "01 LK-TABLE PIC X(6).",
    "01 LK-ROW PIC X(2).",
    "PROCEDURE DIVISION USING LK-TABLE.",
    "    SET WS-P TO ADDRESS OF LK-TABLE.",
    "    SET WS-P UP BY 2.",
    "    SET ADDRESS OF LK-ROW TO WS-P.",
    "    PERFORM READ-ROW.",
    "    SET WS-Q TO ADDRESS OF LK-ROW.",
    "    IF WS-Q = WS-P MOVE 'E' TO WS-FLAGS(1:1).",
    "    IF ADDRESS OF LK-ROW = WS-P MOVE 'A' TO WS-FLAGS(2:1).",
    "    SET WS-Q TO NULL.",
    "    IF WS-Q = NULL MOVE 'N' TO WS-FLAGS(3:1).",
    "    IF WS-P NOT = NULL MOVE 'P' TO WS-FLAGS(4:1).",
    "    MOVE 'ZZ' TO LK-ROW.",
    "    GOBACK.",
    "READ-ROW.",
    "    MOVE LK-ROW TO WS-SEEN(1:2).",
]


@covers(CobolFeature.ADDRESS_OF, CobolFeature.USAGE_POINTER)
def test_set_address_of_rebinds_linkage_for_later_paragraphs() -> None:
    vm = run_cobol_programs(_MAIN, {"PTRSUB": _SUB})
    main = bytes(ws_region(vm, "PTRMAIN"))
    sub = bytes(ws_region(vm, "PTRSUB"))

    assert (main[:6].decode("cp037"), sub[8:10].decode("cp037"), sub[16:20].decode("cp037")) == (
        "AAZZCC",
        "BB",
        "EANP",
    )


@covers(CobolFeature.USAGE_POINTER)
def test_a_pointer_redefined_as_binary_holds_the_address() -> None:
    program = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. PTRNUM.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-Q USAGE POINTER.",
        "01 WS-NUM REDEFINES WS-Q PIC S9(9) COMP.",
        "01 WS-X PIC X(2) VALUE 'XY'.",
        "01 WS-HIT PIC X VALUE 'N'.",
        "PROCEDURE DIVISION.",
        "    SET WS-Q TO ADDRESS OF WS-X.",
        "    SET WS-Q UP BY 1.",
        "    IF WS-NUM = 4096 + 4 + 1 MOVE 'Y' TO WS-HIT.",
        "    STOP RUN.",
    ]
    ws = bytes(ws_region(run_cobol_programs(program, {}), "PTRNUM"))

    assert (int.from_bytes(ws[:4], "big"), ws[6:7].decode("cp037")) == (4101, "Y")


@covers(CobolFeature.ADDRESS_OF)
def test_set_address_of_a_subordinate_item_is_rejected() -> None:
    program = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. PTRBAD.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-P USAGE POINTER.",
        "LINKAGE SECTION.",
        "01 LK-REC.",
        "   05 LK-PART PIC X(2).",
        "PROCEDURE DIVISION USING LK-REC.",
        "    SET ADDRESS OF LK-PART TO WS-P.",
        "    GOBACK.",
    ]

    with pytest.raises(ValueError, match="SET ADDRESS OF LK-PART: only a LINKAGE 01 or 77"):
        run_cobol_programs(program, {}, strict=True)
```

Notes for the implementer: `WS-NUM = 4096 + 4 + 1` in the second test is the WS region's base (the first region allocated in that run — confirm by printing `vm.segment_of(...)` once; if the program-singleton allocation order puts another region first, replace the literal with the actual base and say so in the commit message). `strict=True` must make `run_cobol_programs` propagate a lowering error instead of logging "subprogram … failed — skipping" — add that keyword to the helper if it is absent (it already raises for a main program; check). Add `ADDRESS_OF = "ADDRESS OF special register"` to `CobolFeature`.

- [ ] **Step 2: Run to see them fail** — Expected: FAIL (SET of pointer forms unsupported).

- [ ] **Step 3: Implement** (`interpreter/cobol/lower_pointer.py`)

```python
"""Pointer lowering: ADDRESS OF, pointer stores, SET ADDRESS OF."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.set_operand import SetOperand
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction, LoadVar, StoreVar
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register


def emit_address_of(
    ctx: EmitContext,
    name: str,
    qualifiers: Sequence[str],
    subscripts: Sequence[str],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """The item's address: its region register plus its offset."""
    ref, region_reg = ctx.resolve_field_ref(
        name, materialised, tuple(qualifiers), subscripts=tuple(subscripts), span=span
    )
    address = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(result_reg=address, operator=resolve_binop("+"), left=region_reg, right=ref.offset_reg),
        span=span,
    )
    return address


def emit_store_address(
    ctx: EmitContext,
    target_ref: ResolvedFieldRef,
    target_rr: Register,
    address: Register,
    *,
    span: SourceSpan | None,
) -> None:
    """Write an address into a POINTER field as the addressing mode's binary;
    one too large for the field raises in the encoding."""
    pointer_type = ctx.addressing_mode.pointer_type
    data = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=data,
            func_name=FuncName(BuiltinName.INT_TO_BINARY_BYTES),
            args=(
                address,
                ctx.const_to_reg(pointer_type.byte_length, span=span),
                ctx.const_to_reg(True, span=span),
            ),
        ),
        span=span,
    )
    ctx.emit_write_bytes(target_rr, target_ref, data, span=span)
```

`emit_write_bytes(region_reg, ref, data_reg, *, span)` is a thin `EmitContext` method over the existing `_emit_write_region(region_reg=…, offset_reg=ref.offset_reg, value_reg=data_reg, length=ref.fl.byte_length, extent=ref.extent, span=span)` — add it if no public equivalent exists.

`lower_set_address_of(ctx, target, address, materialised, *, span)`:
1. Resolve `target.name` with `ctx.resolve_field_ref`; find its binding with `materialised.linkage_binding(ref.fl)`; raise `ValueError(f"SET ADDRESS OF {target.name}: only a LINKAGE 01 or 77 item can be rebound")` unless the field is in LINKAGE and `binding.name.upper() == target.name.upper()`.
2. `delta = 0 - binding.start` (a `const_to_reg(-binding.start)`).
3. `StoreVar` the address and delta into the binding's two vars (`__linkage_<name>_region` / `_delta` — expose the two var-name helpers from `lower_data_division.py` as public functions `linkage_region_var(name)` / `linkage_delta_var(name)`), then `LoadVar` each var back into `binding.region_reg` and `binding.delta_reg`, so every later access in any paragraph sees the new binding.

`lower_set` (TO form): for each target —
- `OperandKind.ADDRESS_OF` target → `lower_set_address_of(ctx, target, _address_value(value), …)`;
- a target whose `FieldLayout.holds_address` → `emit_store_address(ctx, ref, rr, _address_value(value), …)`;
- otherwise the existing path.
`_address_value(value)`: `ADDRESS_OF` → `emit_address_of(...)`; `FIGURATIVE` with `value == "NULL"` → `const_to_reg(0)`; a `REF` to a POINTER field → `ctx.emit_decode_field(...)` (binary decode gives the int); a `REF` to a LINKAGE 01 via `ADDRESS OF` is already covered. BY form on a `holds_address` target: decode, `Binop(+/-)` the step, `emit_store_address`.

`condition_lowering._lower_expr_dict`: `"address_of"` → `emit_address_of(ctx, expr["name"], expr.get("qualifiers", ()), expr.get("subscripts", ()), materialised, span=span)`. `_lower_figurative`: `value == "NULL"` → `ctx.const_to_reg(0, span=span)`.

`lower_call._address`: if `param.address_of`, compute `emit_address_of(ctx, param.name, (), (), materialised, span=span)`, allocate a `CALL_ARGUMENT` copy of `pointer_type.byte_length` bytes, store the address into it with `INT_TO_BINARY_BYTES`, and return `(copy, zero)` — reuse `_copy_extent` and the `_literal_copy` allocation shape.

- [ ] **Step 4: Run tests, then the full suite** — Expected: PASS; 0 failed.

- [ ] **Step 5: Lint, commit, push**

```bash
git add interpreter/cobol/lower_pointer.py interpreter/cobol/lower_arithmetic.py interpreter/cobol/condition_lowering.py interpreter/cobol/lower_call.py interpreter/cobol/lower_data_division.py interpreter/cobol/emit_context.py interpreter/cobol/features.py tests/
git commit -m "feat(cobol): ADDRESS OF, SET ADDRESS OF, pointer SET and relations"
git push
```

---

### Task 6: OMITTED and unsupplied parameters bind NULL; docs

**Files:**
- Modify: `interpreter/cobol/lower_data_division.py` (`_bind_parameter` absent branch: `_store_null` in place of `_store_zeroed`; `_placeholder` for unbound records keeps `_store_zeroed`)
- Modify: `docs/frontend-design/cobol.md` (CALL row; new rows for SET pointer forms, ADDRESS OF, USAGE POINTER), `docs/architectural-design-decisions.md` (ADR-152), `README.md` (feature line)
- Test: `tests/integration/test_cobol_omitted_null.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: an OMITTED or unsupplied LINKAGE parameter has region register 0 and shift `-start`, so `ADDRESS OF` it is 0.

- [ ] **Step 1: Write the failing test** (`tests/integration/test_cobol_omitted_null.py`)

```python
"""An OMITTED or unsupplied parameter is NULL: ADDRESS OF it tests equal to
NULL, a supplied one does not, and under the halting strategy touching the
omitted one stops the run."""

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.vm.halt_on_null import HaltOnNull
from interpreter.vm.null_address_access import NullAddressAccess
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. OMMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-B PIC X(2) VALUE 'BB'.",
    "PROCEDURE DIVISION.",
    "    CALL 'OMSUB' USING OMITTED WS-B.",
    "    STOP RUN.",
]


def _sub(touch: bool) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. OMSUB.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-SEEN PIC X(3) VALUE '---'.",
        "LINKAGE SECTION.",
        "01 LK-A PIC X(2).",
        "01 LK-B PIC X(2).",
        "01 LK-C PIC X(2).",
        "PROCEDURE DIVISION USING LK-A LK-B LK-C.",
        "    IF ADDRESS OF LK-A = NULL MOVE 'A' TO WS-SEEN(1:1).",
        "    IF ADDRESS OF LK-B NOT = NULL MOVE 'B' TO WS-SEEN(2:1).",
        "    IF ADDRESS OF LK-C = NULL MOVE 'C' TO WS-SEEN(3:1).",
        *(["    MOVE LK-A TO WS-SEEN(1:2)."] if touch else []),
        "    GOBACK.",
    ]


@covers(CobolFeature.CALL_USING_OMITTED, CobolFeature.ADDRESS_OF)
def test_an_omitted_or_unsupplied_parameter_is_null() -> None:
    ws = bytes(ws_region(run_cobol_programs(_MAIN, {"OMSUB": _sub(False)}), "OMSUB"))

    with pytest.raises(NullAddressAccess):
        run_cobol_programs(_MAIN, {"OMSUB": _sub(True)}, null_access=HaltOnNull())
    assert ws[:3].decode("cp037") == "ABC"
```

Give `run_cobol_programs` a `null_access` keyword forwarded to `initial_vm_state(null_access=…)`.

- [ ] **Step 2: Run to see it fail** — Expected: FAIL (`ADDRESS OF LK-A` is the zero-filled region's base, not NULL).

- [ ] **Step 3: Implement**

```python
def _store_null(ctx: EmitContext, record: LinkageRecord) -> None:
    _store_binding(ctx, record, ctx.const_to_reg(0, span=None), ctx.const_to_reg(0, span=None))
```

(`_store_binding` computes `delta = offset - record.start`, so `ADDRESS OF` the record is `0 + start + delta = 0`.) Use it in `_bind_parameter`'s `absent` label; leave `_placeholder` on `_store_zeroed`.

Docs: in `docs/frontend-design/cobol.md` change the CALL row's "An absent or OMITTED parameter, and a LINKAGE 01 USING does not name, bind zero-filled storage of their own" to "An absent or OMITTED parameter binds NULL — `ADDRESS OF` it is NULL, and touching it goes to the VM's null-access strategy; a LINKAGE 01 USING does not name binds zero-filled storage of its own", and add rows for `SET p TO ADDRESS OF x | NULL | q`, `SET ADDRESS OF lk TO …`, `SET p UP/DOWN BY n`, `ADDRESS OF` in conditions and CALL USING, and `USAGE POINTER` (LP-sized). Append ADR-152 ("COBOL pointers are addresses in the flat space") to `docs/architectural-design-decisions.md` in the ADR-151 format: context (no pointers; OMITTED undetectable — ooil), decision (handles are base addresses; NULL-page strategy; LP → AddressingMode; bridge operands; OMITTED binds NULL), consequences (pointer ops are plain IR; writes to an OMITTED parameter are dropped with a warning; unbound LINKAGE records keep zero-filled placeholders). Add "COBOL pointers (`ADDRESS OF`, `USAGE POINTER`, `SET ADDRESS OF`; ADR-152)" to the README feature list beside ADR-151's line.

- [ ] **Step 4: Run the test, then the full suite** — Expected: PASS; 0 failed. If an existing test wrote to an OMITTED parameter and read it back, report it rather than changing its assertion.

- [ ] **Step 5: Lint, close the issue, commit, push**

```bash
bd close red-dragon-ooil --reason "OMITTED and unsupplied parameters bind NULL; ADDRESS OF is supported"
bd export -o issues/issues.jsonl
git add interpreter/cobol/lower_data_division.py docs/ README.md tests/integration/test_cobol_omitted_null.py tests/integration/cobol_helpers.py issues/issues.jsonl
git commit -m "feat(cobol): an OMITTED or unsupplied parameter is NULL (Closes red-dragon-ooil)"
git push
```

---

### Task 7: The forge bump

**Files (in `~/code/red-dragon-forge`):**
- Modify: `vendor/red-dragon` (submodule pointer to Task 6's commit)
- Modify: `cicada/tests/integration/cics/test_ceedays_stub.py:80-81` (`Address(str(ws_handle))`)
- Modify, only if the suites show it: cobble consumers of `SetStatement.targets/values` (`cobble/cobble/dataflow/depgraph/flows.py:300-302` reads `.name`, which `SetOperand` has; `desugar.py:378-385` `_arm_subject`) and any forge test fixture that hand-writes SET JSON with string targets.

- [ ] **Step 1: Bump and build**

```bash
cd ~/code/red-dragon-forge/vendor/red-dragon && git fetch -q && git checkout -q <task-6-sha> && cd ../..
make jar-force
```

- [ ] **Step 2: Fix the one known forge site and run every suite**

Apply the `str(...)` wrap in `test_ceedays_stub.py`. Then:

```bash
make db2-status   # restart with make db2-restart if it reports down
. ./bridge-env.sh && SQUALL_DIR=squall . squall/db2/dsn-env.sh && make test-all
```

Expected: every suite passes. A cobble failure from string SET targets in an ASG cache means re-running `cobble-parse-corpus --force` for that corpus, not a code change; a failure in a hand-written fixture means updating it to the object form.

- [ ] **Step 3: Commit and push**

```bash
git add vendor/red-dragon cicada/tests/integration/cics/test_ceedays_stub.py
git commit -m "chore: bump red-dragon to <task-6-sha> (COBOL pointer model)"
git push
```
