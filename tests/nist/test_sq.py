"""NIST-85 Sequential File I/O tests (SQ series).

Run: uv run python -m pytest tests/nist/test_sq.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). A SUBPRG member runs after the run
units before it in its CCVS job, which create the files it reads. The FIPS flagger
programs (SQ302M, SQ303M, SQ401M) are classified, not run: their verdict is compile-time
flagging messages. So are SQ109M and SQ110M, the multi-reel and multi-unit tests: their
deck comments out the reel/unit lines, which leaves the write loop with no reachable
exit. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import (
    run_nist,
    skip_flagger_program,
    skip_reel_lines_deleted,
)

pytestmark = pytest.mark.nist


@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
@pytest.mark.parametrize(
    "prog",
    [
        "SQ101M",
        "SQ102A",
        "SQ103A",
        "SQ104A",
        "SQ105A",
        "SQ106A",
        "SQ107A",
        "SQ108A",
        "SQ111A",
        "SQ112A",
        "SQ113A",
        "SQ114A",
        "SQ115A",
        "SQ116A",
        "SQ117A",
        "SQ121A",
        "SQ122A",
        "SQ123A",
        "SQ124A",
        "SQ125A",
        "SQ126A",
        "SQ127A",
        "SQ128A",
        "SQ129A",
        "SQ130A",
        "SQ131A",
        "SQ132A",
        "SQ133A",
        "SQ134A",
        "SQ135A",
        "SQ136A",
        "SQ137A",
        "SQ138A",
        "SQ139A",
        "SQ140A",
        "SQ141A",
        "SQ142A",
        "SQ143A",
        "SQ144A",
        "SQ146A",
        "SQ147A",
        "SQ148A",
        "SQ149A",
        "SQ150A",
        "SQ151A",
        "SQ152A",
        "SQ153A",
        "SQ154A",
        "SQ155A",
        "SQ156A",
        "SQ201M",
        "SQ202A",
        "SQ203A",
        "SQ204A",
        "SQ205A",
        "SQ206A",
        "SQ207M",
        "SQ208M",
        "SQ209M",
        "SQ210M",
        "SQ211A",
        "SQ212A",
        "SQ213A",
        "SQ214A",
        "SQ215A",
        "SQ216A",
        "SQ217A",
        "SQ218A",
        "SQ219A",
        "SQ220A",
        "SQ221A",
        "SQ222A",
        "SQ223A",
        "SQ224A",
        "SQ225A",
        "SQ226A",
        "SQ227A",
        "SQ228A",
        "SQ229A",
        "SQ230A",
    ],
)
def test_sq_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)


@pytest.mark.parametrize(
    "prog, header, flags_expected",
    [
        ("SQ302M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF", 4),
        ("SQ303M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF", 2),
        ("SQ401M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF HIGH", 18),
    ],
)
def test_sq_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    skip_flagger_program(prog, header, flags_expected)


@covers(CobolFeature.CLOSE)
@pytest.mark.parametrize(
    "prog, deleted_remark, reel_test, exit_test",
    [
        (
            "SQ109M",
            'MOVE "CLOSE REEL DELETED" TO RE-MARK.',
            "XRECORD-NUMBER (1) EQUAL TO 325",
            "XRECORD-NUMBER (1) EQUAL TO 750",
        ),
        (
            "SQ110M",
            'MOVE "CLOSE UNIT DELETED" TO RE-MARK.',
            "XRECORD-NUMBER (1) EQUAL TO 196",
            "XRECORD-NUMBER (1) EQUAL TO 649",
        ),
    ],
)
def test_sq_reel_lines_deleted_program(
    prog: str, deleted_remark: str, reel_test: str, exit_test: str
) -> None:
    skip_reel_lines_deleted(prog, deleted_remark, reel_test, exit_test)
