"""CANCEL closes the cancelled program's open files (red-dragon-idkb).

IBM Enterprise COBOL LR, CANCEL statement: "A CANCEL statement closes all open files
that are associated with an internal file connector in the program named in an
explicit CANCEL statement. USE procedures associated with those files are not
executed."
"""

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.layout_data import field_positions
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.cobol.run_inputs import RunInputs
from interpreter.encoding.ebcdic_table import EbcdicTable
from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.run import declarations_of, initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
from tests.covers import covers
from tests.integration.cobol_helpers import ws_region

_SUBPROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. {name}.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT {name}-FILE ASSIGN TO {name}DD
               FILE STATUS IS OWN-FS.
       DATA DIVISION.
       FILE SECTION.
       FD  {name}-FILE.
       01  OWN-REC      PIC X(6).
       WORKING-STORAGE SECTION.
       01  OWN-FS       PIC XX.
       LINKAGE SECTION.
       01  LK-FS        PIC XX.
       PROCEDURE DIVISION USING LK-FS.
           OPEN OUTPUT {name}-FILE.
           MOVE OWN-FS TO LK-FS.
           MOVE 'REC-01' TO OWN-REC.
           WRITE OWN-REC.
           GOBACK.
       END PROGRAM {name}.
"""

_SOURCE = ("""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CANFILES.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  FS-1         PIC XX VALUE '**'.
       01  FS-2         PIC XX VALUE '**'.
       01  FS-3         PIC XX VALUE '**'.
       01  FS-4         PIC XX VALUE '**'.
       PROCEDURE DIVISION.
           CALL 'CANSUB' USING FS-1.
           CANCEL 'CANSUB'.
           CALL 'CANSUB' USING FS-2.
           CALL 'KEEPSUB' USING FS-3.
           CALL 'KEEPSUB' USING FS-4.
           STOP RUN.
       END PROGRAM CANFILES.
""" + _SUBPROGRAM.format(name="CANSUB") + _SUBPROGRAM.format(name="KEEPSUB")).encode()


@covers(CobolFeature.CANCEL, CobolFeature.OPEN, CobolFeature.WRITE)
def test_cancel_closes_the_files_the_cancelled_program_left_open(tmp_path: Path):
    """CANSUB leaves its file open and is cancelled, so its next OPEN succeeds.
    KEEPSUB is never cancelled, so its second OPEN finds its file still open
    (41)."""
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        inputs=RunInputs(
            file_control=[],
            path_overrides={
                "CANSUB-FILE": tmp_path / "cansub.dat",
                "KEEPSUB-FILE": tmp_path / "keepsub.dat",
            },
        ),
    )
    linked = compile_cobol(_SOURCE, parser=make_cobol_parser(), work_dir=tmp_path)
    entry = linked.entry_func_label
    vm = run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=100_000,
        initial_vm=initial_vm_state(io_provider=provider),
        builtins=core_builtins(),
        io_provider=provider,
    )
    region = ws_region(vm, "CANFILES")
    statuses = {
        name: bytes(region[p.offset : p.offset + p.length])
        for name, p in field_positions(declarations_of(linked, "CANFILES")).items()
    }

    assert statuses == {
        "FS-1": _ebcdic("00"),
        "FS-2": _ebcdic("00"),
        "FS-3": _ebcdic("00"),
        "FS-4": _ebcdic("41"),
    }


def _ebcdic(text: str) -> bytes:
    return bytes(EbcdicTable.ascii_to_ebcdic(text.encode()))
