"""NIST-85 Communication tests (CM series): message queues through an MCS.

Run: uv run python -m pytest tests/nist/test_cm.py -m nist -v

Every CM program sends and receives through a Message Control System, which the
interpreter does not provide, so each is skipped. The FIPS flagger programs (CM303M,
CM401M) are classified, not run: their verdict is compile-time flagging messages.
Excluded from the default test run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import FeatureStatus, covers
from tests.nist.conftest import run_nist, skip_flagger_program

pytestmark = pytest.mark.nist


@covers(CobolFeature.ACCEPT, status=FeatureStatus.UNSUPPORTED)
@pytest.mark.skip(
    reason="CM programs need a Message Control System (CD entries, SEND/RECEIVE, "
    "ENABLE/DISABLE); out of scope for the interpreter."
)
@pytest.mark.parametrize(
    "prog",
    [
        "CM101M",
        "CM102M",
        "CM103M",
        "CM104M",
        "CM105M",
        "CM201M",
        "CM202M",
    ],
)
def test_cm_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)


@pytest.mark.parametrize(
    "prog, header, flags_expected",
    [
        ("CM303M", "THE FOLLOWING PROGRAM TESTS THE FLAGGING OF", 2),
        ("CM401M", "The following program tests the flagging of level 2", 10),
    ],
)
def test_cm_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    skip_flagger_program(prog, header, flags_expected)
