"""DISPLAY of a binary or packed decimal item: its value as zoned decimal digit characters, in IR."""

from __future__ import annotations

from decimal import Decimal

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.digit_image_ir import emit_display_image
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _image(value: ParamValue, digits: int, decimals: int, scale: int) -> ParamValue:
    td = CobolTypeDescriptor(
        category=CobolDataCategory.BINARY,
        total_digits=digits,
        decimal_digits=decimals,
        signed=True,
        scale=scale,
    )

    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        (value_reg,) = registers
        return emit_display_image(e, value_reg, td)

    return run_emitted(emit, (value,))


_DIGIT = (
    "__nibble_set(__nibble_set(240, 'low', __list_get("
    "__cobol_prepare_digits(value, 1, 0, False, 0), 0)), 'high', 15)"
)


@covers(CobolFeature.DISPLAY, CobolFeature.USAGE_COMP)
def test_digits_of_the_picture_with_a_negative_value_overpunched():
    assert [
        _image(Decimal(20), 4, 0, 0),
        _image(Decimal(-20), 4, 0, 0),
        _image(Decimal("-1.5"), 3, 1, 0),
        _image(Decimal(-9), 1, 0, 0),
        _image(Decimal(12300), 3, 0, 2),
    ] == ["0020", "002}", "01N", "R", "123"]


@covers(CobolFeature.DISPLAY, CobolFeature.USAGE_COMP)
def test_a_symbolic_value_flows_into_the_displayed_digits():
    image = _image(SymbolicValue("value"), 1, 0, 0)
    assert isinstance(image, SymbolicValue)
    assert image.constraints == [
        "__bytes_to_string([SymbolicValue(name='sym_5', type_hint="
        f"{_DIGIT!r}, constraints=[{_DIGIT!r}])], 'ebcdic')"
    ]
