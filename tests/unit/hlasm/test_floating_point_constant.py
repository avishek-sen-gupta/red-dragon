# pyright: standard
"""E, D and L DC operands encode as the HLASM Language Reference (SC26-4940-09) defines them: HFP without a type extension rounds by adding one in the first lost bit and refuses what it cannot hold (pp. 148-153), H and Q take rounding modes 1, 4-7 and saturate (p. 151), B and D are IEEE conversions with rounding modes R1, R4-R7 and R8-R15 (pp. 154-157), and the special values follow p. 158. Images z390 assembles alike are also in tests/z390/test_dc_image_differential.py."""

from __future__ import annotations

import pytest

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.string_nominal import StringNominal
from interpreter.hlasm.bit_length_image import BitLengthImage
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_characteristic_out_of_range import DcCharacteristicOutOfRange
from interpreter.hlasm.dc_encoding import encode_dc
from interpreter.hlasm.dc_exponent_out_of_range import DcExponentOutOfRange
from interpreter.hlasm.dc_length_wrong import DcLengthWrong
from interpreter.hlasm.dc_precision_lost import DcPrecisionLost
from interpreter.hlasm.dc_warning import DcWarning
from interpreter.hlasm.dc_warning_kind import DcWarningKind

ORIGIN = MacroOrigin(kind="MACRO", file="src/t.asm", line=7, macro="GEN", depth=1)
IMPLICIT_BYTES = {"E": 4, "D": 8, "L": 16}


def _item(
    code: str,
    value: str,
    length: int = 0,
    scale: int = 0,
    exponent: int = 0,
    unit: LengthUnit = LengthUnit.BYTE,
) -> DcItem:
    return DcItem(
        type=code[0],
        extension=code[1:],
        duplication=1,
        length=length or IMPLICIT_BYTES[code[0]],
        length_unit=unit,
        explicit_length=length != 0,
        scale=scale,
        exponent=exponent,
        offset=0,
        bit_offset=0,
        nominal=StringNominal(kind="STRING", value=value),
    )


def _hex(item: DcItem) -> str:
    pieces = encode_dc(item, ORIGIN)
    assert not isinstance(pieces, BitLengthImage)
    return "".join(
        bytes(piece.image).hex().upper()
        for piece in pieces
        if isinstance(piece, ConstantImage)
    )


def _bits(item: DcItem) -> tuple[int, ...]:
    image = encode_dc(item, ORIGIN)
    assert isinstance(image, BitLengthImage)
    return image.values


def test_hexadecimal_constants_without_extension_round_up_scale_and_take_exponents():
    assert [
        _hex(_item("E", "46.415")),
        _hex(_item("E", "46415E-3")),
        _hex(_item("E", "+464.15E-1")),
        _hex(_item("E", "+.46415E+2")),
        _hex(_item("E", ".46415", exponent=2)),
        _hex(_item("D", "+46,-3.729,+473", exponent=4)),
        _hex(_item("E", "0.1")),
        _hex(_item("E", "-0")),
        _hex(_item("E", "1", scale=2)),
        _hex(_item("E", "0.1", scale=1)),
        _hex(_item("L", "1", scale=3)),
        _hex(_item("L", "-1")),
        _hex(_item("L", "1E-70")),
        _hex(_item("E", "0.1", 5)),
        _hex(_item("D", "0.1", 3)),
        _hex(_item("L", "0.1", 10)),
        _hex(_item("E", "1E-78")),
        _hex(_item("E", "16777224")),
    ] == [
        "422E6A3D",
        "422E6A3D",
        "422E6A3D",
        "422E6A3D",
        "422E6A3D",
        "45704E00" "00000000" "C491AA00" "00000000" "46482C90" "00000000",
        "4019999A",
        "00000000",
        "43001000",
        "4101999A",
        "44000100" "00000000" "36000000" "00000000",
        "C1100000" "00000000" "B3000000" "00000000",
        "06B0AF48" "EC79ACE8" "78372D83" "5A9DF0C7",
        "401999999A",
        "40199A",
        "40199999" "99999999" "329A",
        "001DA48D",
        "47100001",
    ]
    assert [
        _bits(_item("E", "1", 12, unit=LengthUnit.BIT)),
        _bits(_item("E", "-1", 13, unit=LengthUnit.BIT)),
        _bits(_item("E", "0", 8, unit=LengthUnit.BIT)),
    ] == [(0x411,), (0x1822,), (0,)]


def test_hexadecimal_h_and_q_constants_round_by_mode_and_saturate():
    assert [
        _hex(_item("EH", "1E+60R1")),
        _hex(_item("DH", "-2.5E10R4")),
        _hex(_item("LH", "3.712E-3R5")),
        _hex(_item("EH", "0.1R5")),
        _hex(_item("EH", "-0.1R6")),
        _hex(_item("EH", "-0.1R7")),
        _hex(_item("EH", "-0")),
        _hex(_item("EH", "1E80")),
        _hex(_item("EH", "-1E80R5")),
        _hex(_item("EH", "1E-79")),
        _hex(_item("EH", "-1E-79R6")),
        _hex(_item("EH", "1E-90")),
        _hex(_item("EH", "1", exponent=-2147483648)),
        _hex(_item("EH", "(MAX)")),
        _hex(_item("EH", "-(min)")),
        _hex(_item("EH", "(DMIN)")),
        _hex(_item("LH", "(MAX)")),
        _hex(_item("LH", "(MIN)")),
        _hex(_item("LQ", "0.1")),
        _hex(_item("EH", "16777224")),
        _hex(_item("EH", "16777224R4")),
    ] == [
        "729F4F27",
        "C95D21DB" "A0000000",
        "3EF34506" "9A4DF47F" "30993D53" "47A5B0FF",
        "40199999",
        "C0199999",
        "C019999A",
        "80000000",
        "7FFFFFFF",
        "FFFFFFFF",
        "0002F6DB",
        "8002F6DA",
        "00000000",
        "00000000",
        "7FFFFFFF",
        "80100000",
        "00000001",
        "7FFFFFFF" "FFFFFFFF" "71FFFFFF" "FFFFFFFF",
        "00100000" "00000000" "72000000" "00000000",
        "40199999" "99999999" "32999999" "9999999A",
        "47100001",
        "47100000",
    ]
    assert _bits(_item("EH", "(MIN)", 12, unit=LengthUnit.BIT)) == (0x001,)


def test_binary_constants_convert_by_rounding_mode_into_any_length():
    assert [
        _hex(_item("EB", "1.5")),
        _hex(_item("EB", "-0")),
        _hex(_item("DB", "0.1")),
        _hex(_item("LB", "0.1")),
        _hex(_item("EB", "0.1")),
        _hex(_item("EB", "0.1R1")),
        _hex(_item("EB", "0.1R5")),
        _hex(_item("EB", "0.1R6")),
        _hex(_item("EB", "-0.1R6")),
        _hex(_item("EB", "-0.1R7")),
        _hex(_item("EB", "3.4028235E38")),
        _hex(_item("EB", "1E39")),
        _hex(_item("EB", "1E39R5")),
        _hex(_item("EB", "-1E39R6")),
        _hex(_item("EB", "1E-46")),
        _hex(_item("EB", "1E-50R6")),
        _hex(_item("DB", "4.9E-324")),
        _hex(_item("DB", "1", exponent=300)),
        _hex(_item("EB", "1", 3)),
        _hex(_item("EB", "16777217")),
        _hex(_item("EB", "16777217R1")),
    ] == [
        "3FC00000",
        "80000000",
        "3FB99999" "9999999A",
        "3FFB9999" "99999999" "99999999" "9999999A",
        "3DCCCCCD",
        "3DCCCCCD",
        "3DCCCCCC",
        "3DCCCCCD",
        "BDCCCCCC",
        "BDCCCCCD",
        "7F7FFFFF",
        "7F800000",
        "7F7FFFFF",
        "FF7FFFFF",
        "00000000",
        "00000001",
        "00000000" "00000001",
        "7E37E43C" "8800759C",
        "3F8000",
        "4B800000",
        "4B800001",
    ]
    assert [
        _bits(_item("EB", "1", 12, unit=LengthUnit.BIT)),
        _bits(_item("EB", "1", 9, unit=LengthUnit.BIT)),
        _bits(_item("LB", "1.5", 20, unit=LengthUnit.BIT)),
    ] == [(0x3F8,), (0x07F,), (0x3FFF8,)]


def test_binary_special_values_and_their_minimum_lengths():
    assert [
        _hex(_item("EB", value))
        for value in (
            "(INF)",
            "-(INF)",
            "(NAN)",
            "-(nan)",
            "(QNAN)",
            "(SNAN)",
            "(MAX)",
            "(MIN)",
            "(DMIN)",
        )
    ] + [_hex(_item("DB", "(SNAN)")), _hex(_item("LB", "(MAX)"))] == [
        "7F800000",
        "FF800000",
        "7FC00000",
        "FFC00000",
        "7FE00000",
        "7FA00000",
        "7F7FFFFF",
        "00800000",
        "00000001",
        "7FF40000" "00000000",
        "7FFEFFFF" "FFFFFFFF" "FFFFFFFF" "FFFFFFFF",
    ]
    assert [
        _bits(_item("EB", "(NAN)", 11, unit=LengthUnit.BIT)),
        _bits(_item("EB", "(MAX)", 9, unit=LengthUnit.BIT)),
        _bits(_item("EB", "(DMIN)", 10, unit=LengthUnit.BIT)),
        _bits(_item("DB", "(MIN)", 12, unit=LengthUnit.BIT)),
        _bits(_item("LB", "(MAX)", 17, unit=LengthUnit.BIT)),
    ] == [(0x3FE,), (0x0FE,), (0x001,), (0x001,), (0x0FFFD,)]
    assert _hex(_item("LB", "(MIN)", 2)) == "0001"
    with pytest.raises(DcLengthWrong) as refused:
        encode_dc(_item("DB", "(INF)", 13, unit=LengthUnit.BIT), ORIGIN)
    assert str(refused.value) == (
        "DB'(INF)' at line 7 of src/t.asm needs a length of at least 14 bits"
        " — ASMA068S"
    )


def test_binary_ties_at_one_bit_of_precision_go_to_the_even_image():
    assert [
        _bits(_item("EB", value, 9, unit=LengthUnit.BIT))
        for value in ("1.5", "3", "6", "1.5R1", "3R1")
    ] + [_hex(_item("LB", "1.5", 2)), _hex(_item("LB", "3", 2))] == [
        (0x080,),
        (0x080,),
        (0x082,),
        (0x080,),
        (0x081,),
        "4000",
        "4000",
    ]


def _warnings(item: DcItem) -> tuple[DcWarning, ...]:
    pieces = encode_dc(item, ORIGIN)
    assert not isinstance(pieces, BitLengthImage)
    return tuple(
        warning
        for piece in pieces
        if isinstance(piece, ConstantImage)
        for warning in piece.warnings
    )


def test_type_extended_constants_warn_of_overflow_underflow_and_inexact_values():
    codes_and_values = (
        ("EB", "1E39"),
        ("EB", "1E-50"),
        ("EB", "0.1"),
        ("EB", "1.5,(MAX)"),
        ("DD", "1E400"),
        ("ED", "15E-102"),
        ("ED", "1234567.8"),
        ("ED", "1.5"),
        ("EH", "1E80"),
        ("EH", "1E-79"),
        ("EH", "0.1"),
        ("EH", "1,(DMIN)"),
        ("E", "0.1"),
    )
    assert [_warnings(_item(code, value)) for code, value in codes_and_values] == [
        (DcWarning("EB'1E39'", DcWarningKind.OVERFLOW),),
        (DcWarning("EB'1E-50'", DcWarningKind.UNDERFLOW),),
        (DcWarning("EB'0.1'", DcWarningKind.INEXACT),),
        (),
        (DcWarning("DD'1E400'", DcWarningKind.OVERFLOW),),
        (DcWarning("ED'15E-102'", DcWarningKind.UNDERFLOW),),
        (DcWarning("ED'1234567.8'", DcWarningKind.INEXACT),),
        (),
        (DcWarning("EH'1E80'", DcWarningKind.OVERFLOW),),
        (DcWarning("EH'1E-79'", DcWarningKind.UNDERFLOW),),
        (DcWarning("EH'0.1'", DcWarningKind.INEXACT),),
        (),
        (),
    ]
    image = encode_dc(_item("EB", "0.1", 32, unit=LengthUnit.BIT), ORIGIN)
    assert image == BitLengthImage(
        (0x3DCCCCCD,), 32, (DcWarning("EB'0.1'", DcWarningKind.INEXACT),)
    )


def test_decimal_constants_keep_the_written_quantum_and_round_by_mode():
    assert [
        _hex(_item("ED", "1.5")),
        _hex(_item("DD", "1.50")),
        _hex(_item("LD", "-0.001")),
        _hex(_item("ED", "-0")),
        _hex(_item("ED", "0.000")),
        _hex(_item("ED", "1234567.8")),
        _hex(_item("ED", "1234567.5R9")),
        _hex(_item("ED", "1234567.5R10")),
        _hex(_item("ED", "-1234567.5R11")),
        _hex(_item("ED", "1234567.5R12")),
        _hex(_item("ED", "1234567.5R13")),
        _hex(_item("ED", "1234567.1R14")),
        _hex(_item("ED", "1234560.1R15")),
        _hex(_item("DD", "1E369")),
        _hex(_item("DD", "1E370")),
        _hex(_item("ED", "1E97")),
        _hex(_item("ED", "1E97R9")),
        _hex(_item("ED", "15E-102")),
        _hex(_item("LD", "1.5E6200")),
        _hex(_item("DD", "1", exponent=-400)),
        _hex(_item("ED", "1234568.5")),
        _hex(_item("ED", "1234568.5R12")),
    ] == [
        "22400015",
        "22300000" "000000D0",
        "A2074000" "00000000" "00000000" "00000001",
        "A2500000",
        "22200000",
        "2654D2E8",
        "2654D2E7",
        "2654D2E8",
        "A654D2E8",
        "2654D2E8",
        "2654D2E7",
        "2654D2E8",
        "2654D2E1",
        "43FC0000" "00000001",
        "43FC0000" "00000010",
        "78000000",
        "77F3FCFF",
        "00000002",
        "78000000" "00000000" "00000000" "00000000",
        "00000000" "00000000",
        "2654D2E8",
        "2654D2E9",
    ]
    assert [
        _hex(_item("ED", value))
        for value in (
            "(INF)",
            "-(INF)",
            "(NAN)",
            "(QNAN)",
            "(SNAN)",
            "(MAX)",
            "(MIN)",
            "(DMIN)",
        )
    ] + [_hex(_item("DD", "(MAX)")), _hex(_item("LD", "(MAX)"))] == [
        "78000000",
        "F8000000",
        "7C000000",
        "7C000000",
        "7E000000",
        "77F3FCFF",
        "00600001",
        "00000001",
        "77FCFF3F" "CFF3FCFF",
        "77FFCFF3" "FCFF3FCF" "F3FCFF3F" "CFF3FCFF",
    ]


@pytest.mark.parametrize(
    ("item", "error", "message"),
    [
        (
            _item("E", "1E76"),
            DcExponentOutOfRange,
            "E'1E76' at line 7 of src/t.asm has an exponent outside -85 to +75"
            " — ASMA071E",
        ),
        (
            _item("D", "1E70", exponent=10),
            DcExponentOutOfRange,
            "D'1E70' at line 7 of src/t.asm has an exponent outside -85 to +75"
            " — ASMA071E",
        ),
        (
            _item("E", "9E75"),
            DcCharacteristicOutOfRange,
            "E'9E75' at line 7 of src/t.asm is outside the HFP range — ASMA064S",
        ),
        (
            _item("L", "-1E-79"),
            DcCharacteristicOutOfRange,
            "L'-1E-79' at line 7 of src/t.asm is outside the HFP range — ASMA064S",
        ),
        (
            _item("E", "1E-70", 2, scale=5),
            DcPrecisionLost,
            "E'1E-70' at line 7 of src/t.asm loses its fraction to its modifiers"
            " — ASMA073E",
        ),
        (
            _item("E", "1", 8, unit=LengthUnit.BIT),
            DcPrecisionLost,
            "E'1' at line 7 of src/t.asm loses its fraction to its modifiers"
            " — ASMA073E",
        ),
    ],
)
def test_hexadecimal_constants_without_extension_refuse_what_they_cannot_hold(
    item: DcItem, error: type[Exception], message: str
):
    with pytest.raises(error) as refused:
        encode_dc(item, ORIGIN)
    assert str(refused.value) == message
