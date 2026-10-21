# pyright: standard
"""The foundation programs run alike in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import HlasmRun, run_hlasm
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390


def differential(z390: Z390Runner, source: str, tmp: Path) -> tuple[HlasmRun, HlasmRun]:
    return run_hlasm(source), z390.run(source, tmp)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_return_code_matches(z390: Z390Runner, tmp_path: Path):
    source = (
        "HELLO    CSECT\n"
        "         LA    15,7\n"
        "         BR    14\n"
        "         END   HELLO\n"
    )

    expected = HlasmRun(return_code=7, abend="", stdout="")
    assert differential(z390, source, tmp_path) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_wto_matches(z390: Z390Runner, tmp_path: Path):
    source = (
        "HELLO    CSECT\n"
        "         WTO   'HELLO WORLD'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END\n"
    )

    expected = HlasmRun(return_code=0, abend="", stdout="HELLO WORLD\n")
    assert differential(z390, source, tmp_path) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_user_abend_matches(z390: Z390Runner, tmp_path: Path):
    source = (
        "QUIT     CSECT\n"
        "         ABEND 42\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END\n"
    )

    expected = HlasmRun(return_code=0, abend="U0042", stdout="")
    assert differential(z390, source, tmp_path) == (expected, expected)
