"""NIST-85 Report Writer tests (RW series).

Run: uv run python -m pytest tests/nist/test_rw.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary
reports zero failed tests (tests/nist/conftest.py). Excluded from the default test run;
run on demand with `-m nist`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.nist.conftest import run_nist

pytestmark = pytest.mark.nist


@covers(CobolFeature.WRITE)
@pytest.mark.parametrize(
    "prog",
    [
        "RW101A",
        "RW102A",
        "RW103A",
        "RW104A",
        "RW301M",
        "RW302M",
    ],
)
def test_rw_program(
    prog: str, tmp_path: Path, record_property: Callable[[str, str], None]
) -> None:
    run_nist(prog, tmp_path, record_property)
