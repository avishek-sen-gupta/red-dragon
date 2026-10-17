"""Tests for the size error test as IR: the result's magnitude against the receiver's capacity."""

from cobol_numeric.number import CobolNumber, from_literal
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.size_error_ir import emit_size_error
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _size_error(value: ParamValue, capacity: CobolNumber) -> ParamValue:
    return run_emitted(
        lambda e, registers: emit_size_error(e, registers[0], capacity), (value,)
    )


@covers(CobolFeature.ON_SIZE_ERROR)
def test_size_error_compares_the_magnitude_with_the_capacity():
    assert _size_error(from_literal("-4.57"), from_literal("1")) is True
    assert _size_error(from_literal(".218"), from_literal("1")) is False
    assert _size_error(-10, from_literal("10")) is True


@covers(CobolFeature.ON_SIZE_ERROR)
def test_reaching_the_magnitude_ignores_the_sign():
    cases = [
        ("99.9", "100", False),
        ("100", "100", True),
        ("-99.9", "100", False),
        ("-100", "100", True),
        ("-4.57", "1", True),
        ("-0.99", "1", False),
        ("-4486.72", "10", True),
    ]
    assert [
        _size_error(from_literal(value), from_literal(capacity))
        for value, capacity, _ in cases
    ] == [expected for _, _, expected in cases]


@covers(CobolFeature.ON_SIZE_ERROR)
def test_a_symbolic_result_flows_through_the_magnitude_comparison():
    flag = _size_error(SymbolicValue("result"), from_literal("100"))
    assert isinstance(flag, SymbolicValue)
    assert flag.constraints == [
        "__cobol_parse_number(result) BinopKind.GE Decimal('100') BinopKind.OR"
        " __cobol_parse_number(result) BinopKind.LE Decimal('-100')"
    ]
