"""Stacked WHENs -- WHEN c1 WHEN c2 <body> -- are one WHEN with one body.

The bridge used to write a WHEN per condition, each with its own copy of the body,
so every statement in it was lowered twice. Running was right either way, since
EVALUATE runs the first match only; these tests pin the single body and that
each stacked condition still selects it.
"""

from collections.abc import Sequence

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import (
    CobolStatementType,
    EvaluateStatement,
    WhenOtherStatement,
    WhenStatement,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    first_region,
    run_cobol,
)

_BY_VALUE = [
    "    EVALUATE WS-A",
    "        WHEN 1",
    "        WHEN 2",
    "            MOVE 5 TO {target}",
    "        WHEN 3 THRU 4",
    "        WHEN 7",
    "            MOVE 6 TO {target}",
    "        WHEN OTHER",
    "            MOVE 9 TO {target}",
    "    END-EVALUATE.",
]

_BY_CONDITION = [
    "    EVALUATE TRUE",
    "        WHEN WS-A = 1",
    "        WHEN WS-A = 2",
    "            MOVE 5 TO {target}",
    "        WHEN OTHER",
    "            MOVE 9 TO {target}",
    "    END-EVALUATE.",
]


def _evaluating(value: int, lines: Sequence[str], target: str) -> list[str]:
    return [
        f"    MOVE {value} TO WS-A.",
        *(line.format(target=target) for line in lines),
    ]


_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. STACKW.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "77 WS-A     PIC 9 VALUE 0.",
    "77 WS-B     PIC 9 VALUE 0.",
    "77 WS-C     PIC 9 VALUE 0.",
    "77 WS-D     PIC 9 VALUE 0.",
    "77 WS-E     PIC 9 VALUE 0.",
    "77 WS-F     PIC 9 VALUE 0.",
    "PROCEDURE DIVISION.",
    "P1.",
    *_evaluating(2, _BY_VALUE, "WS-B"),
    *_evaluating(7, _BY_VALUE, "WS-C"),
    *_evaluating(1, _BY_VALUE, "WS-D"),
    *_evaluating(5, _BY_VALUE, "WS-E"),
    *_evaluating(2, _BY_CONDITION, "WS-F"),
    "    STOP RUN.",
]


def _whens(statement: CobolStatementType) -> list[WhenStatement]:
    assert isinstance(statement, EvaluateStatement)
    assert isinstance(statement.children[-1], WhenOtherStatement)
    whens = statement.children[:-1]
    assert all(isinstance(when, WhenStatement) for when in whens)
    return [when for when in whens if isinstance(when, WhenStatement)]


@covers(CobolFeature.EVALUATE)
def test_a_stacked_when_is_one_when_with_one_body() -> None:
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    statements = make_cobol_parser().parse(source).paragraphs[0].statements
    (first, second), (true_when,) = _whens(statements[1]), _whens(statements[9])

    assert (
        (first.condition, [alt.condition for alt in first.alternatives]),
        (second.condition, second.condition_thru),
        [(alt.condition, alt.condition_thru) for alt in second.alternatives],
        (len(first.children), len(second.children)),
        len(true_when.alternatives),
        [alt.children for alt in (*first.alternatives, *second.alternatives)],
    ) == (
        ("1", ["2"]),
        ("3", "4"),
        [("7", None)],
        (1, 1),
        1,
        [[], []],
    )


@covers(CobolFeature.EVALUATE)
def test_every_stacked_condition_selects_the_shared_body() -> None:
    region = first_region(run_cobol(_PROGRAM, max_steps=20000))
    assert isinstance(region, bytearray)

    assert [decode_zoned_unsigned(region, offset, 1) for offset in range(1, 6)] == [
        5,
        6,
        5,
        9,
        5,
    ]
