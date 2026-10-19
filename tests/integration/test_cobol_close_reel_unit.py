"""CLOSE REEL/UNIT, FOR REMOVAL and NO REWIND on a file that is not on a reel or unit
medium (red-dragon-sl30.94). Every file red-dragon reaches is such a file.

IBM Enterprise COBOL LR, file status key 07: "For a CLOSE statement with the NO
REWIND, REEL/UNIT, or FOR REMOVAL phrase or for an OPEN statement with the NO REWIND
phrase, the referenced file was on a non-reel/unit medium." Effect of CLOSE statement
on file types, code F, for a non-reel/unit file: "Execution of the CLOSE statement is
considered successful. The file remains in the open mode and no action takes place
except that the value of the I-O status associated with the file is updated."
"""

from pathlib import Path

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.layout_data import field_positions
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.cobol.run_inputs import RunInputs
from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.run import declarations_of, initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
from tests.covers import covers
from tests.integration.cobol_helpers import ws_region

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLOSEREEL.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SEQ-FILE ASSIGN TO SEQDD
               FILE STATUS IS FS.
       DATA DIVISION.
       FILE SECTION.
       FD  SEQ-FILE.
       01  SEQ-REC      PIC X(4).
       WORKING-STORAGE SECTION.
       01  FS           PIC XX.
       01  STATUSES.
           05  ST       PIC XX OCCURS 11 TIMES.
       01  READ-BACK    PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
           CLOSE SEQ-FILE REEL.
           MOVE FS TO ST(1).
           OPEN OUTPUT SEQ-FILE.
           MOVE 'AAAA' TO SEQ-REC.
           WRITE SEQ-REC.
           CLOSE SEQ-FILE REEL.
           MOVE FS TO ST(2).
           MOVE 'BBBB' TO SEQ-REC.
           WRITE SEQ-REC.
           MOVE FS TO ST(3).
           CLOSE SEQ-FILE UNIT FOR REMOVAL.
           MOVE FS TO ST(4).
           CLOSE SEQ-FILE.
           MOVE FS TO ST(5).
           OPEN INPUT SEQ-FILE.
           CLOSE SEQ-FILE UNIT WITH NO REWIND.
           MOVE FS TO ST(6).
           READ SEQ-FILE.
           MOVE FS TO ST(7).
           MOVE SEQ-REC TO READ-BACK(1:4).
           READ SEQ-FILE.
           MOVE SEQ-REC TO READ-BACK(5:4).
           CLOSE SEQ-FILE WITH NO REWIND.
           MOVE FS TO ST(8).
           CLOSE SEQ-FILE.
           MOVE FS TO ST(9).
           OPEN INPUT SEQ-FILE.
           MOVE FS TO ST(10).
           CLOSE SEQ-FILE.
           MOVE FS TO ST(11).
           STOP RUN.
"""


@covers(CobolFeature.CLOSE)
def test_close_reel_unit_leaves_a_non_reel_file_open_with_status_07(tmp_path: Path):
    """REEL/UNIT, with or without FOR REMOVAL or NO REWIND, leaves the file open,
    so WRITE and READ go on; NO REWIND alone closes it. Each phrase reports 07; on
    a file that is not open, CLOSE REEL is still refused with 42."""
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        inputs=RunInputs(
            file_control=[], path_overrides={"SEQ-FILE": tmp_path / "seq.dat"}
        ),
    )
    linked = compile_cobol(_SOURCE, parser=make_cobol_parser(), work_dir=tmp_path)
    entry = linked.entry_func_label
    vm = run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=200_000,
        initial_vm=initial_vm_state(io_provider=provider),
        builtins=core_builtins(),
        io_provider=provider,
    )
    region = ws_region(vm, "CLOSEREEL")
    fields = field_positions(declarations_of(linked, "CLOSEREEL"))
    statuses = fields["STATUSES"]
    read_back = fields["READ-BACK"]

    assert (
        [
            bytes(region[statuses.offset + 2 * n : statuses.offset + 2 * n + 2])
            for n in range(11)
        ],
        bytes(region[read_back.offset : read_back.offset + read_back.length]),
    ) == (
        [
            _ebcdic(s)
            for s in ("42", "07", "00", "07", "00", "07", "00", "07", "42", "00", "00")
        ],
        _ebcdic("AAAABBBB"),
    )


def _ebcdic(text: str) -> bytes:
    return bytes(EbcdicTable.ascii_to_ebcdic(text.encode()))
