"""NIST-85 Obsolete Elements tests (OB series).

Run: uv run python -m pytest tests/nist/test_ob.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). OBIC1A is compiled with the SUBRTN
subprograms its *HEADER card names; OBSQ4A and OBSQ5A run after OBSQ3A, which writes the
tapes they read. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist

pytestmark = pytest.mark.nist


@covers(CobolFeature.CALL)
@covers(CobolFeature.OPEN)
@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@pytest.mark.parametrize(
    "prog",
    [
        "OBIC1A",
        "OBNC1M",
        "OBNC2M",
        "OBSQ1A",
        "OBSQ3A",
        "OBSQ4A",
        "OBSQ5A",
    ],
)
def test_ob_program(
    prog: str, tmp_path: Path, record_property: Callable[[str, str], None]
) -> None:
    run_nist(prog, tmp_path, record_property)
