# pyright: standard
"""The GPR, access-register and floating-point-register regions, the FPC, condition code and program mask, read and written through the VM."""

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine import (
    access_register_allocation,
    floating_point_allocation,
    machine_allocation,
)
from interpreter.instructions import Const
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName
from tests.unit.hlasm.straight_line_vm import register_value, run_straight_line


def _const(emitter: HlasmEmitter, value: int) -> Register:
    reg = emitter.fresh_reg()
    emitter.emit_inst(Const.int_(reg, value))
    return reg


def _store_then_load(emitter: HlasmEmitter) -> tuple[Register, ...]:
    emitter.store_gr64(15, _const(emitter, 0x1_0000_0005))
    seven = _const(emitter, 7)
    emitter.store_gr32(15, seven)
    emitter.store_gr64(3, _const(emitter, -2))
    emitter.set_cc(_const(emitter, 3))
    return (
        emitter.load_gr64(15),
        emitter.load_gr32(15),
        emitter.load_gr32(3),
        emitter.load_gr64(3),
    )


def test_gpr_words_are_big_endian_with_the_low_word_at_plus_four():
    emitter = HlasmEmitter()
    loads = _store_then_load(emitter)
    vm = run_straight_line((*machine_allocation(), *emitter.instructions()), {})
    frame_vars = vm.current_frame.local_vars
    gprs = frame_vars[VarName("__hlasm_gprs")].value
    assert [register_value(vm, reg).value for reg in loads] == [
        0x1_0000_0007,
        7,
        0xFFFFFFFE,
        (1 << 64) - 2,
    ]
    assert [vm.load(gprs + 120, 8), vm.load(gprs + 24, 8), vm.load(gprs, 24)] == [
        [0, 0, 0, 1, 0, 0, 0, 7],
        [0xFF] * 7 + [0xFE],
        [0] * 24,
    ]
    assert [
        frame_vars[VarName("__hlasm_cc")].value,
        frame_vars[VarName("__hlasm_pm")].value,
        frame_vars[VarName("__hlasm_tod_last")].value,
    ] == [3, 0b0110, 0]
    assert [emitter.fresh_label("hl"), emitter.fresh_label("hl")] == [
        CodeLabel("hl_0"),
        CodeLabel("hl_1"),
    ]


def test_access_registers_are_sixteen_zero_words_in_their_own_region():
    emitter = HlasmEmitter()
    emitter.store_ar(15, _const(emitter, 0x1_2345_6789))
    loads = (emitter.load_ar(15), emitter.load_ar(0))
    vm = run_straight_line(
        (*machine_allocation(), *access_register_allocation(), *emitter.instructions()),
        {},
    )
    ars = vm.current_frame.local_vars[VarName("__hlasm_ars")].value
    gprs = vm.current_frame.local_vars[VarName("__hlasm_gprs")].value

    assert [register_value(vm, reg).value for reg in loads] == [0x23456789, 0]
    assert [vm.load(ars, 60), vm.load(ars + 60, 4), vm.load(gprs, 128)] == [
        [0] * 60,
        [0x23, 0x45, 0x67, 0x89],
        [0] * 128,
    ]


def test_floating_point_registers_are_sixteen_zero_doublewords_and_short_forms_use_the_high_word():
    emitter = HlasmEmitter()
    emitter.store_fpr(15, _const(emitter, 0x1_0123_4567_89AB_CDEF))
    emitter.store_fpr_high32(15, _const(emitter, 0xFEDC_BA98))
    loads = (emitter.load_fpr(15), emitter.load_fpr_high32(15), emitter.load_fpr(0))
    vm = run_straight_line(
        (*machine_allocation(), *floating_point_allocation(), *emitter.instructions()),
        {},
    )
    frame_vars = vm.current_frame.local_vars

    assert [register_value(vm, reg).value for reg in loads] == [
        0xFEDCBA98_89ABCDEF,
        0xFEDCBA98,
        0,
    ]
    assert [
        vm.load(frame_vars[VarName("__hlasm_fprs")].value, 120),
        vm.load(frame_vars[VarName("__hlasm_gprs")].value, 128),
        frame_vars[VarName("__hlasm_fpc")].value,
    ] == [[0] * 120, [0] * 128, 0]
