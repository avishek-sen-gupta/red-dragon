# pyright: standard
"""The GPR region, condition code and program mask, read and written through the VM."""

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine import machine_allocation
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
    ] == [3, 0b0110]
    assert [emitter.fresh_label("hl"), emitter.fresh_label("hl")] == [
        CodeLabel("hl_0"),
        CodeLabel("hl_1"),
    ]
