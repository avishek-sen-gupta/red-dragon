"""Integration: INSPECT phrase forms end to end (source -> bridge -> IR -> VM)."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(
    CobolFeature.INSPECT_TALLYING,
    CobolFeature.INSPECT_REPLACING,
    CobolFeature.INSPECT_CONVERTING,
)
def test_inspect_phrases_scan_once_with_regions_subscripts_and_combined_forms():
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. INSPHR.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 N-CHARS   PIC 99 VALUE 0.",
            "01 N-AFTER   PIC 99 VALUE 0.",
            "01 N-AA      PIC 9 VALUE 0.",
            "01 N-A       PIC 9 VALUE 0.",
            "01 N-MISS    PIC 9 VALUE 0.",
            "01 N-COMB    PIC 9 VALUE 0.",
            "01 CNTS.",
            "   02 CNT    PIC 9 OCCURS 2 VALUE 0.",
            "01 W-REPL    PIC X(5) VALUE 'HELLO'.",
            "01 W-COMB    PIC X(4) VALUE 'AXAX'.",
            "01 W-CONV    PIC X(12) VALUE 'GAQAUZTABAGA'.",
            "01 W-MISS    PIC X(6) VALUE 'ABCXYZ'.",
            "01 W-ALLS    PIC X(2) VALUE 'AB'.",
            "01 RECS.",
            "   02 REC    PIC X(5) OCCURS 2.",
            "01 W-TEXT    PIC X(10) VALUE 'WORLD WIDE'.",
            "01 W-AABA    PIC X(4) VALUE 'AABA'.",
            "01 I         PIC 9 VALUE 2.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    MOVE 'AABAA' TO REC (1)",
            "    MOVE 'BBAAB' TO REC (2)",
            "    INSPECT W-TEXT TALLYING N-CHARS FOR CHARACTERS",
            "    INSPECT W-TEXT TALLYING N-AFTER FOR CHARACTERS",
            "        AFTER 'W' BEFORE 'D'",
            "    INSPECT W-AABA TALLYING N-AA FOR ALL 'AA'",
            "        N-A FOR ALL 'A'",
            "    INSPECT W-MISS TALLYING N-MISS FOR ALL 'B'",
            "        AFTER INITIAL 'Q'",
            "    INSPECT W-MISS REPLACING ALL 'B' BY '-'",
            "        AFTER INITIAL 'Q'",
            "    INSPECT W-REPL REPLACING CHARACTERS BY 'O'",
            "        BEFORE INITIAL 'L'",
            "    INSPECT W-COMB TALLYING N-COMB FOR ALL 'A'",
            "        REPLACING FIRST 'A' BY 'O'",
            "    INSPECT W-CONV CONVERTING 'AU' TO '23'",
            "        BEFORE 'B' AFTER 'Q'",
            "    INSPECT W-ALLS REPLACING ALL 'A' BY 'B' ALL 'B' BY 'C'",
            "    INSPECT REC (I) TALLYING CNT (I) FOR ALL 'A'",
            "    INSPECT REC (I) REPLACING ALL 'A' BY 'Z'",
            "    STOP RUN.",
        ],
        max_steps=200_000,
    )
    assert bytes(first_region(vm)[:64]).decode("cp037") == (
        "10"
        "03"
        "1"
        "1"
        "0"
        "2"
        "02"
        "OOLLO"
        "OXAX"
        "GAQ23ZT2BAGA"
        "ABCXYZ"
        "BC"
        "AABAA"
        "BBZZB"
        "WORLD WIDE"
        "AABA"
        "2"
    )
