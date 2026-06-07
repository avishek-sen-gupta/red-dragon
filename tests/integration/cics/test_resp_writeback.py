"""Integration: EIBRESP / RESP(name) write-back after a CICS service verb.

Task F2 of the CICS field-ref wiring plan.

A program does ``EXEC CICS INQUIRE PROGRAM(WS-MISSING) RESP(WS-RC)`` for a
program that is NOT in the program cache, so the INQUIRE builtin returns 27
(PGMIDERR). The write-back must store 27 into WS-RC; the program then checks
``IF WS-RC = DFHRESP(PGMIDERR)`` and sets a flag MOVEd into the COMMAREA. The
test asserts the flag round-trips, proving the resp code was written into the
RESP field and decoded correctly from a COMP binary field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from interpreter.cics.preprocessor import apply_cics_prepass
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.cics.types import CicsContext, DispatchKind
from interpreter.cics.dispatcher import run_cics
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


COBOL_RESP = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTRESP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-MISSING PIC X(8) VALUE 'NOPROG  '.
       01 WS-RC      PIC S9(8) COMP.
       01 WS-CA.
          05 WS-CA-FLAG PIC X(1).
       PROCEDURE DIVISION.
           MOVE 'N' TO WS-CA-FLAG.
           EXEC CICS INQUIRE PROGRAM(WS-MISSING) RESP(WS-RC)
               NOHANDLE END-EXEC.
           IF WS-RC = DFHRESP(PGMIDERR)
               MOVE 'Y' TO WS-CA-FLAG
           END-IF.
           EXEC CICS RETURN TRANSID('CC01') COMMAREA(WS-CA) END-EXEC.
           STOP RUN.
"""


def _link_single_cobol(source: bytes, frontend: CobolFrontend):
    from interpreter.cfg import build_cfg
    from interpreter.registry import build_registry
    from interpreter.constants import Language
    from interpreter.project.types import LinkedProgram

    instructions = frontend.lower(source)
    cfg = build_cfg(instructions)
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    return LinkedProgram(
        modules={},
        merged_ir=list(instructions),
        merged_cfg=cfg,
        merged_registry=registry,
        language=Language.COBOL,
        import_graph={},
        type_env_builder=frontend.type_env_builder,
        symbol_table=frontend.symbol_table,
        data_layout=frontend.data_layout,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )


@covers(CobolFeature.EXEC_CICS)
def test_inquire_resp_writeback_round_trips(cobol_parser):
    """INQUIRE of a missing program writes PGMIDERR(27) to WS-RC; IF check fires."""
    import queue

    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder, result_holder=result_holder
    )
    source = apply_cics_prepass(COBOL_RESP).encode()
    frontend = CobolFrontend(cobol_parser=cobol_parser, exec_cics_strategy=strategy)
    program = _link_single_cobol(source, frontend)

    result = run_cics(
        program,
        context_holder[0],
        queue.Queue(),
        queue.Queue(),
        context_holder=context_holder,
        result_holder=result_holder,
    )

    assert result.kind == DispatchKind.RETURN_TRANSID
    # The IF WS-RC = DFHRESP(PGMIDERR) check fired, setting the flag to 'Y'.
    expected = "Y".encode("cp037")
    assert result.commarea == expected, (
        f"RESP(WS-RC) write-back did not round-trip: flag={result.commarea!r} "
        f"(expected {expected!r}); WS-RC likely was not set to PGMIDERR"
    )
