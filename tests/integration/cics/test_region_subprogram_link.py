"""Integration (JAR-gated): a CICS region program links the subprograms it CALLs.

This is the fitness function for red-dragon-1bp2. Before the fix,
``compile_cics_program`` compiled a single COBOL source standalone, so a
``CALL 'X'`` to a sibling program had no linked callee IR — ``CallWithMemory``
left the result symbolic and wrote nothing back through the USING params.

Here a tiny main program CALLs a tiny callee BY REFERENCE; the callee writes a
known value into the LINKAGE field. We compile the main with
``program_source_dir`` pointing at a dir that also holds the callee source, then
drive it through a real CICS region and assert the value the callee wrote
surfaces on the screen — proving the callee actually executed (region linking).
"""

from __future__ import annotations

import queue
from pathlib import Path

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from interpreter.cics.bootstrap import run_carddemo_region
from interpreter.cics.dispatcher import InputEvent
from interpreter.cics.preprocessor import apply_cics_prepass
from interpreter.cics.types import DispatchKind
from tests.integration.cics.channel_drain import drain
from tests.covers import covers
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH, bridge_jar_env

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)

_CICS_COPYBOOKS = Path(__file__).parents[3] / "interpreter" / "cics" / "copybooks"


@pytest.fixture(autouse=True)
def _bridge_jar_env(bridge_jar_env):
    yield


# Main: CALL 'SETVAL' USING BY REFERENCE WS-OUT (initially spaces); then SEND
# MAP with the (now callee-written) value, RETURN to terminate.
MAINLNK_SRC = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINLNK.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 LNKMAP.
          05 RESULTO PIC X(8).
       01 WS-OUT PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
           CALL 'SETVAL' USING BY REFERENCE WS-OUT.
           MOVE WS-OUT TO RESULTO.
           EXEC CICS SEND MAP('LNKMAP') FROM(LNKMAP) END-EXEC.
           EXEC CICS RETURN END-EXEC.
           STOP RUN.
"""

# Callee: write 'LINKEDOK' into the BY REFERENCE linkage field, return to caller.
SETVAL_SRC = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SETVAL.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-OUT PIC X(8).
       PROCEDURE DIVISION USING LS-OUT.
           MOVE 'LINKEDOK' TO LS-OUT.
           EXIT PROGRAM.
"""


@covers(CobolFeature.CALL, CobolFeature.CALL_USING)
def test_region_program_links_called_subprogram(tmp_path):
    """A CICS-compiled main that CALLs a sibling actually invokes it (region link).

    RED before red-dragon-1bp2: SETVAL is not linked, the CALL goes symbolic, and
    WS-OUT stays SPACES (screen shows blanks). GREEN after: the callee runs and
    'LINKEDOK' surfaces on the screen.
    """
    # Place the callee on disk so the COBOL resolver finds CALL 'SETVAL'.
    cbl_dir = tmp_path / "cbl"
    cbl_dir.mkdir()
    (cbl_dir / "SETVAL.cbl").write_text(SETVAL_SRC)

    parser = ProLeapCobolParser(
        RealSubprocessRunner(), JAR_PATH, copybook_dirs=[_CICS_COPYBOOKS]
    )

    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()

    result = run_carddemo_region(
        transid_to_program={"CC00": "MAINLNK"},
        program_sources={"MAINLNK": apply_cics_prepass(MAINLNK_SRC).encode()},
        parser=parser,
        entry_transid="CC00",
        screen_queue=screen_q,
        input_queue=input_q,
        program_source_dir=cbl_dir,
    )

    assert result.kind == DispatchKind.RETURN

    screens = drain(screen_q)
    assert [s["map"] for s in screens] == ["LNKMAP"]
    # The value the callee wrote through BY REFERENCE surfaces — proves it ran.
    assert (
        screens[0]["fields"].get("RESULT") == "LINKEDOK"
    ), f"callee result not linked back; field={screens[0]['fields'].get('RESULT')!r}"
