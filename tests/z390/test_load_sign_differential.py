# pyright: standard
"""Load and test, complement, positive and negative programs leave the same declared registers and CC in RedDragon and in z390, bar LTGR: z390 sets the CC but never writes R1."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_sign_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
LTGR_CASES = frozenset({"LTGR", "LTGR zero"})
MATCHING = [case for case in programs.CASES if case not in LTGR_CASES]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING)
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    body, results, cc = programs.CASES[case]
    source = storage.based_program(body, storage.ABEND)

    expected = HlasmMachine(ABENDED, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", sorted(LTGR_CASES))
def test_ltgr_loads_r1_here_but_z390_leaves_it(
    z390: Z390Runner, tmp_path: Path, case: str
):
    body, results, cc = programs.CASES[case]
    source = storage.based_program(body, storage.ABEND)

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (
        HlasmMachine(ABENDED, cc, results),
        HlasmMachine(ABENDED, cc, {**results, 4: storage.FILL}),
    )
