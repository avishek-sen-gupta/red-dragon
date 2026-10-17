"""NIST-85 Debugging Module tests (DB series): debugging lines and USE FOR DEBUGGING.

Run: uv run python -m pytest tests/nist/test_db.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). Excluded from the default test run;
run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist

pytestmark = pytest.mark.nist


@covers(CobolFeature.DECLARATIVES)
@pytest.mark.parametrize(
    "prog",
    [
        "DB101A",
        "DB102A",
        "DB103M",
        "DB104A",
        "DB105A",
        "DB201A",
        "DB202A",
        "DB203A",
        "DB204A",
        "DB205A",
        "DB301M",
        "DB302M",
        "DB303M",
        "DB304M",
        "DB305M",
    ],
)
def test_db_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)
