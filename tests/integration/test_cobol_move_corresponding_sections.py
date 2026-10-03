"""MOVE CORRESPONDING finds its groups in every section: LINKAGE, LOCAL-STORAGE
and WORKING-STORAGE alike, and a write to a LINKAGE group lands in the caller."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. MCMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 IN-REC.",
    "   05 AA PIC X(2) VALUE 'AB'.",
    "   05 BB PIC X(2) VALUE 'CD'.",
    "   05 CC PIC X(2) VALUE 'EF'.",
    "01 OUT-REC.",
    "   05 AA PIC X(2) VALUE '..'.",
    "   05 BB PIC X(2) VALUE '..'.",
    "   05 DD PIC X(2) VALUE '..'.",
    "PROCEDURE DIVISION.",
    "    CALL 'MCSUB' USING IN-REC OUT-REC.",
    "    STOP RUN.",
]

_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. MCSUB.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-REC.",
    "   05 AA PIC X(2) VALUE '__'.",
    "   05 BB PIC X(2) VALUE '__'.",
    "LOCAL-STORAGE SECTION.",
    "01 LS-REC.",
    "   05 BB PIC X(2) VALUE '--'.",
    "   05 AA PIC X(2) VALUE '--'.",
    "LINKAGE SECTION.",
    "01 LK-IN.",
    "   05 AA PIC X(2).",
    "   05 BB PIC X(2).",
    "   05 CC PIC X(2).",
    "01 LK-OUT.",
    "   05 AA PIC X(2).",
    "   05 BB PIC X(2).",
    "   05 DD PIC X(2).",
    "PROCEDURE DIVISION USING LK-IN LK-OUT.",
    "    MOVE CORRESPONDING LK-IN TO LS-REC.",
    "    MOVE CORRESPONDING LS-REC TO WS-REC.",
    "    MOVE CORRESPONDING WS-REC TO LK-OUT.",
    "    GOBACK.",
]


@covers(CobolFeature.MOVE_CORRESPONDING)
def test_move_corresponding_reads_and_writes_groups_in_any_section() -> None:
    vm = run_cobol_programs(_MAIN, {"MCSUB": _SUB})

    assert (
        bytes(ws_region(vm, "MCMAIN"))[6:12].decode("cp037"),
        bytes(ws_region(vm, "MCSUB"))[:4].decode("cp037"),
    ) == ("ABCD..", "ABCD")
