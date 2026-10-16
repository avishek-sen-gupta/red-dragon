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

    @covers(CobolFeature.PERFORM, CobolFeature.GO_TO)
    def test_unqualified_paragraph_name_resolves_in_its_own_section(self):
        assert (
            _trace(
                [
                    "S1 SECTION.",
                    "INIT.",
                    _step(1),
                    "    PERFORM WORK.",
                    "    GO TO S2.",
                    "WORK.",
                    _step(2),
                    "S2 SECTION.",
                    "INIT.",
                    _step(3),
                    "    PERFORM WORK.",
                    "    STOP RUN.",
                    "WORK.",
                    _step(4),
                ]
            )
            == 1234
        )

    @covers(CobolFeature.PERFORM, CobolFeature.PERFORM_THRU, CobolFeature.GO_TO)
    def test_qualified_paragraph_name_names_the_section_it_is_in(self):
        assert (
            _trace(
                [
                    "MAIN SECTION.",
                    "M1.",
                    "    PERFORM P1 OF S1.",
                    "    PERFORM P1 IN S2.",
                    "    PERFORM P1 OF S1 THRU P2 OF S1.",
                    "    GO TO P1 IN S1.",
                    "S1 SECTION.",
                    "P1.",
                    _step(1),
                    "P2.",
                    _step(2),
                    "S2 SECTION.",
                    "P1.",
                    _step(3),
                    "P2.",
                    _step(4),
                    "    STOP RUN.",
                ]
            )
            == 13121234
        )

    @pytest.mark.parametrize(
        "perform,expected",
        [
            ("PERFORM B1 THRU C1", 1231),
            ("PERFORM B1 THRU C1 2 TIMES", 123231),
        ],
    )
    @covers(CobolFeature.PERFORM_THRU, CobolFeature.PERFORM_TIMES)
    def test_perform_thru_a_section_returns_after_its_last_paragraph(
        self, perform: str, expected: int
    ):
        assert (
            _trace(
                [
                    "T SECTION.",
                    "T1.",
                    _step(1),
                    f"    {perform}.",
                    _step(1),
                    "    GO TO Z2.",
                    "A1 SECTION.",
                    "B1.",
                    _step(2),
                    "C1 SECTION.",
                    "D1.",
                    _step(3),
                    "Z1 SECTION.",
                    "Z2.",
                    "    STOP RUN.",
                ]
            )
            == expected
        )
