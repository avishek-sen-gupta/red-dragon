"""NIST-85 Inter-Program Communication tests (IC series): CALL, CANCEL, USING and nested
programs.

Run: uv run python -m pytest tests/nist/test_ic.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). Each main program is compiled
together with the SUBRTN subprograms its CCVS *HEADER card names; those subprograms are
not run on their own. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist

pytestmark = pytest.mark.nist


@covers(CobolFeature.CALL)
@covers(CobolFeature.CALL_USING)
@covers(CobolFeature.CANCEL)
@pytest.mark.parametrize(
    "prog",
    [
        "IC101A",
        "IC103A",
        "IC106A",
        "IC108A",
        "IC112A",
        "IC114A",
        "IC116M",
        "IC201A",
        "IC203A",
        "IC207A",
        "IC209A",
        "IC213A",
        "IC216A",
        "IC222A",
        "IC223A",
        "IC224A",
        "IC225A",
        "IC226A",
        "IC227A",
        "IC228A",
        "IC233A",
        "IC234A",
        "IC235A",
        "IC237A",
        "IC401M",
    ],
)
def test_ic_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)
