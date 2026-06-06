"""Integration: DFHAID copybook resolves via ProLeap bridge and exposes field names.

Smoke-test verifying that COPY DFHAID resolves when the CICS copybooks
directory is supplied to ProLeapCobolParser and that the expected AID key
constants (DFHENTER, DFHPF3) appear in the parsed data fields.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from interpreter.cics.strategy import CatchAllLoweringStrategy
from interpreter.cics.preprocessor import apply_cics_prepass
from tests.covers import covers
from tests.integration.cobol_helpers import (
    JAR_AVAILABLE,
    JAR_PATH,
    all_field_names as _all_field_names,
    bridge_jar_env,
    to_fixed,
)

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)

_CICS_COPYBOOKS = Path(__file__).parents[3] / "interpreter" / "cics" / "copybooks"


@pytest.fixture(autouse=True)
def _bridge_jar_env(bridge_jar_env):
    """Auto-apply the shared PROLEAP_BRIDGE_JAR env fixture to every test here."""
    yield


@pytest.fixture
def cobol_parser():
    runner = RealSubprocessRunner()
    return ProLeapCobolParser(runner, JAR_PATH, copybook_dirs=[_CICS_COPYBOOKS])


COBOL_WITH_EXEC_CICS = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTCICS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DUMMY PIC X.
       PROCEDURE DIVISION.
           EXEC CICS RETURN END-EXEC.
           STOP RUN.
"""


@covers(CobolFeature.EXEC_CICS)
def test_catchall_strategy_does_not_raise(cobol_parser):
    """COBOL with EXEC CICS compiles without error using CatchAllLoweringStrategy."""
    source = apply_cics_prepass(COBOL_WITH_EXEC_CICS).encode()
    frontend = CobolFrontend(
        cobol_parser=cobol_parser,
        exec_cics_strategy=CatchAllLoweringStrategy(),
    )
    instructions = frontend.lower(source)
    assert len(instructions) > 0


@covers(CobolFeature.MULTI_FILE_IMPORTS)
@covers(CobolFeature.EXEC_CICS)
def test_dfhaid_copy_resolves_and_exposes_aid_key_constants():
    """COPY DFHAID resolves to the canonical copybook and exposes DFHENTER and DFHPF3."""
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SMOKEAID.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "COPY DFHAID.",
            "PROCEDURE DIVISION.",
            "    STOP RUN.",
        ]
    )
    runner = RealSubprocessRunner()
    parser = ProLeapCobolParser(
        runner,
        JAR_PATH,
        copybook_dirs=[_CICS_COPYBOOKS],
    )
    asg = parser.parse(source.encode("utf-8"))

    field_names = _all_field_names(asg.data_fields)
    assert "DFHENTER" in field_names, f"DFHENTER missing from {field_names}"
    assert "DFHPF3" in field_names, f"DFHPF3 missing from {field_names}"
