"""NIST-85 Sequential File I/O tests (SQ series).

Run: uv run python -m pytest tests/nist/test_sq.py -m nist -v

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
        "SQ101M",
        "SQ102A",
        "SQ103A",
        "SQ104A",
        "SQ105A",
        "SQ106A",
        "SQ107A",
        "SQ108A",
        "SQ109M",
        "SQ110M",
        "SQ111A",
        "SQ112A",
        "SQ113A",
        "SQ114A",
        "SQ115A",
        "SQ116A",
        "SQ117A",
        "SQ121A",
        "SQ122A",
        "SQ123A",
        "SQ124A",
        "SQ125A",
        "SQ126A",
        "SQ127A",
        "SQ128A",
        "SQ129A",
        "SQ130A",
        "SQ131A",
        "SQ132A",
        "SQ133A",
        "SQ134A",
        "SQ135A",
        "SQ136A",
        "SQ137A",
        "SQ138A",
        "SQ139A",
        "SQ140A",
        "SQ141A",
        "SQ142A",
        "SQ143A",
        "SQ144A",
        "SQ146A",
        "SQ147A",
        "SQ148A",
        "SQ149A",
        "SQ150A",
        "SQ151A",
        "SQ152A",
        "SQ153A",
        "SQ154A",
        "SQ155A",
        "SQ156A",
        "SQ201M",
        "SQ202A",
        "SQ203A",
        "SQ204A",
        "SQ205A",
        "SQ206A",
        "SQ207M",
        "SQ208M",
        "SQ209M",
        "SQ210M",
        "SQ211A",
        "SQ212A",
        "SQ213A",
        "SQ214A",
        "SQ215A",
        "SQ216A",
        "SQ217A",
        "SQ218A",
        "SQ219A",
        "SQ220A",
        "SQ221A",
        "SQ222A",
        "SQ223A",
        "SQ224A",
        "SQ225A",
        "SQ226A",
        "SQ227A",
        "SQ228A",
        "SQ229A",
        "SQ230A",
        "SQ302M",
        "SQ303M",
        "SQ401M",
    ],
)
def test_sq_program(prog: str, tmp_path: Path) -> None:
    _run_nist(prog, tmp_path)
