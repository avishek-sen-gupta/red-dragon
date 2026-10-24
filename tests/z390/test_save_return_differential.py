# pyright: standard
"""SAVE, RETURN and YREGS leave the same registers and return code in RedDragon, with our macros, and in z390, with its own; z390 ignores the T and identifier operands, so the flag and the R14/R15 slots differ."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import save_return_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm, run_hlasm_machine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
Z390_IGNORES_T = {
    "whole_range_t_id_rc": {6: 0},
    "partial_range_with_t_saves_14_15": {6: 0, 9: 0},
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.SUB_CASES))
def test_registers_after_return_match(z390: Z390Runner, tmp_path: Path, case: str):
    body, expected = programs.SUB_CASES[case]
    source = programs.caller(body)

    ours = run_hlasm_machine(source)
    theirs = z390.run_machine(source, tmp_path)

    assert (
        (ours.run, programs.machine_view(ours.gprs)),
        (theirs.run, programs.machine_view(theirs.gprs)),
    ) == (
        (ABENDED, expected),
        (ABENDED, {**expected, **Z390_IGNORES_T.get(case, {})}),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_standard_entry_and_exit_returns_the_same_code(
    z390: Z390Runner, tmp_path: Path
):
    returned = HlasmRun(return_code=7, abend="", stdout="")

    assert (
        run_hlasm(programs.STANDARD),
        z390.run(programs.STANDARD, tmp_path),
    ) == (returned, returned)
