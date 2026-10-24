# pyright: standard
"""CALL, LINK and LOAD in RedDragon and in z390: CALL's lists reach a module autolinked from SYSOBJ, and LINK and LOAD reach a load module z390 finds beside the program. Return codes are compared, and after LINK the registers the linked program set (R7, and R9's VL bit). Both leave the registers as the linked program left them, but z390's LINK hands back R15 as 0 where IBM's hands back the program's R15, so z390's LINK return code is pinned at the sum alone (42, not 142)."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import program_service_programs as programs
from tests.integration.hlasm.far_branch_programs import module
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

LINK_THEN_ABEND = programs.LINKER.replace(
    "         LR    14,10\n         A     15,SUM\n         BR    14\n",
    "         ABEND 1\n",
)
ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
LOW_WORD = 0xFFFFFFFF
VL_SHIFT = 31
LOAD_THEN_RETURN_ITS_CODE = programs.LOADER.replace(
    "         DELETE EP=OTHER\n", "         DELETE EP=OTHER\n         LR    15,9\n"
)


def _ours(main: str, callee: str) -> tuple[int, str]:
    run = run_hlasm_machine(main, (module("SUB", callee),)).run
    return run.return_code, run.abend


def _called(z390: Z390Runner, tmp: Path) -> tuple[int, str]:
    tmp.mkdir()
    z390.assemble_object("SUB", programs.ADDER, tmp)
    run = z390.run(programs.CALLER, tmp, (f"SYSOBJ({tmp})",))
    return run.return_code, run.abend


def _loaded(z390: Z390Runner, tmp: Path, main: str, callee: str) -> tuple[int, str]:
    tmp.mkdir()
    z390.assemble_load_module("SUB", callee, tmp)
    run = z390.run(main, tmp)
    return run.return_code, run.abend


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_call_link_and_load_agree_with_z390(z390: Z390Runner, tmp_path: Path):
    ours = (
        _ours(programs.CALLER, programs.ADDER),
        _ours(programs.LINKER, programs.CLOBBERS),
        _ours(LOAD_THEN_RETURN_ITS_CODE, programs.RETURNS_23),
    )
    theirs = (
        _called(z390, tmp_path / "call"),
        _loaded(z390, tmp_path / "link", programs.LINKER, programs.CLOBBERS),
        _loaded(
            z390, tmp_path / "load", LOAD_THEN_RETURN_ITS_CODE, programs.RETURNS_23
        ),
    )

    assert (ours, theirs) == (
        ((180, ""), (142, ""), (23, "")),
        ((180, ""), (42, ""), (23, "")),
    )


def _left_registers(machine: HlasmMachine) -> tuple[HlasmRun, int, int]:
    return (
        machine.run,
        machine.gprs[7] & LOW_WORD,
        (machine.gprs[9] & LOW_WORD) >> VL_SHIFT,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_link_leaves_the_registers_the_program_left_as_z390_does(
    z390: Z390Runner, tmp_path: Path
):
    ours = run_hlasm_machine(LINK_THEN_ABEND, (module("SUB", programs.CLOBBERS),))
    z390.assemble_load_module("SUB", programs.CLOBBERS, tmp_path)
    theirs = z390.run_machine(LINK_THEN_ABEND, tmp_path)

    assert (_left_registers(ours), _left_registers(theirs)) == (
        (ABENDED, 99, 1),
        (ABENDED, 99, 1),
    )
