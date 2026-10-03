"""A name declared in two groups, used with OF, resolves to the group it names.

COBOL requires the qualifier exactly when a name is declared more than once, so
every statement kind has to carry it from the reference to the field it lowers.
"""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import first_region, run_cobol

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. QUALS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 G1.",
    "   05 F-NUM  PIC 9(3) VALUE 5.",
    "   05 F-TXT  PIC X(4) VALUE 'ABCD'.",
    "01 G2.",
    "   05 F-NUM  PIC 9(3) VALUE 7.",
    "   05 F-TXT  PIC X(4) VALUE 'WXYZ'.",
    "01 WS-R      PIC 9 VALUE 0.",
    "PROCEDURE DIVISION.",
    "    ADD 1 TO F-NUM OF G1.",
    "    COMPUTE F-NUM OF G2 = F-NUM OF G1 + F-NUM OF G2.",
    "    IF F-TXT OF G2 = 'WXYZ'",
    "        MOVE 1 TO WS-R",
    "    END-IF.",
    "    STOP RUN.",
]


@covers(CobolFeature.QUALIFIED_NAMES)
def test_qualified_operands_resolve_in_arithmetic_and_conditions() -> None:
    region = first_region(run_cobol(_PROGRAM, max_steps=20000))
    assert isinstance(region, bytearray)

    assert bytes(region[:15]).decode("cp037") == "006ABCD013WXYZ1"
