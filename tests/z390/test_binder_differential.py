# pyright: standard
"""An A-constant naming a DSECT label holds its offset, and a V-constant naming another module's ENTRY reads that module's data, in RedDragon's binder and in z390's linker (lz390 autolinks the second module's object from SYSOBJ; z390 echoes the SYSOBJ option into its output, so only its return code and abend are compared)."""

from pathlib import Path

import pytest

from interpreter.frontends import get_hlasm_parser
from interpreter.hlasm_run_inputs.job_parm_builtins import NO_PARM, job_parm_builtins
from interpreter.project.hlasm_compile import compile_hlasm
from interpreter.project.program_entry import ProgramEntry
from interpreter.project.source_file import SourceFile
from interpreter.run import initial_vm_state, run_linked
from interpreter.vm.builtins import compose_builtins, core_builtins
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import MAX_STEPS, hlasm_run_of, run_hlasm
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

CALLER = (
    "MAIN     CSECT\n"
    "         USING MAIN,15\n"
    "         L     2,=V(BDATA)\n"
    "         L     15,0(,2)\n"
    "         BR    14\n"
    "         DC    V(BMOD)\n"
    "         END   MAIN\n"
)
CALLEE = (
    "BMOD     CSECT\n"
    "         ENTRY BDATA\n"
    "         DC    F'1'\n"
    "BDATA    DC    F'42'\n"
    "         END\n"
)


def _red_dragon() -> HlasmRun:
    linked = compile_hlasm(
        CALLER.encode("ascii"),
        parser=get_hlasm_parser(),
        programs=(SourceFile(Path("BMOD.asm"), CALLEE.encode("ascii")),),
    )
    vm = run_linked(
        linked,
        ProgramEntry("MAIN"),
        max_steps=MAX_STEPS,
        initial_vm=initial_vm_state(),
        builtins=compose_builtins(core_builtins(), job_parm_builtins(NO_PARM)),
    )
    return hlasm_run_of(vm, "")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_v_constant_reads_another_modules_entry(z390: Z390Runner, tmp_path: Path):
    z390.assemble_object("BMOD", CALLEE, tmp_path)
    z390_run = z390.run(CALLER, tmp_path, (f"SYSOBJ({tmp_path})",))

    assert (_red_dragon(), (z390_run.return_code, z390_run.abend)) == (
        HlasmRun(return_code=42, abend="", stdout=""),
        (42, ""),
    )


DSECT_ADDRESS = (
    "MAIN     CSECT\n"
    "         USING MAIN,15\n"
    "         L     15,ADDR\n"
    "         BR    14\n"
    "ADDR     DC    A(FLD)\n"
    "D        DSECT\n"
    "         DS    F\n"
    "FLD      DS    F\n"
    "         END   MAIN\n"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_address_in_a_dsect_is_its_offset(z390: Z390Runner, tmp_path: Path):
    expected = HlasmRun(return_code=4, abend="", stdout="")

    assert (run_hlasm(DSECT_ADDRESS), z390.run(DSECT_ADDRESS, tmp_path)) == (
        expected,
        expected,
    )
