"""Integration: ASSIGN / FORMATTIME write their results into named COBOL fields.

Task F3 of the CICS field-ref wiring plan.

A program does ``EXEC CICS ASSIGN APPLID(WS-APPLID)`` and ``EXEC CICS FORMATTIME
ABSTIME(WS-T) YYYYMMDD(WS-D)``, then MOVEs the populated fields into a COMMAREA
and RETURNs. The test asserts the configured applid ("CARDDEMO") round-trips and
that the YYYYMMDD field holds 8 digits — proving both verbs now write their
output sub-option fields instead of no-opping.
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


COBOL_ASSIGN = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTASGN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-APPLID PIC X(8).
       01 WS-T      PIC S9(15) COMP-3.
       01 WS-D      PIC X(8).
       01 WS-CA.
          05 WS-CA-APPLID PIC X(8).
          05 WS-CA-DATE   PIC X(8).
       PROCEDURE DIVISION.
           EXEC CICS ASSIGN APPLID(WS-APPLID) END-EXEC.
           EXEC CICS ASKTIME ABSTIME(WS-T) END-EXEC.
           EXEC CICS FORMATTIME ABSTIME(WS-T) YYYYMMDD(WS-D) END-EXEC.
           MOVE WS-APPLID TO WS-CA-APPLID.
           MOVE WS-D TO WS-CA-DATE.
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
def test_assign_and_formattime_write_target_fields(cobol_parser):
    """ASSIGN APPLID and FORMATTIME YYYYMMDD populate their named fields."""
    import queue

    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        applid="CARDDEMO",
        sysid="SYS1",
    )
    source = apply_cics_prepass(COBOL_ASSIGN).encode()
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
    decoded = result.commarea.decode("cp037")
    applid_part = decoded[:8]
    date_part = decoded[8:16]
    assert (
        applid_part == "CARDDEMO"
    ), f"ASSIGN APPLID did not round-trip: got {applid_part!r}"
    assert (
        date_part.strip().isdigit() and len(date_part.strip()) == 8
    ), f"FORMATTIME YYYYMMDD did not round-trip: got {date_part!r}"
