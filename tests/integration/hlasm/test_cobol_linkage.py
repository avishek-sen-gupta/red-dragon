# pyright: standard
"""COBOL and HLASM in one image: both start-ups in a fixed order, each program entered by name, one duplicate check over both languages; a COBOL CALL builds a standard R1 list, an HLASM call to a COBOL program walks one by its USING signature, calls nest, and an HLASM abend ends the run unit."""

from pathlib import Path

import pytest

from interpreter.cobol.layout_data import field_positions
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
from interpreter.run import declarations_of, initial_vm_state, run_linked
from interpreter.vm.builtins import compose_builtins, core_builtins
from interpreter.vm.vm_types import VMState
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import ws_region
from tests.integration.hlasm.fixed_machine_clock import FixedMachineClock
from tests.integration.hlasm.hlasm_helpers import MAX_STEPS, gpr, hlasm_run_of
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


CALLS_ASMSUB = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COBMAIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A   PIC X(20) VALUE SPACES.
       01  WS-B   PIC X(4)  VALUE 'SAME'.
       01  WS-N   PIC S9(9) COMP-5 VALUE 305419896.
       01  WS-H   PIC S9(4) COMP-5 VALUE -2.
       01  WS-C   PIC X VALUE 'Q'.
       01  WS-D   COMP-2.
       01  WS-RC  PIC S9(4) COMP-5 VALUE 0.
       PROCEDURE DIVISION.
           MOVE 1.5 TO WS-D.
           CALL 'ASMSUB' USING BY REFERENCE WS-A BY CONTENT WS-B
               BY VALUE WS-N WS-H WS-C WS-D.
           MOVE RETURN-CODE TO WS-RC.
           CANCEL 'ASMSUB'.
           GOBACK.
"""
ASMSUB = b"""\
ASMSUB   CSECT
         LR    12,15
         USING ASMSUB,12
         LM    2,8,0(1)
         STM   4,8,0(2)
         MVC   0(4,3),=C'ZZZZ'
         L     15,=F'-7'
         BR    14
         END
"""
CALLS_OMITTING = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COBOMIT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-W1  PIC X(8) VALUE SPACES.
       01  WS-W2  PIC X(4) VALUE SPACES.
       PROCEDURE DIVISION.
           CALL 'ASMOMIT' USING WS-W1 OMITTED WS-W2 OMITTED.
           GOBACK.
"""
ASMOMIT = b"""\
ASMOMIT  CSECT
         LR    12,15
         USING ASMOMIT,12
         LM    2,5,0(1)
         ST    3,0(,2)
         ST    5,4(,2)
         MVC   0(4,4),=C'SEEN'
         SR    15,15
         BR    14
         END
"""
COBSUB = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COBSUB.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-A   PIC X(5).
       01  LK-N   PIC S9(9) COMP-5.
       01  LK-B   PIC S9(9) COMP-5.
       PROCEDURE DIVISION USING LK-A BY VALUE LK-N BY REFERENCE LK-B.
           MOVE 'HELLO' TO LK-A.
           IF ADDRESS OF LK-B = NULL
               MOVE 9 TO RETURN-CODE
           ELSE
               COMPUTE LK-B = LK-N + 1
               MOVE 5 TO RETURN-CODE
           END-IF.
           GOBACK.
"""
CALLS_COBSUB = b"""\
ASMMAIN  CSECT
         LR    12,15
         USING ASMMAIN,12
         LR    11,14
         LA    2,77
         LA    4,NUMBER
         O     4,=X'80000000'
         ST    4,LIST+8
         LA    1,LIST
         L     15,=V(COBSUB)
         BALR  14,15
         LR    3,15
         LA    4,FIELD2
         O     4,=X'80000000'
         ST    4,SHORT
         LA    1,SHORT
         L     15,=V(COBSUB)
         BALR  14,15
         LR    4,15
         L     5,NUMBER
         L     6,FIELD
         L     7,FIELD2
         LR    14,11
         LR    15,2
         BR    14
LIST     DC    A(FIELD)
         DC    F'41'
         DC    A(0)
SHORT    DC    A(0)
NUMBER   DC    F'0'
FIELD    DC    CL5' '
FIELD2   DC    CL5' '
         END
"""
NESTS = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NMAIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-X   PIC X(4) VALUE SPACES.
       01  WS-RC  PIC S9(4) COMP-5 VALUE 0.
       PROCEDURE DIVISION.
           CALL 'ASMMID' USING WS-X.
           MOVE RETURN-CODE TO WS-RC.
           GOBACK.
"""
ASMMID = b"""\
ASMMID   CSECT
         LR    12,15
         USING ASMMID,12
         LR    11,14
         LA    2,77
         L     15,=V(COBLEAF)
         BALR  14,15
         AR    15,2
         LR    14,11
         BR    14
         END
"""
COBLEAF = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COBLEAF.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-X   PIC X(4).
       PROCEDURE DIVISION USING LK-X.
           CALL 'ASMCLOB'.
           MOVE 'LEAF' TO LK-X.
           MOVE 3 TO RETURN-CODE.
           GOBACK.
"""
ASMCLOB = b"""\
ASMCLOB  CSECT
         LA    2,5
         LA    11,0
         SR    15,15
         BR    14
         END
"""
ABENDS_UNDER_COBOL = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ABMAIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-X   PIC X(5) VALUE 'FIRST'.
       PROCEDURE DIVISION.
           CALL 'ASMABND'.
           MOVE 'AFTER' TO WS-X.
           GOBACK.
"""
ASMABND = b"""\
ASMABND  CSECT
         ABEND 5
         END
"""
EBCDIC = "cp037"
LOW_WORD = 0xFFFFFFFF


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


def _image(
    cobol: tuple[bytes, ...], hlasm: tuple[bytes, ...], work_dir: Path
) -> LinkedProgram:
    return link_hlasm_units(
        (
            *(unit for source in cobol for unit in _cobol(source, work_dir)),
            *(
                unit
                for at, source in enumerate(hlasm)
                for unit in _hlasm(f"ASM{at}.asm", source, work_dir)
            ),
        ),
        work_dir,
    )


def _ws(vm: VMState, image: LinkedProgram, program: str) -> dict[str, bytes]:
    region = ws_region(vm, program)
    return {
        name: bytes(region[p.offset : p.offset + p.length])
        for name, p in field_positions(declarations_of(image, program)).items()
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_cobol_call_hands_hlasm_a_standard_list_and_takes_r15(tmp_path: Path):
    image = _image((CALLS_ASMSUB,), (ASMSUB,), tmp_path)

    ws = _ws(_entered(image, "COBMAIN"), image, "COBMAIN")

    assert (ws["WS-A"], ws["WS-B"], ws["WS-RC"]) == (
        bytes.fromhex("12345678" "0000FFFE" "000000D8") + ws["WS-D"],
        "SAME".encode(EBCDIC),
        bytes.fromhex("FFF9"),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_omitted_is_a_zero_word_and_the_high_bit_alone_when_last(tmp_path: Path):
    image = _image((CALLS_OMITTING,), (ASMOMIT,), tmp_path)

    ws = _ws(_entered(image, "COBOMIT"), image, "COBOMIT")

    assert (ws["WS-W1"], ws["WS-W2"]) == (
        bytes.fromhex("00000000" "80000000"),
        "SEEN".encode(EBCDIC),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_hlasm_calls_a_cobol_program_by_its_using_signature(tmp_path: Path):
    image = _image((COBSUB,), (CALLS_COBSUB,), tmp_path)

    vm = _entered(image, "ASMMAIN")

    assert (
        hlasm_run_of(vm, ""),
        [gpr(vm, r) & LOW_WORD for r in (2, 3, 4, 5)],
        [(gpr(vm, r) & LOW_WORD).to_bytes(4, "big") for r in (6, 7)],
    ) == (
        HlasmRun(return_code=77, abend="", stdout=""),
        [77, 5, 9, 42],
        ["HELL".encode(EBCDIC), "HELL".encode(EBCDIC)],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_hlasm_cobol_nests_and_registers_survive_the_cobol_call(
    tmp_path: Path,
):
    image = _image((NESTS, COBLEAF), (ASMMID, ASMCLOB), tmp_path)

    ws = _ws(_entered(image, "NMAIN"), image, "NMAIN")

    assert (ws["WS-X"], ws["WS-RC"]) == ("LEAF".encode(EBCDIC), (80).to_bytes(2, "big"))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_hlasm_abend_ends_the_run_unit_under_a_cobol_caller(tmp_path: Path):
    image = _image((ABENDS_UNDER_COBOL,), (ASMABND,), tmp_path)

    vm = _entered(image, "ABMAIN")

    assert (_ws(vm, image, "ABMAIN")["WS-X"], hlasm_run_of(vm, "")) == (
        "FIRST".encode(EBCDIC),
        HlasmRun(return_code=0, abend="U0005", stdout=""),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_id_that_is_also_a_csect_is_refused_naming_both(tmp_path: Path):
    units = (*_hlasm("ASM.asm", ASM_NINE, tmp_path), *_cobol(NAMED_ASMMAIN, tmp_path))

    with pytest.raises(DuplicateProgramInImage) as refused:
        link_hlasm_units(units, tmp_path)

    assert str(refused.value) == (
        "program ASMMAIN is in the image twice: ASM.asm and ASMMAIN.cbl"
    )
