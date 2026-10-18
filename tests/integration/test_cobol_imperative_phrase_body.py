"""A statement inside a conditional phrase body does not take the outer statement's NOT phrase."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(CobolFeature.ON_SIZE_ERROR)
def test_not_on_size_error_after_a_nested_compute_belongs_to_the_add():
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. IMPBODY.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 A     PIC 9 VALUE 1.",
            "01 B     PIC 9 VALUE 0.",
            "01 FLAG  PIC X VALUE 'N'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    ADD 1 TO A",
            "        ON SIZE ERROR COMPUTE B = 9",
            "        NOT ON SIZE ERROR MOVE 'Y' TO FLAG",
            "    END-ADD",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )
    assert bytes(first_region(vm)[0:3]).decode("cp037") == "20Y"
