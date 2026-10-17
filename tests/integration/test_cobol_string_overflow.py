"""STRING moves each sending up to its delimiter, a figurative constant being one
character and a delimiter possibly a subscripted data item; the pointer advances
by the characters that fitted, and ON / NOT ON OVERFLOW run on the outcome."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. STROVF.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 R5  PIC X(5) VALUE '*****'.",
    "01 P   PIC 99   VALUE 1.",
    "01 FL  PIC X    VALUE 'N'.",
    "01 NF  PIC X    VALUE 'N'.",
    "01 R9  PIC X(9) VALUE SPACES.",
    "01 DT  PIC X(3) VALUE 'XCD'.",
    "01 DTT REDEFINES DT.",
    "   02 DC PIC X OCCURS 3.",
    "01 I   PIC 9    VALUE 2.",
    "01 R4  PIC X(4) VALUE '....'.",
    "01 Q   PIC 99   VALUE 0.",
    "01 QF  PIC X    VALUE 'N'.",
    "PROCEDURE DIVISION.",
    "    STRING 'ABCDEF' DELIMITED BY SIZE INTO R5 WITH POINTER P",
    "        ON OVERFLOW MOVE 'Y' TO FL",
    "        NOT ON OVERFLOW MOVE 'X' TO FL",
    "    END-STRING",
    "    STRING SPACE 'X' ZERO 'Y' QUOTE 'Z' DELIMITED BY SIZE INTO R9",
    "        NOT ON OVERFLOW MOVE 'Y' TO NF",
    "    END-STRING",
    "    STRING 'ABCDEFG' DELIMITED BY DC (I) INTO R4",
    "    STRING 'Z' DELIMITED BY SIZE INTO R4 POINTER Q",
    "        ON OVERFLOW MOVE 'Y' TO QF",
    "    END-STRING",
    "    STOP RUN.",
]


@covers(CobolFeature.STRING_VERB, CobolFeature.STRING_DELIMITED_BY)
def test_string_pointer_overflow_figuratives_and_data_item_delimiter() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "STROVF"))

    assert ws[:29].decode("cp037") == (
        "ABCDE" "06" "Y" "Y" ' X0Y"Z   ' "XCD" "2" "AB.." "00" "Y"
    )
