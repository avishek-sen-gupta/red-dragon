"""Integration (JAR-gated): a REAL two-turn CICS region run.

This is the CICS epic's fitness function. It drives a real pseudo-conversational
sign-on -> menu flow through COMPILED-AND-EXECUTED COBOL (no stubbed run_fn):

  pre-pass -> ProLeap -> CICS lowering -> VM -> builtins -> screen / COMMAREA.

  Turn 1: CC00 / SGNPGM  -- MOVE a value into a symbolic output field, SEND MAP
          SGNMAP, RETURN TRANSID('CM00') COMMAREA(WS-CA).
  Turn 2: CM00 / MENUPGM -- read DFHCOMMAREA into a symbolic output field,
          SEND MAP MENMAP, RETURN (terminate).

The dispatcher carries the COMMAREA from SGNPGM into MENUPGM; the second screen
reflects bytes that originated in the first program's COMMAREA, proving the whole
stack works end to end.
"""

from __future__ import annotations

import queue
from pathlib import Path

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from interpreter.cics.bootstrap import run_carddemo_region
from interpreter.cics.bms.loader import BmsLoader, BmsMap, BmsField
from interpreter.cics.dispatcher import InputEvent
from interpreter.cics.preprocessor import apply_cics_prepass
from interpreter.cics.types import DispatchKind
from tests.covers import covers
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH, bridge_jar_env

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)

_CICS_COPYBOOKS = Path(__file__).parents[3] / "interpreter" / "cics" / "copybooks"


@pytest.fixture(autouse=True)
def _bridge_jar_env(bridge_jar_env):
    yield


@pytest.fixture
def cobol_parser():
    runner = RealSubprocessRunner()
    return ProLeapCobolParser(runner, JAR_PATH, copybook_dirs=[_CICS_COPYBOOKS])


# Sign-on program: MOVE 'WELCOME!' into the SGNMAP symbolic output field MSGO,
# carry the same value in the COMMAREA, then RETURN TRANSID('CM00').
SGNPGM_SRC = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SGNPGM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 SGNMAP.
          05 MSGO PIC X(8).
       01 WS-CA.
          05 WS-CA-MSG PIC X(8).
       PROCEDURE DIVISION.
           MOVE 'WELCOME!' TO MSGO.
           MOVE 'WELCOME!' TO WS-CA-MSG.
           EXEC CICS SEND MAP('SGNMAP') END-EXEC.
           EXEC CICS RETURN TRANSID('CM00') COMMAREA(WS-CA) END-EXEC.
           STOP RUN.
"""

# Menu program: read DFHCOMMAREA into the MENMAP symbolic output field MENMSGO,
# SEND MAP, RETURN (terminate). The carried COMMAREA value becomes visible on
# the menu screen.
MENUPGM_SRC = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MENUPGM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 MENMAP.
          05 MENMSGO PIC X(8).
       LINKAGE SECTION.
       01 DFHCOMMAREA.
          05 DFH-CA-MSG PIC X(8).
       PROCEDURE DIVISION.
           MOVE DFH-CA-MSG TO MENMSGO.
           EXEC CICS SEND MAP('MENMAP') END-EXEC.
           EXEC CICS RETURN END-EXEC.
           STOP RUN.
"""


def _make_loader() -> BmsLoader:
    loader = BmsLoader(maps_dir=None)
    # field bases MSG / MENMSG -> symbolic output subfields MSGO / MENMSGO.
    loader.register_stub(
        "SGNMAP", BmsMap(name="SGNMAP", fields={"MSG": BmsField(offset=0, length=8)})
    )
    loader.register_stub(
        "MENMAP",
        BmsMap(name="MENMAP", fields={"MENMSG": BmsField(offset=0, length=8)}),
    )
    return loader


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
@covers(CobolFeature.EXEC_CICS)
def test_two_turn_region_real_execution(cobol_parser):
    """Real compiled sign-on -> menu flow: two screens + COMMAREA carry-through."""
    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()
    # Unblocks the RETURN TRANSID turn transition (CC00 -> CM00).
    input_q.put(InputEvent(eibaid="\x7d", fields={}))

    program_sources = {
        "SGNPGM": apply_cics_prepass(SGNPGM_SRC).encode(),
        "MENUPGM": apply_cics_prepass(MENUPGM_SRC).encode(),
    }

    result = run_carddemo_region(
        transid_to_program={"CC00": "SGNPGM", "CM00": "MENUPGM"},
        program_sources=program_sources,
        parser=cobol_parser,
        entry_transid="CC00",
        screen_queue=screen_q,
        input_queue=input_q,
        bms_loader=_make_loader(),
    )

    # Loop terminated on MENUPGM's RETURN.
    assert result.kind == DispatchKind.RETURN

    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())

    # Two screens, in order: sign-on then menu.
    assert [s["map"] for s in screens] == ["SGNMAP", "MENMAP"]

    # Screen 1 reflects the value SGNPGM MOVEd into the symbolic output field.
    assert screens[0]["fields"].get("MSG") == "WELCOME!"

    # Screen 2 reflects the COMMAREA value carried from SGNPGM into MENUPGM.
    assert screens[1]["fields"].get("MENMSG") == "WELCOME!"


# Data-name map program (the standard CardDemo idiom, e.g. MAP(CCARD-NEXT-MAP)):
# the map NAME is held in a WS field, set at runtime, then SEND MAP(WS-MAPNM).
# Before the structural fix this rendered nothing because WS-MAPNM (the field
# NAME) was passed to the loader instead of its runtime VALUE 'MYMAP'.
DATANAME_PGM_SRC = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DNPGM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-MAPNM PIC X(7).
       01 MYMAP.
          05 GREETO PIC X(8).
       PROCEDURE DIVISION.
           MOVE 'MYMAP' TO WS-MAPNM.
           MOVE 'HELLO!' TO GREETO.
           EXEC CICS SEND MAP(WS-MAPNM) END-EXEC.
           EXEC CICS RETURN END-EXEC.
           STOP RUN.
"""


@pytest.mark.skip(reason="re-enabled after Task 7 migration (red-dragon-zvta)")
@covers(CobolFeature.EXEC_CICS)
def test_send_map_data_name_resolves_runtime_value(cobol_parser):
    """SEND MAP(WS-MAPNM) sends the runtime VALUE 'MYMAP', not the field name (g5gx)."""
    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()

    loader = BmsLoader(maps_dir=None)
    loader.register_stub(
        "MYMAP", BmsMap(name="MYMAP", fields={"GREET": BmsField(offset=0, length=8)})
    )

    result = run_carddemo_region(
        transid_to_program={"CC00": "DNPGM"},
        program_sources={"DNPGM": apply_cics_prepass(DATANAME_PGM_SRC).encode()},
        parser=cobol_parser,
        entry_transid="CC00",
        screen_queue=screen_q,
        input_queue=input_q,
        bms_loader=loader,
    )

    assert result.kind == DispatchKind.RETURN

    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())

    assert len(screens) == 1
    # The map name is the DECODED field value 'MYMAP' (not 'WS-MAPNM').
    assert screens[0]["map"] == "MYMAP"
    assert screens[0]["fields"].get("GREET") == "HELLO!"
