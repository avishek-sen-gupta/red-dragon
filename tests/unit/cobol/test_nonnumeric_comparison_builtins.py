"""What a nonnumeric comparison runs: a numeric item's digit image builtin and space padding in IR."""

from __future__ import annotations

from cobol_numeric.number import from_literal
from interpreter.cobol.byte_builtins import _builtin_cobol_digit_image
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm_types import VMState
from tests.covers import covers
from tests.unit.cobol.emitted_ir import run_emitted


def _args(*values):
    return [typed_from_runtime(v) for v in values]


@covers(CobolFeature.COMPARISON_OPERATORS)
def test_digit_image_is_every_digit_position_without_the_sign_and_p_positions_as_zeros():
    images = [
        _builtin_cobol_digit_image(_args(*shape), VMState()).value
        for shape in (
            (from_literal("-1234"), 4, 0, 0),
            (42, 6, 0, 0),
            (from_literal("-12.5"), 5, 2, 0),
            (5000, 1, 0, 3),
            (from_literal("-200"), 1, 0, 2),
            (from_literal("0.005"), 1, 0, -3),
        )
    ]
    assert images == ["1234", "000042", "01250", "5000", "200", "5"]


@covers(CobolFeature.COMPARISON_OPERATORS)
def test_pad_to_extends_only_the_shorter_operand_with_spaces():
    def pad(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        value, other = registers
        return e.ctx.emit_pad_to(value, other, span=None)

    padded = [
        run_emitted(pad, (value, other))
        for value, other in (("AB", "ABCDE"), ("ABCDE", "AB"), ("", "XYZ"))
    ]
    assert padded == ["AB   ", "ABCDE", "   "]
