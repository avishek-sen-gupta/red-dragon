"""NEXT SENTENCE goes past the period that ends its sentence, not past its END-IF.

After END-IF the same sentence can carry on, and CONTINUE would run what follows;
NEXT SENTENCE skips it. SEARCH ... WHEN ... NEXT SENTENCE does the same past
END-SEARCH.
"""

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import (
    IfStatement,
    MoveStatement,
    NextSentenceStatement,
    SearchStatement,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    first_region,
    run_cobol,
)

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. NEXTS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "77 WS-A     PIC 9 VALUE 1.",
    "77 WS-B     PIC 9 VALUE 0.",
    "77 WS-C     PIC 9 VALUE 0.",
    "77 WS-D     PIC 9 VALUE 0.",
    "77 WS-E     PIC 9 VALUE 0.",
    "01 WS-TAB   VALUE '123'.",
    "   05 WS-T  PIC 9 OCCURS 3 INDEXED BY WS-I.",
    "PROCEDURE DIVISION.",
    "P1.",
    "    MOVE '123' TO WS-TAB.",
    "    IF WS-A = 1",
    "        NEXT SENTENCE",
    "    ELSE",
    "        MOVE 8 TO WS-B",
    "    END-IF",
    "    MOVE 9 TO WS-B.",
    "    MOVE 2 TO WS-C.",
    "    SET WS-I TO 1.",
    "    SEARCH WS-T",
    "        AT END MOVE 7 TO WS-D",
    "        WHEN WS-T(WS-I) = 2 NEXT SENTENCE",
    "    END-SEARCH",
    "    MOVE 9 TO WS-D.",
    "    MOVE 5 TO WS-E.",
    "    STOP RUN.",
]


@covers(CobolFeature.NEXT_SENTENCE)
def test_the_bridge_keeps_next_sentence_and_where_each_sentence_ends() -> None:
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    (p1,) = make_cobol_parser().parse(source).paragraphs
    branch, search = p1.statements[1], p1.statements[5]
    assert isinstance(branch, IfStatement)
    assert isinstance(search, SearchStatement)

    assert (
        [type(s) for s in branch.children],
        [type(s) for s in branch.else_children],
        [type(s) for s in search.whens[0].children],
        p1.sentence_ends,
    ) == (
        [NextSentenceStatement],
        [MoveStatement],
        [NextSentenceStatement],
        [0, 2, 3, 4, 6, 7, 8],
    )


@covers(CobolFeature.NEXT_SENTENCE, CobolFeature.IF_ELSE, CobolFeature.SEARCH_LINEAR)
def test_next_sentence_skips_the_rest_of_its_sentence() -> None:
    region = first_region(run_cobol(_PROGRAM, max_steps=20000))
    assert isinstance(region, bytearray)

    assert [decode_zoned_unsigned(region, offset, 1) for offset in range(5)] == [
        1,
        0,
        2,
        0,
        5,
    ]
