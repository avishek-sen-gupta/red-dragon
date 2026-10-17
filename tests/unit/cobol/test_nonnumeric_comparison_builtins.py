"""What a nonnumeric comparison runs: a numeric item's digit image and space padding, in IR."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_numeric.number import from_literal
from interpreter.cobol.digit_image_ir import emit_value_digit_image
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _digit_image(
    value: ParamValue, digits: int, decimals: int, scale: int
) -> ParamValue:
    td = CobolTypeDescriptor(
        category=CobolDataCategory.COMP3,
        total_digits=digits,
        decimal_digits=decimals,
        signed=True,
        scale=scale,
    )

    def image(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        (value_reg,) = registers
        return emit_value_digit_image(e, value_reg, td)

    return run_emitted(image, (value,))


_DIGIT = (
    "__nibble_set(__nibble_set(240, 'low', __list_get("
    "__cobol_prepare_digits(value, 1, 0, False, 0), 0)), 'high', 15)"
)


@covers(CobolFeature.COMPARISON_OPERATORS)
def test_digit_image_is_every_digit_position_without_the_sign_and_p_positions_as_zeros():
    images = [
        _digit_image(*shape)
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
def test_a_symbolic_value_flows_into_the_digit_image():
    image = _digit_image(SymbolicValue("value"), 1, 0, 0)
    assert isinstance(image, SymbolicValue)
    assert image.constraints == [
        "__bytes_to_string([SymbolicValue(name='sym_3', type_hint="
        f"{_DIGIT!r}, constraints=[{_DIGIT!r}])], 'ebcdic')"
    ]


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
