# pyright: standard
"""GETMAIN/FREEMAIN, TIME and STORAGE lower to IR over existing builtins only (the table's membership test, the TOD clock and the byte conversions) with nothing left symbolic, and a release finds its area in the allocation table or abends."""

from collections.abc import Callable, Sequence

import pytest

from interpreter.field_name import FieldName
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine import machine_allocation
from interpreter.hlasm.storage_services import (
    TABLE_HOLDS,
    emit_getmain_freemain,
    emit_storage,
)
from interpreter.hlasm.time_service import emit_time
from interpreter.instructions import CallFunction, InstructionBase, Symbolic
from interpreter.operator_kind import BinopKind
from interpreter.var_name import VarName
from interpreter.vm.vm_types import SymbolicValue, VMState
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.branching_vm import run_branching

REGISTER_IMAGES = {"__binary_bytes_to_int", "__int_to_binary_bytes"}
TABLE_LOOKUP = {str(TABLE_HOLDS), *REGISTER_IMAGES}

SERVICES: dict[str, tuple[Callable[[HlasmEmitter], None], set[str]]] = {
    "svc_10": (emit_getmain_freemain, TABLE_LOOKUP),
    "svc_11": (emit_time, {"__hlasm_tod_clock", *REGISTER_IMAGES}),
    "svc_120": (emit_storage, TABLE_LOOKUP),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("service", list(SERVICES))
def test_a_service_calls_only_existing_builtins(service: str):
    emit, builtins = SERVICES[service]
    emitter = HlasmEmitter()
    emit(emitter)
    instructions = emitter.instructions()

    assert (
        {str(i.func_name) for i in instructions if isinstance(i, CallFunction)},
        [i for i in instructions if isinstance(i, Symbolic)],
    ) == (builtins, [])


def _release_after_obtain(offset: int) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    emitter.store_gr32(0, emitter.int_(24))
    emitter.store_gr32(15, emitter.int_(0))
    emit_storage(emitter)
    moved = emitter.binop(BinopKind.ADD, emitter.load_gr32(1), emitter.int_(offset))
    emitter.store_gr32(1, moved)
    emitter.store_gr32(15, emitter.int_(1))
    emit_storage(emitter)
    return (*machine_allocation(), *emitter.instructions())


def _entries(vm: VMState) -> list[tuple[int, int]]:
    table = vm.current_frame.local_vars[VarName("__hlasm_allocations")].value
    entries = vm.heap_get(table.base).fields.values()
    return [
        (
            vm.heap_get(e.value.base).fields[FieldName("length")].value,
            vm.heap_get(e.value.base).fields[FieldName("subpool")].value,
        )
        for e in entries
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    "offset,abend,entries",
    [(0, [], [(-1, 0)]), (8, ["SA78"], [(24, 0)])],
)
def test_a_release_finds_its_area_in_the_table_or_abends(
    offset: int, abend: Sequence[str], entries: Sequence[tuple[int, int]]
):
    vm = run_branching(_release_after_obtain(offset))
    frame_vars = vm.current_frame.local_vars

    assert (
        [v.value for k, v in frame_vars.items() if k == VarName("__hlasm_abend")],
        _entries(vm),
        [
            v
            for v in vm.current_frame.registers.values()
            if isinstance(v.value, SymbolicValue)
        ],
    ) == (abend, entries, [])
