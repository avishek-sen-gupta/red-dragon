"""NIST-85 Source Text Manipulation tests (SM series): COPY and REPLACE.

Run: uv run python -m pytest tests/nist/test_sm.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). COPY members are the K*.CPY library
texts beside the programs. A SUBPRG member runs after the run units before it in its
CCVS job, which create the files it reads. The FIPS flagger programs (SM301M, SM401M)
are classified, not run: their verdict is compile-time flagging messages. Excluded from
the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist, skip_flagger_program

pytestmark = pytest.mark.nist


@covers(CobolFeature.MULTI_FILE_IMPORTS)
@pytest.mark.parametrize(
    "prog",
    [
        "SM101A",
        "SM102A",
        "SM103A",
        "SM104A",
        "SM105A",
        "SM106A",
        "SM107A",
        "SM201A",
        "SM202A",
        "SM203A",
        "SM204A",
        "SM205A",
        "SM206A",
        "SM207A",
        "SM208A",
    ],
)
def test_sm_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)


@pytest.mark.parametrize(
    "prog, header, flags_expected",
    [
        ("SM301M", "The following program tests the flagging of the intermediate", 1),
        ("SM401M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF HIGH", 2),
    ],
)
def test_sm_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    skip_flagger_program(prog, header, flags_expected)
