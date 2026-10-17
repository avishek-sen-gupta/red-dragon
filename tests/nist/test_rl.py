"""NIST-85 Relative File I/O tests (RL series).

Run: uv run python -m pytest tests/nist/test_rl.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). A SUBPRG member runs after the run
units before it in its CCVS job, which create the files it reads. Excluded from the
default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist

pytestmark = pytest.mark.nist


@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
@pytest.mark.parametrize(
    "prog",
    [
        "RL101A",
        "RL102A",
        "RL103A",
        "RL104A",
        "RL105A",
        "RL106A",
        "RL107A",
        "RL108A",
        "RL109A",
        "RL110A",
        "RL111A",
        "RL112A",
        "RL113A",
        "RL114A",
        "RL115A",
        "RL116A",
        "RL117A",
        "RL118A",
        "RL119A",
        "RL201A",
        "RL202A",
        "RL203A",
        "RL204A",
        "RL205A",
        "RL206A",
        "RL207A",
        "RL208A",
        "RL209A",
        "RL210A",
        "RL211A",
        "RL212A",
        "RL213A",
        "RL301M",
        "RL302M",
        "RL401M",
    ],
)
def test_rl_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)
