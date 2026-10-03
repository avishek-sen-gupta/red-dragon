"""STRING changes only the characters it transfers: the rest of the receiving
field keeps its value, with or without WITH POINTER, and nothing past the
receiver is touched."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. STRRCV.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-F    PIC X(8) VALUE 'FFFFFFFF'.",
    "01 WS-G    PIC X(8) VALUE 'GGGGGGGG'.",
    "01 WS-NEXT PIC X(2) VALUE 'NN'.",
    "01 WS-P    PIC 99   VALUE 3.",
    "PROCEDURE DIVISION.",
    "    STRING 'AB' DELIMITED BY SIZE INTO WS-F.",
    "    STRING 'CD' DELIMITED BY SIZE INTO WS-G WITH POINTER WS-P.",
    "    STOP RUN.",
]


@covers(CobolFeature.STRING_VERB)
def test_string_leaves_untransferred_receiver_bytes_unchanged() -> None:
    ws = bytes(ws_region(run_cobol_programs(_PROGRAM, {}), "STRRCV"))

    assert ws[:20].decode("cp037") == "ABFFFFFFGGCDGGGGNN05"
