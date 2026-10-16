"""NIST-85 Nucleus tests (NC series): data description, arithmetic, MOVE, conditions,
PERFORM and the other core-language statements.

Run: uv run python -m pytest tests/nist/test_nc.py -m nist -v

A program passes only when it runs to its END OF TEST banner and its CCVS summary reports
zero failed tests (tests/nist/conftest.py). Known gaps are tracked under the NIST NC
conformance epic in beads. Excluded from the default test run; run on demand with `-m nist`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.run import run
from tests.covers import covers
from tests.nist.conftest import NIST_DIR, assert_nist_pass, make_provider

pytestmark = pytest.mark.nist


def _run_nist(prog: str, tmp_path: Path) -> None:
    src_path = NIST_DIR / f"{prog}.CBL"
    if not src_path.exists():
        pytest.skip(f"NIST source not found: {src_path}")
    src = src_path.read_text()
    provider, print_path = make_provider(src, tmp_path)
    run(src, language="cobol", io_provider=provider, max_steps=2_000_000)
    assert_nist_pass(print_path, prog)


@covers(CobolFeature.MOVE)
@covers(CobolFeature.ADD)
@covers(CobolFeature.COMPUTE)
@covers(CobolFeature.PERFORM)
@covers(CobolFeature.EVALUATE)
@pytest.mark.parametrize(
    "prog",
    [
        "NC101A",
        "NC102A",
        "NC103A",
        "NC104A",
        "NC105A",
        "NC106A",
        "NC107A",
        "NC108M",
        "NC109M",
        "NC110M",
        "NC111A",
        "NC112A",
        "NC113M",
        "NC114M",
        "NC115A",
        "NC116A",
        "NC117A",
        "NC118A",
        "NC119A",
        "NC120A",
        "NC121M",
        "NC122A",
        "NC123A",
        "NC124A",
        "NC125A",
        "NC126A",
        "NC127A",
        "NC131A",
        "NC132A",
        "NC133A",
        "NC134A",
        "NC135A",
        "NC136A",
        "NC137A",
        "NC138A",
        "NC139A",
        "NC140A",
        "NC141A",
        "NC170A",
        "NC171A",
        "NC172A",
        "NC173A",
        "NC174A",
        "NC175A",
        "NC176A",
        "NC177A",
        "NC201A",
        "NC202A",
        "NC203A",
        "NC204M",
        "NC205A",
        "NC206A",
        "NC207A",
        "NC208A",
        "NC209A",
        "NC210A",
        "NC211A",
        "NC214M",
        "NC215A",
        "NC216A",
        "NC217A",
        "NC218A",
        "NC219A",
        "NC220M",
        "NC221A",
        "NC222A",
        "NC223A",
        "NC224A",
        "NC225A",
        "NC231A",
        "NC232A",
        "NC233A",
        "NC234A",
        "NC235A",
        "NC236A",
        "NC237A",
        "NC238A",
        "NC239A",
        "NC240A",
        "NC241A",
        "NC242A",
        "NC243A",
        "NC244A",
        "NC245A",
        "NC246A",
        "NC247A",
        "NC248A",
        "NC250A",
        "NC251A",
        "NC252A",
        "NC253A",
        "NC254A",
        "NC302M",
        "NC303M",
        "NC401M",
    ],
)
def test_nc_program(prog: str, tmp_path: Path) -> None:
    _run_nist(prog, tmp_path)
