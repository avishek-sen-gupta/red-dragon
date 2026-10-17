"""NIST-85 CCVS executive (EXEC85): the suite's own extraction program.

Run: uv run python -m pytest tests/nist/test_ex.py -m nist -v

EXEC85 extracts the test programs from the CCVS population file, substituting X-cards
from a control-card deck. Neither the population file (X-001) nor a control-card deck
(X-058) is in the corpus, and it writes no CCVS END OF TEST summary, so it is skipped.
Excluded from the default test run.
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
@pytest.mark.skip(
    reason="EXEC85 needs the CCVS population file (X-001) and a control-card deck "
    "(X-058), neither of which is in the corpus."
)
@pytest.mark.parametrize(
    "prog",
    [
        "EXEC85",
    ],
)
def test_ex_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)
