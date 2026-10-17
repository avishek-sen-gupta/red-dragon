"""A group's USAGE applies to every elementary item in it, and a USAGE INDEX item has storage of its own."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. GRPUSAGE.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 U5 USAGE COMP.",
    "   02 U6 PIC 9 VALUE 5.",
    "   02 U7 PIC 9 VALUE 6.",
    "01 U9 USAGE COMP.",
    "   02 U10 PIC 9.",
    "   02 U11 PIC 9 COMP.",
    "01 TBL VALUE SPACES.",
    "   02 EL PIC X OCCURS 5 INDEXED BY I1 I2.",
    "77 USE-IDX USAGE INDEX.",
    "77 AFTER-IDX PIC X(3) VALUE 'END'.",
    "01 DATA-NAMES USAGE INDEX.",
    "   02 KEY-1.",
    "   02 KEY-2.",
    "77 N PIC 9.",
    "77 M PIC 9.",
    "77 FLAG PIC X VALUE 'N'.",
    "PROCEDURE DIVISION.",
    "    MOVE U5 TO U9.",
    "    SET I1 TO 3.",
    "    SET USE-IDX TO I1.",
    "    SET I2 TO USE-IDX.",
    "    SET N TO I2.",
    "    SET I1 TO 4.",
    "    SET KEY-2 TO I1.",
    "    SET KEY-1 TO I2.",
    "    SET I2 TO KEY-2.",
    "    SET M TO I2.",
    "    IF USE-IDX = KEY-1 MOVE 'Y' TO FLAG.",
    "    STOP RUN.",
]


@covers(CobolFeature.USAGE_COMP, CobolFeature.USAGE_INDEX, CobolFeature.GROUP_ITEM)
def test_group_usage_is_inherited_and_index_items_have_storage() -> None:
    """ANSI X3.23-1985 / ISO 1989 USAGE clause: USAGE written at group level
    applies to each elementary item in the group. A USAGE INDEX data item
    occupies a fullword (IBM Enterprise COBOL LR, USAGE INDEX), and SET moves
    an occurrence number into and out of it."""
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "GRPUSAGE"))

    assert ws.hex() == (
        "00050006"
        "00050006"
        "4040404040"
        "00000003"
        "c5d5c4"
        "0000000300000004"
        "f3"
        "f4"
        "e8"
    )
