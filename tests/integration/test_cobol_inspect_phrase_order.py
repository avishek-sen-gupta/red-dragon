"""INSPECT phrases are applied in the order written, and an ALL after a pattern starts a new ALL phrase."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(CobolFeature.INSPECT_TALLYING, CobolFeature.INSPECT_REPLACING)
def test_phrases_apply_in_written_order_and_all_starts_a_phrase():
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. INSORD.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 W-LEAD  PIC X(6) VALUE 'AABBCA'.",
            "01 W-CHAR  PIC X(6) VALUE 'AABBCA'.",
            "01 N-AB    PIC 9 VALUE 0.",
            "01 N-LEAD  PIC 9 VALUE 0.",
            "01 N-CHAR  PIC 9 VALUE 0.",
            "01 W-TALL  PIC X(6) VALUE 'AABBCA'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    INSPECT W-LEAD REPLACING LEADING 'A' BY 'X' CHARACTERS BY 'Y'",
            "    INSPECT W-CHAR REPLACING CHARACTERS BY 'Y' BEFORE 'C'",
            "        ALL 'A' BY 'Z'",
            "    INSPECT W-TALL TALLYING N-AB FOR ALL 'A' ALL 'B'",
            "    INSPECT W-TALL TALLYING N-LEAD FOR LEADING 'A'",
            "        N-CHAR FOR CHARACTERS",
            "    STOP RUN.",
        ],
        max_steps=200000,
    )
    assert bytes(first_region(vm)[0:15]).decode("cp037") == (
        "XXYYYY" + "YYYYCZ" + "5" + "2" + "4"
    )
