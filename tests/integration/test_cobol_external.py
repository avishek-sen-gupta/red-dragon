"""EXTERNAL records and files are one storage area per run unit, shared by every
program that describes them by the same name (red-dragon-ljku.3).

IBM Enterprise COBOL LR, EXTERNAL clause: "An external data item can be referenced by
any program or method in the run unit that describes the data item"; for a file, "In a
run unit, there is only one representative of an external file." The FILE STATUS item
stays each program's own: an I-O statement updates the one its own program names.
"""

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.layout_data import field_positions
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.encoding.ebcdic_table import EbcdicTable
from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.project.types import LinkedProgram
from interpreter.record_io.run_inputs import RunInputs
from interpreter.run import declarations_of, initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
from tests.covers import covers
from tests.integration.cobol_helpers import ws_region

_DATA = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXTA.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-BEFORE   PIC X(4) VALUE 'MAIN'.
       01  SHARED-AREA IS EXTERNAL.
           05  SH-TEXT PIC X(4).
           05  SH-NUM  PIC 9(4).
       01  WS-COPY     PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
           MOVE 'ABCD' TO SH-TEXT.
           MOVE 12 TO SH-NUM.
           CALL 'EXTA-1'.
           MOVE SHARED-AREA TO WS-COPY.
           STOP RUN.
       END PROGRAM EXTA.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXTA-1.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  SUB-SEEN    PIC X(8) VALUE SPACES.
       01  SHARED-AREA PIC X(8) EXTERNAL.
       PROCEDURE DIVISION.
           MOVE SHARED-AREA TO SUB-SEEN.
           MOVE 'WXYZ0099' TO SHARED-AREA.
           GOBACK.
       END PROGRAM EXTA-1.
"""

_FILE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXTF.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SHARED-FILE ASSIGN TO SHAREDDD
               FILE STATUS IS MAIN-FS.
       DATA DIVISION.
       FILE SECTION.
       FD  SHARED-FILE IS EXTERNAL.
       01  MAIN-REC     PIC X(6).
       WORKING-STORAGE SECTION.
       01  MAIN-FS      PIC XX.
       01  SUB-FS       PIC XX VALUE '**'.
       01  FS-AFTER     PIC XX.
       01  READ-BACK    PIC X(6).
       PROCEDURE DIVISION.
           OPEN OUTPUT SHARED-FILE.
           MOVE 'REC-01' TO MAIN-REC.
           MOVE '<>' TO MAIN-FS.
           CALL 'EXTF-1' USING SUB-FS.
           MOVE MAIN-FS TO FS-AFTER.
           CLOSE SHARED-FILE.
           OPEN INPUT SHARED-FILE.
           READ SHARED-FILE INTO READ-BACK.
           CLOSE SHARED-FILE.
           STOP RUN.
       END PROGRAM EXTF.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXTF-1.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SHARED-FILE ASSIGN TO SHAREDDD
               FILE STATUS IS LK-FS.
       DATA DIVISION.
       FILE SECTION.
       FD  SHARED-FILE IS EXTERNAL.
       01  SUB-REC      PIC X(6).
       LINKAGE SECTION.
       01  LK-FS        PIC XX.
       PROCEDURE DIVISION USING LK-FS.
           WRITE SUB-REC.
           GOBACK.
       END PROGRAM EXTF-1.
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
    )
    region = ws_region(vm, program)
    return {
        name: bytes(region[p.offset : p.offset + p.length])
        for name, p in field_positions(declarations_of(linked, program)).items()
    }


def _ebcdic(text: str) -> bytes:
    return text.encode("cp037")


@covers(CobolFeature.EXTERNAL_DATA, CobolFeature.BATCHED_PROGRAMS)
def test_two_programs_describing_one_external_record_share_its_storage(tmp_path):
    linked = compile_cobol(_DATA, parser=make_cobol_parser(), work_dir=tmp_path)
    provider = RealFileIOProvider(base_dir=tmp_path)

    assert (
        _working_storage(linked, "EXTA", provider),
        _working_storage(linked, "EXTA-1", provider),
    ) == (
        {"WS-BEFORE": _ebcdic("MAIN"), "WS-COPY": _ebcdic("WXYZ0099")},
        {"SUB-SEEN": _ebcdic("ABCD0012")},
    )


@covers(CobolFeature.EXTERNAL_FILE, CobolFeature.BATCHED_PROGRAMS)
def test_an_external_file_shares_its_connector_and_record_area_but_not_its_status(
    tmp_path: Path,
):
    data_path = tmp_path / "shared.dat"
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        inputs=RunInputs(file_control=[], path_overrides={"SHARED-FILE": data_path}),
    )
    linked = compile_cobol(_FILE, parser=make_cobol_parser(), work_dir=tmp_path)

    assert (_working_storage(linked, "EXTF", provider), data_path.read_bytes()) == (
        {
            "MAIN-FS": _ebcdic("00"),
            "SUB-FS": _ebcdic("00"),
            "FS-AFTER": _ebcdic("<>"),
            "READ-BACK": _ebcdic("REC-01"),
        },
        bytes(EbcdicTable.ascii_to_ebcdic(b"REC-01")),
    )
