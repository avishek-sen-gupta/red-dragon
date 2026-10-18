"""IS NUMERIC decided in IR: from the stored bytes of a zoned or packed decimal item, and from character data."""

from __future__ import annotations

import pytest

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.class_test_ir import (
    emit_is_digits,
    emit_packed_is_numeric,
    emit_zoned_is_numeric,
)
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _zoned(
    data: ParamValue, length: int, signed: bool, sign_index: int, separate: bool
) -> ParamValue:
    fl = FieldLayout(
        name="ITEM",
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=length - separate,
            signed=signed,
            sign_separate=separate,
            sign_leading=sign_index == 0,
        ),
        offset=0,
        byte_length=length,
    )

    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        (stored,) = registers
        return emit_zoned_is_numeric(e, stored, fl)

    return run_emitted(emit, (data,))


@pytest.mark.parametrize(
    ("data", "signed", "sign_index", "separate", "numeric"),
    [
        (b"\xf1\xf2\xf3", False, 2, False, True),
        (b"\xf1\xf2\xc3", False, 2, False, False),
        (b"\xf1\xf2\xc1\xc2", False, 3, False, False),
        (b"\xf1\xf2\xc3", True, 2, False, True),
        (b"\xf1\xf2\xd3", True, 2, False, True),
        (b"\xf1\xf2\xf3", True, 2, False, True),
        (b"\xf1\xf2\xe3", True, 2, False, False),
        (b"\xf1\xc2\xc3", True, 2, False, False),
        (b"\xc1\xf2\xf3", True, 0, False, True),
        (b"\x4e\xf2\xf3", True, 0, True, True),
        (b"\xf2\xf3\x60", True, 2, True, True),
        (b"\xf2\xf3\xf4", True, 2, True, False),
        (b"\x40\xf3\x60", True, 2, True, False),
        (b"\x00\x00", False, 1, False, False),
        (b"\xfa\xf2\xf3", False, 2, False, False),
    ],
)
def test_zoned_digits_and_sign(
    data: bytes, signed: bool, sign_index: int, separate: bool, numeric: bool
) -> None:
    assert _zoned(list(data), len(data), signed, sign_index, separate) is numeric


@pytest.mark.parametrize(
    ("data", "signed", "numeric"),
    [
        (b"\x12\x3f", False, True),
        (b"\x12\x3c", False, False),
        (b"\x12\x3c", True, True),
        (b"\x12\x3d", True, True),
        (b"\x12\x3f", True, True),
        (b"\x12\x3e", True, False),
        (b"\x1a\x3c", True, False),
        (b"\xa2\x3c", True, False),
    ],
)
def test_packed_digit_and_sign_nibbles(
    data: bytes, signed: bool, numeric: bool
) -> None:
    td = CobolTypeDescriptor(
        category=CobolDataCategory.COMP3, total_digits=3, signed=signed
    )

    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        (stored,) = registers
        return emit_packed_is_numeric(e, stored, td, len(data))

    assert run_emitted(emit, (list(data),)) is numeric


@covers(CobolFeature.CLASS_CONDITION)
def test_true_only_when_every_character_is_a_digit() -> None:
    """ANSI X3.23-1985 VI-6.15.4: an alphanumeric item is NUMERIC only when
    it consists entirely of the characters 0 through 9."""

    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        (text,) = registers
        return emit_is_digits(e, text)

    values = ["01234", "+1234", "-1234", "12.34", "12 ", "", "\u0661"]
    assert [run_emitted(emit, (v,)) for v in values] == [
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


@covers(CobolFeature.CLASS_CONDITION)
def test_a_symbolic_stored_byte_flows_into_the_class_test() -> None:
    numeric = _zoned(SymbolicValue("stored"), 1, False, 0, False)
    assert isinstance(numeric, SymbolicValue)
    assert numeric.constraints == [
        "__nibble_get(__list_get(stored, 0), 'high') BinopKind.EQ 15"
        " BinopKind.AND __nibble_get(__list_get(stored, 0), 'low') BinopKind.LE 9"
    ]
