"""A signed zoned item's operational sign taken out of its bytes and put back, in IR."""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.sign_position import SignPosition
from interpreter.cobol.zoned_sign_ir import emit_restore_sign, emit_strip_sign
from interpreter.register import Register
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _strip(data: ParamValue, index: int, separate: bool) -> ParamValue:
    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        (stored,) = registers
        return emit_strip_sign(e, stored, SignPosition(index=index, separate=separate))

    return run_emitted(emit, (data,))


def _restore(
    digits: list[int], original: list[int], index: int, separate: bool
) -> ParamValue:
    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        digits_reg, original_reg = registers
        return emit_restore_sign(
            e, digits_reg, original_reg, SignPosition(index=index, separate=separate)
        )

    return run_emitted(emit, (digits, original))


@covers(CobolFeature.INSPECT_TALLYING, CobolFeature.SIGN_CLAUSE)
def test_strip_leaves_only_the_digit_characters():
    stripped = [
        _strip(*shape)
        for shape in (
            ([0xF1, 0xF2, 0xD3], 2, False),
            ([0xC1, 0xF2, 0xF3], 0, False),
            ([0x60, 0xF1, 0xF2], 0, True),
            ([0xF1, 0xF2, 0x4E], 2, True),
            ([0xF1, 0x40, 0x40], 2, False),
        )
    ]
    assert stripped == [
        [0xF1, 0xF2, 0xF3],
        [0xF1, 0xF2, 0xF3],
        [0xF1, 0xF2],
        [0xF1, 0xF2],
        [0xF1, 0x40, 0x40],
    ]


@covers(CobolFeature.INSPECT_REPLACING, CobolFeature.SIGN_CLAUSE)
def test_restore_puts_the_original_sign_back_on_the_new_digits():
    restored = [
        _restore(*shape)
        for shape in (
            ([0xF9, 0xF2, 0xF3], [0xF1, 0xF2, 0xD3], 2, False),
            ([0xF1, 0xF2, 0xF7], [0xF1, 0xF2, 0xD3], 2, False),
            ([0xF7, 0xF2, 0xF3], [0xC1, 0xF2, 0xF3], 0, False),
            ([0xF1, 0xF2, 0xC1], [0xF1, 0xF2, 0xD3], 2, False),
            ([0xF1, 0xF2, 0xF4], [0xF1, 0x40, 0x40], 2, False),
            ([0xF9, 0xF2], [0x60, 0xF1, 0xF2], 0, True),
            ([0xF3, 0xF4], [0xF1, 0xF2, 0x60], 2, True),
        )
    ]
    assert restored == [
        [0xF9, 0xF2, 0xD3],
        [0xF1, 0xF2, 0xD7],
        [0xC7, 0xF2, 0xF3],
        [0xF1, 0xF2, 0xC1],
        [0xF1, 0xF2, 0xF4],
        [0x60, 0xF9, 0xF2],
        [0xF3, 0xF4, 0x60],
    ]


@covers(CobolFeature.INSPECT_TALLYING, CobolFeature.SIGN_CLAUSE)
def test_a_symbolic_sign_byte_flows_into_the_stripped_digits():
    stripped = _strip(SymbolicValue("stored"), 0, False)
    assert isinstance(stripped, SymbolicValue)
    assert stripped.constraints == ["__list_set(stored, 0, __list_get(stored, 0))"]
