"""Integration: UNSTRING with no DELIMITED BY fills each receiver by its size."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(CobolFeature.UNSTRING_VERB)
def test_undelimited_unstring_moves_receiver_sized_pieces():
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. UNSSIZE.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 A   PIC X(3).",
            "01 B   PIC X(5).",
            "01 C   PIC X(2) VALUE 'ZZ'.",
            "01 SRC PIC X(6) VALUE 'ABCDEF'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    UNSTRING SRC INTO A B C",
            "    STOP RUN.",
        ],
        max_steps=100_000,
    )
    assert bytes(first_region(vm)[:10]).decode("cp037") == "ABC" "DEF  " "ZZ"
