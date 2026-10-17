"""NIST-85 Sort-Merge tests (ST series): SORT and MERGE with USING/GIVING and
INPUT/OUTPUT PROCEDUREs.

Run: uv run python -m pytest tests/nist/test_st.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). A sort work file is the SD's ASSIGN,
mapped to a file like any other. A SUBPRG member runs after the run units before it in
its CCVS job, which create the files it reads. Excluded from the default test run; run
on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist

pytestmark = pytest.mark.nist


@covers(CobolFeature.OPEN)
@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@pytest.mark.parametrize(
    "prog",
    [
        "ST101A",
        "ST102A",
        "ST103A",
        "ST104A",
        "ST105A",
        "ST106A",
        "ST107A",
        "ST108A",
        "ST109A",
        "ST110A",
        "ST111A",
        "ST112M",
        "ST113M",
        "ST114M",
        "ST115A",
        "ST116A",
        "ST117A",
        "ST118A",
        "ST119A",
        "ST120A",
        "ST121A",
        "ST122A",
        "ST123A",
        "ST124A",
        "ST125A",
        "ST126A",
        "ST127A",
        "ST131A",
        "ST132A",
        "ST133A",
        "ST134A",
        "ST135A",
        "ST136A",
        "ST137A",
        "ST139A",
        "ST140A",
        "ST144A",
        "ST146A",
        "ST147A",
        "ST301M",
    ],
)
def test_st_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)
