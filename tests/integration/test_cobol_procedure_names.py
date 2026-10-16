"""End-to-end: how PERFORM and GO TO resolve the procedure-names they reference.

Each procedure appends its own digit to WS-T, so WS-T spells the order in which
control reached them."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
    ws_region,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)


def _trace(procedure: list[str]) -> int:
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. PROCNAME.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-T PIC 9(8) VALUE 0.",
            "PROCEDURE DIVISION.",
            *procedure,
        ],
        max_steps=4000,
    )
    return _decode(ws_region(vm, "PROCNAME"), 0, 8)


def _step(digit: int) -> str:
    return f"    COMPUTE WS-T = WS-T * 10 + {digit}."


@pytest.mark.usefixtures("bridge_jar")
class TestProcedureNames:
    @covers(CobolFeature.PERFORM, CobolFeature.GO_TO)
    def test_procedure_names_are_case_insensitive(self):
        assert (
            _trace(
                [
                    "main section.",
                    "m1.",
                    _step(1),
                    "    perform pass.",
                    _step(2),
                    "    go to fin.",
                    "PASS.",
                    _step(3),
                    "Fin.",
                    _step(4),
                    "    stop run.",
                ]
            )
            == 1324
        )
