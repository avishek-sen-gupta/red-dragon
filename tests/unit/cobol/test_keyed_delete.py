"""DELETE removes the record its key names in random or dynamic access, and the
current record in sequential access (ANSI X3.23-1985 Relative and Indexed I-O
modules, DELETE statement)."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.unit.cobol.file_status_program import FileProgram, Step

_PROGRAM = FileProgram(
    selects=(
        "    SELECT IX ASSIGN TO IXDD ORGANIZATION INDEXED",
        "        ACCESS DYNAMIC RECORD KEY IX-KEY FILE STATUS IS FS-IX.",
        "    SELECT IQ ASSIGN TO IQDD ORGANIZATION INDEXED",
        "        ACCESS SEQUENTIAL RECORD KEY IQ-KEY FILE STATUS IS FS-IQ.",
        "    SELECT RL ASSIGN TO RLDD ORGANIZATION RELATIVE",
        "        ACCESS DYNAMIC RELATIVE KEY RL-NO FILE STATUS IS FS-RL.",
    ),
    fds=(
        "FD  IX.",
        "01  IX-REC.",
        "    05  IX-KEY PIC XX.",
        "    05  FILLER PIC XX.",
        "FD  IQ.",
        "01  IQ-REC.",
        "    05  IQ-KEY PIC XX.",
        "    05  FILLER PIC XX.",
        "FD  RL.",
        "01  RL-REC PIC X(4).",
    ),
    working_storage=(
        "01  FS-IX PIC XX.",
        "01  FS-IQ PIC XX.",
        "01  FS-RL PIC XX.",
        "01  RL-NO PIC 9.",
    ),
)


def _loaded(name: str, records: tuple[str, ...]) -> tuple[Step, ...]:
    status = (f"FS-{name}",)
    return (
        Step(f"OPEN OUTPUT {name}.", status),
        *(
            Step(
                f"MOVE {n} TO RL-NO MOVE '{r}' TO {name}-REC WRITE {name}-REC.",
                status,
            )
            for n, r in enumerate(records, start=1)
        ),
        Step(f"CLOSE {name}.", status),
        Step(f"OPEN I-O {name}.", status),
    )


@covers(CobolFeature.DELETE_RECORD)
def test_a_keyed_delete_needs_no_current_record(tmp_path: Path) -> None:
    statuses = _PROGRAM.statuses(
        tmp_path,
        (
            *_loaded("IX", ("01AA", "02BB", "03CC")),
            *_loaded("IQ", ("01AA", "02BB", "03CC")),
            *_loaded("RL", ("AAAA", "BBBB")),
            Step("MOVE '02' TO IX-KEY DELETE IX.", ("FS-IX",)),
            Step("MOVE '09' TO IX-KEY DELETE IX.", ("FS-IX",)),
            Step("DELETE IQ.", ("FS-IQ",)),
            Step("READ IQ.", ("FS-IQ",)),
            Step("DELETE IQ.", ("FS-IQ",)),
            Step("MOVE 2 TO RL-NO DELETE RL.", ("FS-RL",)),
            Step("CLOSE IX CLOSE IQ CLOSE RL.", ("FS-RL",)),
        ),
    )
    assert (
        statuses[-7:],
        (tmp_path / "ix.dat").read_bytes(),
        (tmp_path / "iq.dat").read_bytes(),
        (tmp_path / "rl.dat").read_bytes(),
    ) == (
        ["00", "23", "43", "00", "00", "00", "00"],
        "01AA03CC".encode("cp037"),
        "02BB03CC".encode("cp037"),
        b"\xff" + "AAAA".encode("cp037") + b"\x00" + "BBBB".encode("cp037"),
    )
