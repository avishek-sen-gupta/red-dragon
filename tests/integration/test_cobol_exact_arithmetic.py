"""Exact COBOL fixed-point arithmetic end to end (red-dragon-4q25.1)."""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import first_region, run_cobol


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Fails loudly when PROLEAP_BRIDGE_JAR is unset."""


def _program(working_storage: list[str], procedure: list[str], max_steps: int = 5000):
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EXACT.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *working_storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *procedure,
            "    STOP RUN.",
        ],
        max_steps=max_steps,
    )


class TestEncodePaths:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_value_clause_fraction_into_integer_field_truncates(self):
        """red-dragon-bqds: VALUE 12.5 into PIC 999 stores 012, not 125."""
        vm = _program(["01 X PIC 999 VALUE 12.5."], ["    CONTINUE."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f1f2"


class TestNumericText:
    @covers(CobolFeature.CLASS_CONDITION)
    def test_tiny_implied_decimal_value_is_numeric(self):
        """str(float) rendered 1e-05, which IS NUMERIC rejected."""
        vm = _program(
            ["01 T PIC 9V9(5) VALUE 0.00001.", "01 FLAG PIC 9 VALUE 0."],
            ["    IF T IS NUMERIC", "        MOVE 1 TO FLAG", "    END-IF."],
        )
        assert first_region(vm)[6] == 0xF1
