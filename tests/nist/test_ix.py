"""NIST-85 Indexed File I/O tests (IX series).

Run: poetry run python -m pytest tests/nist/test_ix.py -m nist -v

assert_nist_pass now requires real completion (END OF TEST banner) AND a zero
failure count in the CCVS summary — see tests/nist/conftest.py. Under that
honest bar most programs currently FAIL: across SQ/IX/RL only ~17/162 genuinely
pass; ~98 halt before completion (red-dragon-m0oa.7) and ~38 complete but report
real conformance failures. This suite is excluded from the default test run and
is executed on demand with `-m nist`.
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
    result = run(src, language="cobol", io_provider=provider, max_steps=1_000_000)
    assert result is not None, f"{prog}: run() returned None"
    assert_nist_pass(print_path, prog)


@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
@pytest.mark.parametrize(
    "prog",
    [
        "IX101A",
        "IX102A",
        "IX103A",
        "IX104A",
        "IX105A",
        "IX106A",
        "IX107A",
        "IX108A",
        "IX109A",
        "IX110A",
        "IX111A",
        "IX112A",
        "IX113A",
        "IX114A",
        "IX115A",
        "IX116A",
        "IX117A",
        "IX118A",
        "IX119A",
        "IX120A",
        "IX121A",
        "IX201A",
        "IX202A",
        "IX203A",
        "IX204A",
        "IX205A",
        "IX206A",
        "IX207A",
        "IX208A",
        "IX209A",
        "IX210A",
        "IX211A",
        "IX212A",
        "IX213A",
        "IX214A",
        "IX215A",
        "IX216A",
        "IX217A",
        "IX218A",
        "IX301M",
        "IX302M",
        "IX401M",
    ],
)
def test_ix_program(prog: str, tmp_path: Path) -> None:
    _run_nist(prog, tmp_path)
