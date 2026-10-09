"""STRING INTO a subscripted table element writes to the SUBSCRIPTED element,
not the table's base address -- a sending operand's subscript is honoured
(``_write_ref_mod_target``, used for ref-modified targets), but the INTO
target's plain (non-ref-mod) resolution dropped ``stmt.into.subscripts``
entirely, so every ``STRING ... INTO TAB-FLD(idx)`` wrote to element 1
regardless of ``idx``, repeatedly overwriting it with each loop iteration's
value and leaving every other element untouched (red-dragon, found serving
a real multi-row occupant screen over TN3270: three distinct STRING INTO
calls with idx=1,2,3 left elements 2 and 3 at their initial value and
element 1 holding the LAST iteration's data instead of the first's).

Each element's "before" content is set via an explicit subscripted MOVE
(already correctly subscripted, unaffected by this bug) rather than an
OCCURS item's own VALUE clause, which only initializes the first occurrence
in this interpreter -- a separate, pre-existing question this test does not
depend on either way."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. STRSUB.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-TAB.",
    "   05 WS-ROW OCCURS 3 TIMES.",
    "      10 WS-ROW-FLD PIC X(8).",
    "PROCEDURE DIVISION.",
    "    MOVE 'ZZZZZZZZ' TO WS-ROW-FLD(1).",
    "    MOVE 'ZZZZZZZZ' TO WS-ROW-FLD(2).",
    "    MOVE 'ZZZZZZZZ' TO WS-ROW-FLD(3).",
    "    STRING 'AAAA' DELIMITED BY SIZE INTO WS-ROW-FLD(1).",
    "    STRING 'BBBB' DELIMITED BY SIZE INTO WS-ROW-FLD(2).",
    "    STRING 'CCCC' DELIMITED BY SIZE INTO WS-ROW-FLD(3).",
    "    STOP RUN.",
]


@covers(CobolFeature.STRING_VERB)
def test_string_into_subscripted_table_element_writes_that_element() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "STRSUB"))

    assert ws[0:8].decode("cp037") == "AAAAZZZZ"
    assert ws[8:16].decode("cp037") == "BBBBZZZZ"
    assert ws[16:24].decode("cp037") == "CCCCZZZZ"
