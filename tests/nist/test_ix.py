"""NIST-85 Indexed File I/O tests (IX series).

Run: uv run python -m pytest tests/nist/test_ix.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). A SUBPRG member runs after the run
units before it in its CCVS job, which create the files it reads. The FIPS flagger
programs (IX301M, IX302M, IX401M) are classified, not run: their verdict is compile-time
flagging messages. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist, skip_flagger_program

pytestmark = pytest.mark.nist


@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
@pytest.mark.parametrize(
    "prog",
    [
        "IX101A",
        "IX102A",
        "IX103A",
        "IX104A",
        "IX105A",
        "IX106A",
        "IX107A",
        "IX108A",
        "IX109A",
        "IX110A",
        "IX111A",
        "IX112A",
        "IX113A",
        "IX114A",
        "IX115A",
        "IX116A",
        "IX117A",
        "IX118A",
        "IX119A",
        "IX120A",
        "IX121A",
        "IX201A",
        "IX202A",
        "IX203A",
        "IX204A",
        "IX205A",
        "IX206A",
        "IX207A",
        "IX208A",
        "IX209A",
        "IX210A",
        "IX211A",
        "IX212A",
        "IX213A",
        "IX214A",
        "IX215A",
        "IX216A",
        "IX217A",
        "IX218A",
    ],
)
def test_ix_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)


@pytest.mark.parametrize(
    "prog, header, flags_expected",
    [
        ("IX301M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF INTERMEDIATE", 7),
        ("IX302M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF", 4),
        ("IX401M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF HIGH", 10),
    ],
)
def test_ix_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    skip_flagger_program(prog, header, flags_expected)
