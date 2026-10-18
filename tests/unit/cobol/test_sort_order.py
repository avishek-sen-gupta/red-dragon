"""Sort work-file ordering: keys major to minor, equal keys in release order."""

from __future__ import annotations

from cobol_asg.alphabet import Alphabet
from cobol_asg.cobol_statements import (
    MergeStatement,
    ProcedureRange,
    ProcedureRef,
    SortStatement,
    parse_statement,
)
from cobol_asg.program_collation import PROGRAM_COLLATION
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.sort_files import SortFiles
from cobol_asg.sort_key import SortKey
from cobol_asg.sort_key_direction import SortKeyDirection
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.sort_field import SortField
from interpreter.cobol.sort_key_encoding import SortKeyEncoding
from interpreter.cobol.sort_order import ordered
from interpreter.cobol.sort_ordering import SortOrdering, ordering_of
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
    assert ordering_of(SortOrdering((key, key), swapped).data()) == SortOrdering(
        (key, key), swapped
    )


@covers(CobolFeature.SORT)
def test_sort_and_merge_statements_read_and_write_their_bridge_form() -> None:
    data = {
        "type": "SORT",
        "file_name": "SRT",
        "keys": [
            {"direction": "DESCENDING", "key": {"name": "K", "qualifiers": ["G"]}}
        ],
        "collating_sequence": {
            "name": "REV",
            "kind": "LITERALS",
            "items": [{"link": "NONE", "kind": "NONNUMERIC", "value": "B"}],
        },
        "using": ["IN-F"],
        "giving": [],
        "output_procedure": {"target": "P1", "thru": "P2", "thru_section": "S"},
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
        collating_sequence=Alphabet.from_parts(
            "REV", "LITERALS", [{"kind": "NONNUMERIC", "value": "B", "link": "NONE"}]
        ),
        source=SortFiles(("IN-F",)),
        sink=ProcedureRange(target=ProcedureRef("P1"), thru=ProcedureRef("P2", "S")),
        span=None,
    )
    assert stmt.to_dict() == data
    merge = {
        "type": "MERGE",
        "file_name": "SRT",
        "keys": [],
        "using": ["A", "B"],
        "giving": ["C"],
    }
    assert parse_statement(merge) == MergeStatement(
        file_name="SRT",
        keys=(),
        collating_sequence=PROGRAM_COLLATION,
        using=SortFiles(("A", "B")),
        sink=SortFiles(("C",)),
        span=None,
    )
    assert parse_statement(merge).to_dict() == merge
