"""NIST-85 Segmentation tests (SG series): fixed and independent segments.

Run: uv run python -m pytest tests/nist/test_sg.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). The FIPS flagger programs (SG302M,
SG303M, SG401M) are classified, not run: their verdict is compile-time flagging
messages. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist, skip_flagger_program

pytestmark = pytest.mark.nist


@covers(CobolFeature.PERFORM)
@covers(CobolFeature.GO_TO)
@covers(CobolFeature.ALTER)
@pytest.mark.parametrize(
    "prog",
    [
        "SG101A",
        "SG102A",
        "SG103A",
        "SG104A",
        "SG105A",
        "SG106A",
        "SG201A",
        "SG202A",
        "SG203A",
        "SG204A",
    ],
)
def test_sg_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)


@pytest.mark.parametrize(
    "prog, header, flags_expected",
    [
        ("SG302M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF", 1),
        ("SG303M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF", 4),
        ("SG401M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF LEVEL 2", 2),
    ],
)
def test_sg_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    skip_flagger_program(prog, header, flags_expected)
