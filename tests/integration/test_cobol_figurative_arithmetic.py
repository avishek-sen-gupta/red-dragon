"""Figurative constant ZERO as an arithmetic operand (red-dragon-b17i).

`ADD 8 TO ZERO GIVING X` and `ADD ZERO TO Y` decode a non-field operand via
float(operand). For the figurative ZERO that raised
`ValueError: could not convert string to float: 'ZERO'` and crashed lowering.
ZERO/ZEROS/ZEROES are numeric 0; they must resolve to 0 in arithmetic (other
figuratives like SPACE are not valid numeric operands and still fail loudly).
"""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)
from tests.integration.cobol_helpers import (
    first_region as _first_region,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


def _program() -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. FIGARITH.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  WS-X PIC 9(2) VALUE 0.",
        "01  WS-Y PIC 9(2) VALUE 5.",
        "PROCEDURE DIVISION.",
        "MAIN.",
        "    ADD 8 TO ZERO GIVING WS-X.",
        "    ADD ZERO TO WS-Y.",
        "    STOP RUN.",
    ]


@covers(CobolFeature.ADD)
def test_figurative_zero_arithmetic_operand() -> None:
    vm = run_cobol(_program(), max_steps=3000)
    region = _first_region(vm)
    assert _decode(region, 0, 2) == 8  # WS-X = 8 + ZERO  (GIVING path)
    assert _decode(region, 2, 2) == 5  # WS-Y = 5 + ZERO  (plain-ADD source)
