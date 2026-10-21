# pyright: standard
"""Compare programs leave the same declared registers and CC in RedDragon and in z390, bar z390 not checking relative-long alignment."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import compare_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm, run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    body, results, cc = programs.CASES[case]
    source = storage.based_program(body, storage.ABEND)

    expected = HlasmMachine(ABENDED, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_misaligned_relative_compare_abends_here_but_not_in_z390(
    z390: Z390Runner, tmp_path: Path
):
    source = storage.based_program("         CRL   2,NEG+2\n", storage.ABEND)

    assert run_hlasm(source) == HlasmRun(return_code=0, abend="S0C6", stdout="")
    assert z390.run_machine(source, tmp_path).restricted_to((2,)) == HlasmMachine(
        ABENDED, 1, {2: storage.FILL}
    )
