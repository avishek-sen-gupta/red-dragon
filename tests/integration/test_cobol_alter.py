"""ALTER changes where a paragraph's lone GO TO transfers control, until it is altered again or the program is cancelled."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_REDIRECTING = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. ALTERS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 C-COUNT PIC 9 VALUE 0.",
    "01 D-COUNT PIC 9 VALUE 0.",
    "01 L-COUNT PIC 9 VALUE 0.",
    "01 U-COUNT PIC 99 VALUE 0.",
    "PROCEDURE DIVISION.",
    "MAIN SECTION.",
    "M-1.",
    "    PERFORM T-SEC.",
    "    ALTER T-A TO PROCEED TO T-C.",
    "    PERFORM T-SEC.",
    "    ALTER T-A TO PROCEED TO T-D.",
    "    PERFORM T-SEC.",
    "    PERFORM L-SEC.",
    "    ALTER U-A TO PROCEED TO U-C.",
    "    PERFORM U-SEC.",
    "    STOP RUN.",
    "T-SEC SECTION.",
    "T-A.",
    "    GO TO T-D.",
    "T-C.",
    "    ADD 1 TO C-COUNT.",
    "T-D.",
    "    ADD 1 TO D-COUNT.",
    "L-SEC SECTION.",
    "L-0.",
    "    GO TO L-A.",
    "L-A.",
    "    ADD 1 TO L-COUNT.",
    "    ALTER L-0 TO PROCEED TO L-B.",
    "    GO TO L-0.",
    "L-B.",
    "    EXIT.",
    "U-SEC SECTION.",
    "U-A.",
    "    GO TO.",
    "U-B.",
    "    MOVE 9 TO U-COUNT.",
    "U-C.",
    "    ADD 1 TO U-COUNT.",
]

_SWITCHING = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SWITCH.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 TAKEN PIC X.",
    "PROCEDURE DIVISION USING TAKEN.",
    "S-0.",
    "    GO TO S-SW.",
    "S-SW.",
    "    GO TO S-A.",
    "S-A.",
    "    MOVE 'A' TO TAKEN.",
    "    ALTER S-SW TO PROCEED TO S-B.",
    "    GOBACK.",
    "S-B.",
    "    MOVE 'B' TO TAKEN.",
    "    GOBACK.",
]

_CALLING = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CALLER.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 TAKEN-1 PIC X VALUE SPACE.",
    "01 TAKEN-2 PIC X VALUE SPACE.",
    "01 TAKEN-3 PIC X VALUE SPACE.",
    "PROCEDURE DIVISION.",
    "    CALL 'SWITCH' USING TAKEN-1.",
    "    CALL 'SWITCH' USING TAKEN-2.",
    "    CANCEL 'SWITCH'.",
    "    CALL 'SWITCH' USING TAKEN-3.",
    "    STOP RUN.",
]


@covers(CobolFeature.ALTER, CobolFeature.GO_TO)
def test_alter_redirects_the_go_to_of_the_paragraph_it_names() -> None:
    """IBM Enterprise COBOL LR, ALTER: "the next time control reaches the
    paragraph specified in procedure-name-1, the GO TO statement transfers
    control to the paragraph specified in procedure-name-2". T-A's GO TO goes
    to T-D, then to T-C once altered, then to T-D again once altered back; L-0
    is altered by a statement that follows it, and its loop ends through the
    ALTER (NIST-85 SG203A PARA-54); U-A's GO TO has no operand and goes where
    the ALTER sends it (NIST-85 OBNC1M GO--TEST-1)."""
    ws = bytes(ws_region(run_cobol_programs(_REDIRECTING, {}), "ALTERS"))

    assert ws.decode("cp037") == "13101"


@covers(CobolFeature.ALTER, CobolFeature.CANCEL)
def test_an_altered_go_to_keeps_its_target_across_calls_until_cancel() -> None:
    """A called program is left in its last-used state, so the second CALL
    finds S-SW altered; CANCEL puts the program back in its initial state, so
    the third CALL finds S-SW going to S-A again (IBM Enterprise COBOL LR,
    CANCEL)."""
    vm = run_cobol_programs(_CALLING, {"SWITCH": _SWITCHING})

    assert bytes(ws_region(vm, "CALLER")).decode("cp037") == "ABA"
