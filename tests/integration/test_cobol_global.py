"""GLOBAL data, files and USE GLOBAL declaratives reach the programs a program contains
(red-dragon-ljku.4).

IBM Enterprise COBOL LR, scope of names: a referenced name is searched for among the
program's own declarations, then "only global declarations are searched in
successive outer containing programs"; "the search ends when the first matching name
is found".
"""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.layout_data import field_positions
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.project.types import LinkedProgram
from interpreter.run import declarations_of, initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
from tests.covers import covers
from tests.integration.cobol_helpers import ws_region

_DATA = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. OUTER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  G-VAL  PIC XX VALUE 'OU' GLOBAL.
       01  G-TWO  PIC XX VALUE 'OU' GLOBAL.
       01  G-GRP  GLOBAL.
           05  G-PART PIC 9(4) VALUE 7.
               88  G-PART-DONE VALUE 17.
       01  O-SEEN PIC X VALUE 'N'.
       01  G-SHADOW PIC XX VALUE 'OU' GLOBAL.
       01  G-FLAG   PIC X VALUE 'N' GLOBAL.
       PROCEDURE DIVISION.
           CALL 'MIDDLE'.
           IF G-PART-DONE MOVE 'Y' TO O-SEEN END-IF.
           STOP RUN.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MIDDLE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  G-VAL  PIC XX VALUE 'MI' GLOBAL.
       01  G-TWO  PIC XX VALUE 'MI'.
       PROCEDURE DIVISION.
           CALL 'INNER'.
           GOBACK.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INNER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  G-SHADOW PIC XX VALUE 'IS'.
       PROCEDURE DIVISION.
           MOVE 'IN' TO G-SHADOW.
           MOVE 'IN' TO G-VAL.
           MOVE 'IN' TO G-TWO.
           ADD 10 TO G-PART OF G-GRP.
           IF G-PART-DONE MOVE 'Y' TO G-FLAG END-IF.
           GOBACK.
       END PROGRAM INNER.
       END PROGRAM MIDDLE.
       END PROGRAM OUTER.
"""


def _working_storage(
    linked: LinkedProgram, program: str, provider: RealFileIOProvider
) -> dict[str, bytes]:
    entry = linked.entry_func_label
    vm = run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=50_000,
        initial_vm=initial_vm_state(io_provider=provider),
        builtins=core_builtins(),
        io_provider=provider,
    )
    region = ws_region(vm, program)
    return {
        name: bytes(region[p.offset : p.offset + p.length])
        for name, p in field_positions(declarations_of(linked, program)).items()
    }


def _ebcdic(text: str) -> bytes:
    return text.encode("cp037")


@covers(CobolFeature.GLOBAL_DATA, CobolFeature.NESTED_PROGRAMS)
def test_a_contained_program_reaches_the_nearest_global_declaration_of_a_name(
    tmp_path,
):
    linked = compile_cobol(_DATA, parser=make_cobol_parser(), work_dir=tmp_path)
    provider = RealFileIOProvider(base_dir=tmp_path)

    assert (
        _working_storage(linked, "OUTER", provider),
        _working_storage(linked, "MIDDLE", provider),
    ) == (
        {
            "G-VAL": _ebcdic("OU"),
            "G-TWO": _ebcdic("IN"),
            "G-GRP": _ebcdic("0017"),
            "G-PART": _ebcdic("0017"),
            "O-SEEN": _ebcdic("Y"),
            "G-SHADOW": _ebcdic("OU"),
            "G-FLAG": _ebcdic("Y"),
        },
        {"G-VAL": _ebcdic("IN"), "G-TWO": _ebcdic("MI")},
    )


_RECORD_AREA = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. KEEPER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  K-SEEN  PIC X(4) VALUE SPACES.
       PROCEDURE DIVISION.
           CALL 'KEEPER-1' USING K-SEEN.
           CALL 'KEEPER-1' USING K-SEEN.
           STOP RUN.
       END PROGRAM KEEPER.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. KEEPER-1.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT KEPT-FILE ASSIGN TO KEPTDD.
       DATA DIVISION.
       FILE SECTION.
       FD  KEPT-FILE.
       01  KEPT-REC  PIC X(4).
       LINKAGE SECTION.
       01  LK-SEEN   PIC X(4).
       PROCEDURE DIVISION USING LK-SEEN.
           MOVE KEPT-REC TO LK-SEEN.
           MOVE 'KEPT' TO KEPT-REC.
           GOBACK.
       END PROGRAM KEEPER-1.
"""


@covers(CobolFeature.SECTION_FILE)
def test_a_record_area_keeps_its_contents_from_one_call_to_the_next(tmp_path):
    linked = compile_cobol(_RECORD_AREA, parser=make_cobol_parser(), work_dir=tmp_path)

    assert _working_storage(
        linked, "KEEPER", RealFileIOProvider(base_dir=tmp_path)
    ) == {"K-SEEN": _ebcdic("KEPT")}
