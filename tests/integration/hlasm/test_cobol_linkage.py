# pyright: standard
"""COBOL and HLASM in one image: both start-ups in a fixed order, each program entered by name, one duplicate check over both languages."""

from pathlib import Path

import pytest

from interpreter.frontend import make_cobol_parser
from interpreter.frontends import get_hlasm_parser
from interpreter.hlasm_run_inputs.job_parm_builtins import NO_PARM
from interpreter.hlasm_run_inputs.run_input_builtins import run_input_builtins
from interpreter.project.coprocessor_compile import lower_program
from interpreter.project.duplicate_program_in_image import DuplicateProgramInImage
from interpreter.project.hlasm_compile import link_hlasm_units, lower_hlasm_program
from interpreter.project.program_entry import ProgramEntry
from interpreter.project.source_file import SourceFile
from interpreter.project.types import LinkedProgram
from interpreter.run import initial_vm_state, run_linked
from interpreter.vm.builtins import compose_builtins, core_builtins
from interpreter.vm.vm_types import VMState
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.fixed_machine_clock import FixedMachineClock
from tests.integration.hlasm.hlasm_helpers import MAX_STEPS, hlasm_run_of
from tests.integration.hlasm.hlasm_run import HlasmRun

COBOL_SAYS = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COBMAIN.
       PROCEDURE DIVISION.
           DISPLAY 'IN COBOL'.
           GOBACK.
"""
NAMED_ASMMAIN = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ASMMAIN.
       PROCEDURE DIVISION.
           GOBACK.
"""
ASM_NINE = b"""\
ASMMAIN  CSECT
         LA    15,9
         BR    14
         END
"""


def _cobol(source: bytes, work_dir: Path) -> tuple[Path, ...]:
    return lower_program(
        source,
        parser=make_cobol_parser(),
        specs=(),
        copybook_dirs=(),
        work_dir=work_dir,
        tolerant=False,
    )


def _hlasm(name: str, source: bytes, work_dir: Path) -> tuple[Path, ...]:
    return lower_hlasm_program(
        SourceFile(Path(name), source), parser=get_hlasm_parser(), work_dir=work_dir
    )


def _entered(image: LinkedProgram, name: str) -> VMState:
    return run_linked(
        image,
        ProgramEntry(name),
        max_steps=MAX_STEPS,
        initial_vm=initial_vm_state(),
        builtins=compose_builtins(
            core_builtins(), run_input_builtins(FixedMachineClock(), NO_PARM)
        ),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_mixed_image_enters_each_program_by_name(tmp_path: Path, capsys):
    image = link_hlasm_units(
        (*_cobol(COBOL_SAYS, tmp_path), *_hlasm("ASM.asm", ASM_NINE, tmp_path)),
        tmp_path,
    )
    capsys.readouterr()

    _entered(image, "COBMAIN")
    said = capsys.readouterr().out
    assembled = _entered(image, "ASMMAIN")

    assert (
        [path.name for path in image.modules],
        sorted(image.programs),
        said,
        hlasm_run_of(assembled, ""),
    ) == (
        [
            "__cobol_start_up__",
            "__start_up__",
            "COBMAIN.cbl",
            "ASM.asm",
            "__hlasm_job__",
        ],
        ["ASMMAIN", "COBMAIN"],
        "IN COBOL\n",
        HlasmRun(return_code=9, abend="", stdout=""),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_id_that_is_also_a_csect_is_refused_naming_both(tmp_path: Path):
    units = (*_hlasm("ASM.asm", ASM_NINE, tmp_path), *_cobol(NAMED_ASMMAIN, tmp_path))

    with pytest.raises(DuplicateProgramInImage) as refused:
        link_hlasm_units(units, tmp_path)

    assert str(refused.value) == (
        "program ASMMAIN is in the image twice: ASM.asm and ASMMAIN.cbl"
    )
