"""Tests for UNSTRING's examination of the source into receiver pieces, as IR."""

from collections.abc import Sequence

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.unstring_ir import emit_unstring
from interpreter.register import Register
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted_values

_ZERO = ("0", False)
_ALL_ZERO = ("0", True)
_COMMA = (",", False)
_COMMA_SPACE = (", ", False)

type _Piece = tuple[ParamValue, ParamValue, ParamValue]


def _piece(text: str, delimiter: str = "") -> _Piece:
    return text, delimiter, len(text)


def _unstring(
    source: ParamValue,
    pointer: int,
    delimiters: Sequence[tuple[str, bool]],
    sizes: Sequence[int],
) -> tuple[tuple[_Piece, ...], ParamValue, ParamValue]:
    """(pieces of the receivers acted on, pointer, overflow)."""

    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> tuple[Register, ...]:
        outcome = emit_unstring(
            e,
            registers[0],
            registers[1],
            (
                [
                    (register, all_flag)
                    for register, (_, all_flag) in zip(
                        registers[2:], delimiters, strict=True
                    )
                ],
                sizes,
            ),
        )
        return (
            outcome.acted,
            outcome.pointer,
            outcome.overflow,
            *(
                register
                for piece in outcome.pieces
                for register in (piece.text, piece.delimiter, piece.count)
            ),
        )

    acted, moved_to, overflow, *flat = run_emitted_values(
        emit, (source, pointer, *(text for text, _ in delimiters))
    )
    assert isinstance(acted, int)
    pieces = tuple(
        (flat[index], flat[index + 1], flat[index + 2])
        for index in range(0, 3 * acted, 3)
    )
    return pieces, moved_to, overflow


@covers(CobolFeature.UNSTRING_VERB, CobolFeature.UNSTRING_DELIMITED_BY)
def test_each_receiver_takes_the_characters_before_the_nearest_delimiter():
    cases = [
        ("1200300", 1, (_ZERO,), (3, 3, 3)),
        ("1200300", 1, (_ALL_ZERO,), (3, 3, 3)),
        ("000", 1, (_ALL_ZERO,), (2, 2)),
        ("A,B, C", 1, (_COMMA, _COMMA_SPACE), (2, 2, 2)),
        ("A,B, C", 1, (_COMMA_SPACE, _COMMA), (2, 2, 2)),
        ("A,B,C,D", 3, (_COMMA,), (2, 2)),
        ("ABCDEF", 1, (), (2, 3)),
        ("ABCDEF", 2, (), (3, 2)),
        ("ABC", 0, (_COMMA,), (2,)),
        ("ABC", 4, (_COMMA,), (2,)),
    ]
    assert [_unstring(*case) for case in cases] == [
        ((_piece("12", "0"), _piece("", "0"), _piece("3", "0")), 7, True),
        ((_piece("12", "0"), _piece("3", "0")), 8, False),
        ((_piece("", "0"),), 4, False),
        ((_piece("A", ","), _piece("B", ","), _piece(" C")), 7, False),
        ((_piece("A", ","), _piece("B", ", "), _piece("C")), 7, False),
        ((_piece("B", ","), _piece("C", ",")), 7, True),
        ((_piece("AB"), _piece("CDE")), 6, True),
        ((_piece("BCD"), _piece("EF")), 7, False),
        ((), 0, True),
        ((), 4, True),
    ]
