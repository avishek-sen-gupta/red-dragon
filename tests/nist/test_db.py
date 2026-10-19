"""NIST-85 Debugging Module tests (DB series): debugging lines and USE FOR DEBUGGING.

Run: uv run python -m pytest tests/nist/test_db.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). The FIPS flagger programs (DB301M,
DB302M, DB303M, DB304M, DB305M) are classified, not run: their verdict is compile-time
flagging messages. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist, skip_flagger_program

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
    ],
)
def test_db_program(
    prog: str, tmp_path: Path, record_property: Callable[[str, str], None]
) -> None:
    run_nist(prog, tmp_path, record_property)


@pytest.mark.parametrize(
    "prog, header, flags_expected",
    [
        ("DB301M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF LEVEL 1", 1),
        ("DB302M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF LEVEL 1", 1),
        ("DB303M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF LEVEL 2", 2),
        ("DB304M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF OBSOLETE", 1),
        ("DB305M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF LEVEL 1", 1),
    ],
)
def test_db_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    skip_flagger_program(prog, header, flags_expected)
