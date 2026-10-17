"""UNSTRING examines the source from the pointer: each receiver takes the
characters up to the nearest delimiter (ALL folding a run into one), its
DELIMITER IN and COUNT IN receive the delimiter and the count, TALLYING counts
the receivers acted on, and ON / NOT ON OVERFLOW run on whether characters
remain. Without DELIMITED BY each receiver takes its size."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. USTPHR.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 SRC PIC X(7) VALUE '1200300'.",
    "01 R1  PIC X(3) VALUE '***'.",
    "01 R2  PIC X(3) VALUE '***'.",
    "01 R3  PIC X(3) VALUE '***'.",
    "01 D1  PIC X(2) VALUE '**'.",
    "01 D2  PIC X(2) VALUE '**'.",
    "01 C1  PIC 99   VALUE 0.",
    "01 C2  PIC 99   VALUE 0.",
    "01 P   PIC 99   VALUE 1.",
    "01 T   PIC 99   VALUE 5.",
    "01 FL  PIC X    VALUE 'N'.",
    "01 G.",
    "   02 E PIC X(3) OCCURS 2.",
    "01 K   PIC 9    VALUE 2.",
    "01 DT  PIC X(2) VALUE ',E'.",
    "01 DTT REDEFINES DT.",
    "   02 DC PIC X OCCURS 2.",
    "01 S1  PIC X(2) VALUE '..'.",
    "01 S2  PIC X(2) VALUE '..'.",
    "01 S3  PIC X(2) VALUE '..'.",
    "01 S4  PIC X(2) VALUE '..'.",
    "01 Q   PIC 99   VALUE 3.",
    "01 QF  PIC X    VALUE 'N'.",
    "PROCEDURE DIVISION.",
    "    UNSTRING SRC DELIMITED BY ALL '0'",
    "        INTO R1 DELIMITER IN D1 COUNT IN C1",
    "             R2 DELIMITER IN D2 COUNT IN C2",
    "             R3",
    "        WITH POINTER P TALLYING IN T",
    "        ON OVERFLOW MOVE 'Y' TO FL",
    "        NOT ON OVERFLOW MOVE 'X' TO FL",
    "    END-UNSTRING",
    "    MOVE 'ABCDEF' TO G",
    "    UNSTRING E OF G (K) DELIMITED BY DC (K) OR 'Z' INTO S1 S2",
    "    UNSTRING SRC INTO S3 S4 WITH POINTER Q",
    "        ON OVERFLOW MOVE 'Y' TO QF",
    "    END-UNSTRING",
    "    STOP RUN.",
]


@covers(CobolFeature.UNSTRING_VERB, CobolFeature.UNSTRING_DELIMITED_BY)
def test_unstring_delimiter_count_pointer_tallying_and_overflow() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "USTPHR"))

    assert ws[:54].decode("cp037") == (
        "1200300"
        "12 "
        "3  "
        "***"
        "0 "
        "0 "
        "02"
        "01"
        "08"
        "07"
        "X"
        "ABCDEF"
        "2"
        ",E"
        "D "
        "F "
        "00"
        "30"
        "07"
        "Y"
    )
