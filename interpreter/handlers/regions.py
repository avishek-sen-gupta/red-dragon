"""Region opcode handlers: ALLOC_REGION, WRITE_REGION, LOAD_REGION."""

# pyright: standard

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interpreter.vm.executor import HandlerContext

from interpreter.instructions import (
    AllocRegion,
    InstructionBase,
    LoadRegion,
    WriteRegion,
)
from interpreter.types.type_expr import UNKNOWN
from interpreter.types.typed_value import typed
from interpreter.vm.vm import (
    ExecutionResult,
    RegionWrite,
    StateUpdate,
    VMState,
    _is_symbolic,
    _resolve_reg,
)


def _handle_alloc_region(
    inst: InstructionBase, vm: VMState, ctx: HandlerContext
) -> ExecutionResult:
    """ALLOC_REGION: operands[0] = size literal. Allocate a zeroed byte region."""
    t = inst
    assert isinstance(t, AllocRegion)
    size = _resolve_reg(vm, t.size_reg).value
    if _is_symbolic(size):
        sym = vm.fresh_symbolic(hint="region_addr")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"alloc_region(symbolic size) → {sym.name}",
            )
        )
    base = vm.next_address
    return ExecutionResult.success(
        StateUpdate(
            new_regions={str(base): int(size)},
            register_writes={t.result_reg: typed(base, UNKNOWN)},
            reasoning=f"alloc_region({size}) → {base}",
        )
    )


def _handle_write_region(
    inst: InstructionBase, vm: VMState, ctx: HandlerContext
) -> ExecutionResult:
    """WRITE_REGION: operands = [region_reg, offset_reg, length_literal, value_reg].

    Write bytes from value_reg (a list[int]) into the region at the given offset.
    """
    t = inst
    assert isinstance(t, WriteRegion)
    region_addr = _resolve_reg(vm, t.region_reg).value
    offset = _resolve_reg(vm, t.offset_reg).value
    length = t.length
    value = _resolve_reg(vm, t.value_reg).value

    has_symbolic_elements = isinstance(value, list) and any(
        _is_symbolic(v) for v in value
    )
    if (
        _is_symbolic(region_addr)
        or _is_symbolic(offset)
        or _is_symbolic(value)
        or has_symbolic_elements
    ):
        return ExecutionResult.success(
            StateUpdate(
                reasoning="write_region(symbolic args) — no-op",
            )
        )

    data = list(value)[: int(length)] if isinstance(value, (list, bytes)) else []
    return ExecutionResult.success(
        StateUpdate(
            region_writes=[
                RegionWrite(address=int(region_addr) + int(offset), data=data)
            ],
            reasoning=f"write_region({region_addr}, offset={offset}, len={length})",
        )
    )


def _handle_load_region(
    inst: InstructionBase, vm: VMState, ctx: HandlerContext
) -> ExecutionResult:
    """LOAD_REGION: operands = [region_reg, offset_reg, length_literal].

    Read bytes from the region and return as list[int].
    """
    t = inst
    assert isinstance(t, LoadRegion)
    region_addr = _resolve_reg(vm, t.region_reg).value
    offset = _resolve_reg(vm, t.offset_reg).value
    length = t.length

    if _is_symbolic(region_addr) or _is_symbolic(offset):
        sym = vm.fresh_symbolic(hint="region_load")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load_region(symbolic) → {sym.name}",
            )
        )

    start = int(region_addr) + int(offset)
    n = int(length)
    raw = list(vm.read_at(start, n))
    data = raw + [0] * (n - len(raw))
    return ExecutionResult.success(
        StateUpdate(
            register_writes={t.result_reg: typed(data, UNKNOWN)},
            reasoning=f"load_region({region_addr}, offset={offset}, len={length}) = {data}",
        )
    )
