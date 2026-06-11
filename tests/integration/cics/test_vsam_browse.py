"""Integration: VSAM browse round-trips real records (Task D3b).

The JAR-gated test drives a COBOL program through the REAL run_cics path with a
``CicsLoweringStrategy`` constructed with a ``vsam_engine`` built from a temp FCT.
The program WRITEs two records, STARTBRs, READNEXTs through them, MOVEs the
second record's body into the COMMAREA, and RETURNs — asserting the browsed
read-back bytes round-trip.
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
from interpreter.cics.vsam.backend import InMemoryBackend
from interpreter.cics.vsam.engine import VsamEngine
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig
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


# Record layout: 4-byte key + 6-byte body = 10 bytes. Two records written;
# browse forward returns them in key order, so the 2nd READNEXT yields BB02.
# WS-KEY is LOW-VALUES so STARTBR positions before the first record: in EBCDIC
# the letter keys (0xC1..) sort BELOW digit keys (0xF0..), so a numeric RIDFLD
# like '0000' would sort ABOVE 'AA01' and (correctly) position past end-of-file.
COBOL_BROWSE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTBRWS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-KEY  PIC X(4) VALUE LOW-VALUES.
       01 WS-REC.
          05 WS-REC-KEY  PIC X(4).
          05 WS-REC-BODY PIC X(6).
       01 WS-RD.
          05 WS-RD-KEY  PIC X(4).
          05 WS-RD-BODY PIC X(6).
       01 WS-CA.
          05 WS-CA-BODY PIC X(6).
       PROCEDURE DIVISION.
           MOVE 'AA01' TO WS-REC-KEY.
           MOVE 'ALPHA!' TO WS-REC-BODY.
           EXEC CICS WRITE FILE('TESTDS') FROM(WS-REC)
               RIDFLD(WS-REC-KEY) END-EXEC.
           MOVE 'BB02' TO WS-REC-KEY.
           MOVE 'BRAVO!' TO WS-REC-BODY.
           EXEC CICS WRITE FILE('TESTDS') FROM(WS-REC)
               RIDFLD(WS-REC-KEY) END-EXEC.
           EXEC CICS STARTBR FILE('TESTDS') RIDFLD(WS-KEY) END-EXEC.
           EXEC CICS READNEXT FILE('TESTDS') INTO(WS-RD)
               RIDFLD(WS-KEY) END-EXEC.
           EXEC CICS READNEXT FILE('TESTDS') INTO(WS-RD)
               RIDFLD(WS-KEY) END-EXEC.
           EXEC CICS ENDBR FILE('TESTDS') END-EXEC.
           MOVE WS-RD-BODY TO WS-CA-BODY.
           EXEC CICS RETURN TRANSID('CC01') COMMAREA(WS-CA) END-EXEC.
           STOP RUN.
"""


def _engine() -> VsamEngine:
    config = FctConfig(datasets={"TESTDS": DatasetConfig(record_length=10)})
    engine = VsamEngine(config, backend=InMemoryBackend())
    engine.load_all()
    return engine


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
def test_vsam_browse_forward_round_trips(cobol_parser):
    """STARTBR + two READNEXTs walk records in key order; 2nd record body reaches COMMAREA."""
    import queue

    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=_engine(),
    )
    source = apply_cics_prepass(COBOL_BROWSE).encode()
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
    expected = "BRAVO!".encode("cp037")
    assert (
        result.commarea == expected
    ), f"VSAM browse read-back did not round-trip: {result.commarea!r} (expected {expected!r})"
