"""A relative file is addressed by relative record number, given and returned as text;
the lowered IR refuses a WRITE below record 1 with 24."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import FileOrganization
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.io_provider import IOResult
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.record_io.access_result import AccessCondition
from interpreter.record_io.file_frame import FileFrame
from interpreter.record_io.prime_key import PrimeKey
from tests.covers import covers
from tests.unit.cobol.declared_files import opened
from tests.unit.cobol.file_status_program import FileProgram, Step

_REL = "RELATIVE"


def _seen(result: IOResult) -> tuple[AccessCondition, str, int]:
    return (result.condition, result.data or "", result.record_number)


_KEYED = FileProgram(
    selects=(
        "    SELECT RLF ASSIGN TO RLFDD ORGANIZATION RELATIVE",
        "        ACCESS DYNAMIC RELATIVE KEY RLF-NO FILE STATUS IS FS-R.",
    ),
    fds=("FD  RLF.", "01  RLF-REC PIC X(3)."),
    working_storage=(
        "01  FS-R PIC XX.",
        "01  RLF-NO PIC 9(4).",
        "01  SEEN PIC XX.",
    ),
)


def _at(number: int, statement: str) -> Step:
    return Step(f"MOVE {number} TO RLF-NO {statement}", ("FS-R",))


def _read_at(number: int) -> Step:
    return Step(
        f"MOVE {number} TO RLF-NO MOVE SPACES TO RLF-REC\nREAD RLF MOVE RLF-REC TO SEEN.",
        ("FS-R", "SEEN"),
    )


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
def test_keyed_verbs_address_the_record_number_they_are_given(tmp_path: Path) -> None:
    statuses = _KEYED.statuses(
        tmp_path,
        (
            Step("OPEN OUTPUT RLF.", ("FS-R",)),
            _at(1, "MOVE 'ONE' TO RLF-REC WRITE RLF-REC."),
            _at(3, "MOVE 'TWO' TO RLF-REC WRITE RLF-REC."),
            _at(3, "MOVE 'DUP' TO RLF-REC WRITE RLF-REC."),
            _at(0, "MOVE 'NIL' TO RLF-REC WRITE RLF-REC."),
            Step("CLOSE RLF.", ("FS-R",)),
            Step("OPEN I-O RLF.", ("FS-R",)),
            *(_read_at(n) for n in (0, 5, 2, 3)),
            _at(0, "MOVE 'NIL' TO RLF-REC REWRITE RLF-REC."),
            _at(1, "MOVE 'NEW' TO RLF-REC REWRITE RLF-REC."),
            _at(3, "DELETE RLF."),
            *(_read_at(n) for n in (1, 3)),
        ),
    )
    assert statuses == [
        "00",
        *("00", "00", "22", "24"),
        "00",
        "00",
        *("23", "  ", "23", "  ", "23", "  ", "00", "TW"),
        *("23", "00", "00"),
        *("00", "NE", "23", "  "),
    ]


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
def test_sequential_verbs_return_the_record_number_they_used(tmp_path: Path) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    opened(
        prov,
        "OUTPUT",
        FileFrame("F", FileOrganization(_REL), PrimeKey(0, 0), False, 3),
    )
    written = [prov._write_record("F", rec, "", "P").record_number for rec in "AB"]
    prov._close_file("F", "P")
    opened(
        prov,
        "EXTEND",
        FileFrame("F", FileOrganization(_REL), PrimeKey(0, 0), False, 3),
    )
    extended = prov._write_record("F", "C", "", "P").record_number
    prov._close_file("F", "P")
    opened(
        prov,
        "INPUT",
        FileFrame("F", FileOrganization(_REL), PrimeKey(0, 0), False, 3),
    )
    read = [_seen(prov._read_record("F", "", "P")) for _ in range(4)]
    assert (written, extended, read) == (
        [1, 2],
        3,
        [
            (AccessCondition.OK, "A  ", 1),
            (AccessCondition.OK, "B  ", 2),
            (AccessCondition.OK, "C  ", 3),
            (AccessCondition.END_OF_FILE, "", 0),
        ],
    )
