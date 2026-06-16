"""NIST-85 Relative File I/O tests (RL series).

Run: poetry run python -m pytest tests/nist/test_rl.py -m nist -v

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
    result = run(src, language="cobol", io_provider=provider, max_steps=50_000)
    assert result is not None, f"{prog}: run() returned None"
    assert_nist_pass(print_path, prog)


@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
@pytest.mark.parametrize(
    "prog",
    [
        "RL101A",
        "RL102A",
        "RL103A",
        "RL104A",
        "RL105A",
        "RL106A",
        "RL107A",
        "RL108A",
        "RL109A",
        "RL110A",
        "RL111A",
        "RL112A",
        "RL113A",
        "RL114A",
        "RL115A",
        "RL116A",
        "RL117A",
        "RL118A",
        "RL119A",
        "RL201A",
        "RL202A",
        "RL203A",
        "RL204A",
        "RL205A",
        "RL206A",
        "RL207A",
        "RL208A",
        "RL209A",
        "RL210A",
        "RL211A",
        "RL212A",
        "RL213A",
        "RL301M",
        "RL302M",
        "RL401M",
    ],
)
def test_rl_program(prog: str, tmp_path: Path) -> None:
    _run_nist(prog, tmp_path)
