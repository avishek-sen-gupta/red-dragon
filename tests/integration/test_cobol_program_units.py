"""Every program of a source file reaches the run unit, batch and nested (red-dragon-ljku.1).

A source holds programs written one after another, each ended by END PROGRAM, or
programs contained in another and ended by END PROGRAM before the containing
program's own END PROGRAM header (IBM Enterprise COBOL LR, "Nested programs"). The
main program is the first top-level one; each other program is a program of the run
unit that a CALL names.
"""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.layout_data import field_positions
from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.project.types import LinkedProgram
from interpreter.run import declarations_of, initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
from tests.covers import covers
from tests.integration.cobol_helpers import ws_region

_BATCH = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BATCHA.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-N    PIC 9(4) VALUE 7.
       01  WS-TEXT PIC X(4) VALUE SPACES.
       PROCEDURE DIVISION.
           CALL 'BATCHA-1' USING WS-N WS-TEXT.
           STOP RUN.
       END PROGRAM BATCHA.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BATCHA-1.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-N    PIC 9(4).
       01  LK-TEXT PIC X(4).
       PROCEDURE DIVISION USING LK-N LK-TEXT.
           ADD 10 TO LK-N.
           MOVE 'SIBL' TO LK-TEXT.
           GOBACK.
       END PROGRAM BATCHA-1.
"""

_NESTED = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NESTA.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ONE  PIC 9(4) VALUE 1.
       01  WS-TWO  PIC 9(4) VALUE 2.
       PROCEDURE DIVISION.
           CALL 'NESTA-1' USING WS-ONE.
           CALL 'NESTA-2' USING WS-TWO.
           STOP RUN.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NESTA-1.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-ONE  PIC 9(4).
       PROCEDURE DIVISION USING LK-ONE.
           ADD 100 TO LK-ONE.
           GOBACK.
       END PROGRAM NESTA-1.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NESTA-2.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-TWO  PIC 9(4).
       PROCEDURE DIVISION USING LK-TWO.
           MULTIPLY 3 BY LK-TWO.
           GOBACK.
       END PROGRAM NESTA-2.
       END PROGRAM NESTA.
"""


def _working_storage_after_run(linked: LinkedProgram, program: str) -> dict[str, bytes]:
    entry = linked.entry_func_label
    vm = run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=20_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )
    region = ws_region(vm, program)
    return {
        name: bytes(region[p.offset : p.offset + p.length])
        for name, p in field_positions(declarations_of(linked, program)).items()
    }


@covers(CobolFeature.BATCHED_PROGRAMS, CobolFeature.CALL_USING)
def test_a_main_program_calls_the_program_written_after_it_and_gets_values_back(
    tmp_path,
):
    linked = compile_cobol(_BATCH, parser=make_cobol_parser(), work_dir=tmp_path)

    assert (
        sorted(linked.programs),
        _working_storage_after_run(linked, "BATCHA"),
    ) == (
        ["BATCHA", "BATCHA-1"],
        {"WS-N": "0017".encode("cp037"), "WS-TEXT": "SIBL".encode("cp037")},
    )


@covers(CobolFeature.NESTED_PROGRAMS, CobolFeature.CALL_USING)
def test_a_main_program_calls_both_programs_it_contains(tmp_path):
    linked = compile_cobol(_NESTED, parser=make_cobol_parser(), work_dir=tmp_path)

    assert (
        sorted(linked.programs),
        _working_storage_after_run(linked, "NESTA"),
    ) == (
        ["NESTA", "NESTA-1", "NESTA-2"],
        {"WS-ONE": "0101".encode("cp037"), "WS-TWO": "0006".encode("cp037")},
    )
