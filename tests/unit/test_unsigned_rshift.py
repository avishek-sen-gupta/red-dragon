# pyright: standard
"""The VM evaluates >>> as a logical right shift of a 64-bit two's-complement image."""

from interpreter.operator_kind import BinopKind
from interpreter.vm.vm import Operators


def test_unsigned_rshift_evaluates():
    shift = BinopKind.UNSIGNED_RSHIFT.value
    assert Operators.eval_binop(shift, 8, 1) == 4
    assert Operators.eval_binop(shift, -1, 60) == 0xF
    assert Operators.eval_binop(shift, -8, 1) == 0x7FFFFFFFFFFFFFFC
    assert Operators.eval_binop(shift, 1 << 64, 0) == 0
