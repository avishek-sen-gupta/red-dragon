"""Sort work-file ordering: keys major to minor, equal keys in release order."""

from __future__ import annotations

from cobol_asg.cobol_statements import SortStatement, parse_statement
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.sort_key import SortKey
from cobol_asg.sort_key_direction import SortKeyDirection
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.sort_field import SortField, sort_field_arguments, sort_fields
from interpreter.cobol.sort_key_encoding import SortKeyEncoding
from interpreter.cobol.sort_order import ordered
from tests.covers import covers

_NATIVE = tuple(range(256))


@covers(CobolFeature.SORT)
def test_alphanumeric_key_orders_by_collating_weight_and_keeps_ties_in_order() -> None:
    key = SortField(
        offset=1,
        length=2,
        encoding=SortKeyEncoding.ALPHANUMERIC,
        direction=SortKeyDirection.ASCENDING,
    )
    records = [b"1ZZ", b"2AB", b"3AA", b"4AB", b"5aa"]
    swapped = tuple(
        {ord("A"): ord("b"), ord("b"): ord("A")}.get(b, b) for b in range(256)
    )
    assert ordered(records, [key], _NATIVE) == [b"3AA", b"2AB", b"4AB", b"1ZZ", b"5aa"]
    assert ordered([b"1Ab", b"2bA"], [key], swapped) == [b"2bA", b"1Ab"]
    assert sort_fields((*sort_field_arguments(key), *sort_field_arguments(key))) == (
        key,
        key,
    )


@covers(CobolFeature.SORT)
def test_sort_statement_reads_and_writes_its_bridge_form() -> None:
    data = {
        "type": "SORT",
        "file_name": "SRT",
        "keys": [
            {"direction": "DESCENDING", "key": {"name": "K", "qualifiers": ["G"]}}
        ],
        "using": ["IN-F"],
        "giving": ["OUT-F", "OUT-G"],
    }
    stmt = parse_statement(data)
    assert stmt == SortStatement(
        file_name="SRT",
        keys=(
            SortKey(
                direction=SortKeyDirection.DESCENDING,
                key=RefModOperand(name="K", qualifiers=("G",)),
            ),
        ),
        using=("IN-F",),
        giving=("OUT-F", "OUT-G"),
        span=None,
    )
    assert stmt.to_dict() == data
