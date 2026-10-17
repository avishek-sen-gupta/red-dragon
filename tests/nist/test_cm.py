"""NIST-85 Communication tests (CM series): message queues through an MCS.

Run: uv run python -m pytest tests/nist/test_cm.py -m nist -v

Every CM program sends and receives through a Message Control System, which the
interpreter does not provide, so each is skipped. Excluded from the default test run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import FeatureStatus, covers
from tests.nist.conftest import run_nist

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
        "CM303M",
        "CM401M",
    ],
)
def test_cm_program(prog: str, tmp_path: Path) -> None:
    run_nist(prog, tmp_path)
