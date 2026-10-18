"""NIST-85 Nucleus tests (NC series): data description, arithmetic, MOVE, conditions,
PERFORM and the other core-language statements.

Run: uv run python -m pytest tests/nist/test_nc.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary reports
zero failed tests (tests/nist/conftest.py). Known gaps are tracked under the NIST NC
conformance epic in beads. The FIPS flagger programs (NC302M, NC303M, NC401M) are
classified, not run: their verdict is compile-time flagging messages. NC110M reports by
DISPLAY rather than to a PRINT-FILE, so its displayed report is checked. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_display_report, run_nist, skip_flagger_program

pytestmark = pytest.mark.nist


@covers(CobolFeature.MOVE)
@covers(CobolFeature.ADD)
@covers(CobolFeature.COMPUTE)
@covers(CobolFeature.PERFORM)
@covers(CobolFeature.EVALUATE)
@pytest.mark.parametrize(
    "prog",
    [
        "NC101A",
        "NC102A",
        "NC103A",
        "NC104A",
        "NC105A",
        "NC106A",
        "NC107A",
        "NC108M",
        "NC109M",
        "NC111A",
        "NC112A",
        "NC113M",
        "NC114M",
        "NC115A",
        "NC116A",
        "NC117A",
        "NC118A",
        "NC119A",
        "NC120A",
        "NC121M",
        "NC122A",
        "NC123A",
        "NC124A",
        "NC125A",
        "NC126A",
        "NC127A",
        "NC131A",
        "NC132A",
        "NC133A",
        "NC134A",
        "NC135A",
        "NC136A",
        "NC137A",
        "NC138A",
        "NC139A",
        "NC140A",
        "NC141A",
        "NC170A",
        "NC171A",
        "NC172A",
        "NC173A",
        "NC174A",
        "NC175A",
        "NC176A",
        "NC177A",
        "NC201A",
        "NC202A",
        "NC203A",
        "NC204M",
        "NC205A",
        "NC206A",
        "NC207A",
        "NC208A",
        "NC209A",
        "NC210A",
        "NC211A",
        "NC214M",
        "NC215A",
        "NC216A",
        "NC217A",
        "NC218A",
        "NC219A",
        "NC220M",
        "NC221A",
        "NC222A",
        "NC223A",
        "NC224A",
        "NC225A",
        "NC231A",
        "NC232A",
        "NC233A",
        "NC234A",
        "NC235A",
        "NC236A",
        "NC237A",
        "NC238A",
        "NC239A",
        "NC240A",
        "NC241A",
        "NC242A",
        "NC243A",
        "NC244A",
        "NC245A",
        "NC246A",
        "NC247A",
        "NC248A",
        "NC250A",
        "NC251A",
        "NC252A",
        "NC253A",
        "NC254A",
    ],
)
def test_nc_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)


@pytest.mark.parametrize(
    "prog, header, flags_expected",
    [
        ("NC302M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF OBSOLETE", 7),
        ("NC303M", "OBSOLETE HIGH SUBSET NUCLEUS FEATURES.", 4),
        ("NC401M", "THIS PROGRAM TESTS THE FLAGGING OF HIGH SUBSET NUCLEUS", 40),
    ],
)
def test_nc_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    skip_flagger_program(prog, header, flags_expected)


_NC110M_SEPARATOR = " " + "-" * 57


@covers(CobolFeature.DISPLAY, CobolFeature.GO_TO, CobolFeature.PERFORM)
@pytest.mark.parametrize("prog", ["NC110M"])
def test_nc110m_display_report(
    prog: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """NC110M's procedure division "CONSISTS ENTIRELY OF PARAGRAPH NAMES AND
    'DISPLAY' LITERAL STATEMENTS". Its GO TO test "PASSES UNLESS FAIL APPEARS
    BELOW" and its PERFORM test "FAILS UNLESS PASS APPEARS BELOW", so the result
    block between the separators must be the two feature lines and one PASS."""
    lines = run_display_report(prog, tmp_path, capsys)
    first = lines.index(_NC110M_SEPARATOR)
    last = lines.index(_NC110M_SEPARATOR, first + 1)
    assert (lines[first + 1 : last], lines[last + 1 : last + 3]) == (
        [
            " GO TO       THIS TEST PASSES UNLESS FAIL APPEARS BELOW.  ",
            " PERFORM     THIS TEST FAILS UNLESS PASS APPEARS BELOW.   ",
            "             PASS",
        ],
        [" ", "                  END OF TEST - NC110M                    "],
    )
