"""Tests for STRING's transfer of the delimited sendings into the receiver, as IR."""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.string_ir import emit_string
from interpreter.register import Register
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted_values


def _emit(e: IrEmitter, registers: tuple[Register, ...]) -> tuple[Register, ...]:
    receiver, pointer, *parts = registers
    outcome = emit_string(e, receiver, pointer, parts)
    return outcome.image, outcome.pointer, outcome.overflow


def _string_into(
    receiver: str, pointer: int, parts: tuple[ParamValue, ...]
) -> tuple[ParamValue, ...]:
    return run_emitted_values(_emit, (receiver, pointer, *parts))


@covers(CobolFeature.STRING_VERB)
def test_transfer_stops_at_the_receiver_end_and_moves_the_pointer_by_what_fitted():
    cases = [
        ("*****", 1, ("ABCDEF",)),
        ("*****", 1, ("AB", "CDE")),
        ("*****", 2, ("AB",)),
        ("*****", 3, ("ABCD", "EFGH", "IJKL")),
        ("*****", 0, ("A",)),
        ("*****", 6, ("A",)),
        ("*****", 6, ()),
        ("*****", 1, ("", "")),
    ]
    assert [_string_into(*case) for case in cases] == [
        ("ABCDE", 6, True),
        ("ABCDE", 6, False),
        ("*AB**", 4, False),
        ("**ABC", 6, True),
        ("*****", 0, True),
        ("*****", 6, True),
        ("*****", 6, True),
        ("*****", 1, False),
    ]


@covers(CobolFeature.STRING_VERB)
def test_a_symbolic_sending_keeps_the_sendings_before_it_concrete():
    image, pointer, overflow = _string_into("*****", 1, ("AB", SymbolicValue("s")))
    assert isinstance(image, SymbolicValue)
    assert image.constraints == [
        "__string_splice('AB***', 2, __length(__string_slice(s, 0, 3)),"
        " __string_slice(s, 0, 3))"
    ]
    assert isinstance(pointer, SymbolicValue)
    assert pointer.constraints == ["3 BinopKind.ADD __length(__string_slice(s, 0, 3))"]
    assert overflow is False
