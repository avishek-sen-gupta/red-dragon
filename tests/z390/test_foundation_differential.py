# pyright: standard
"""The foundation programs run alike in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import HlasmRun, run_hlasm
from tests.z390.z390_assembly_failed import Z390AssemblyFailed
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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_assembly_failure_reports_exit_code_and_err(z390: Z390Runner, tmp_path: Path):
    source = (
        "BAD      CSECT\n"
        "         FOOBAR 1,2\n"
        "         BR    14\n"
        "         END\n"
    )

    with pytest.raises(Z390AssemblyFailed) as failed:
        z390.run(source, tmp_path)

    err = (tmp_path / "PROG.ERR").read_text(encoding="latin-1")
    assert str(failed.value) == f"z390 left no PROG.LOG: asmlg exited 12\n{err}"
