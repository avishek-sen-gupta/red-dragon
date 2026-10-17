"""NIST-85 Intrinsic Function tests (IF series).

Run: uv run python -m pytest tests/nist/test_if.py -m nist -v

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


@covers(CobolFeature.INTRINSIC_FUNCTION)
@pytest.mark.parametrize(
    "prog",
    [
        "IF101A",
        "IF102A",
        "IF103A",
        "IF104A",
        "IF105A",
        "IF106A",
        "IF107A",
        "IF108A",
        "IF109A",
        "IF110A",
        "IF111A",
        "IF112A",
        "IF113A",
        "IF114A",
        "IF115A",
        "IF116A",
        "IF117A",
        "IF118A",
        "IF119A",
        "IF120A",
        "IF121A",
        "IF122A",
        "IF123A",
        "IF124A",
        "IF125A",
        "IF126A",
        "IF127A",
        "IF128A",
        "IF129A",
        "IF130A",
        "IF131A",
        "IF132A",
        "IF133A",
        "IF134A",
        "IF135A",
        "IF136A",
        "IF137A",
        "IF138A",
        "IF139A",
        "IF140A",
        "IF141A",
        "IF142A",
        "IF401M",
        "IF402M",
        "IF403M",
    ],
)
def test_if_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)
