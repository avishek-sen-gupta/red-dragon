"""The lowered IR reports the I-O statuses that depend on a file's ACCESS MODE and on
its RELATIVE KEY's size: 21, 43 on a keyed file, and 14."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.unit.cobol.file_status_program import FileProgram, Step

_INDEXED = FileProgram(
    selects=(
        "    SELECT IX ASSIGN TO IXDD ORGANIZATION INDEXED",
        "        ACCESS SEQUENTIAL RECORD KEY IX-KEY FILE STATUS IS FS-IX.",
        "    SELECT IR ASSIGN TO IRDD ORGANIZATION INDEXED",
        "        ACCESS RANDOM RECORD KEY IR-KEY FILE STATUS IS FS-IR.",
    ),
    fds=(
        "FD  IX.",
        "01  IX-REC.",
        "    05  FILLER PIC X.",
        "    05  IX-KEY PIC XX.",
        "    05  FILLER PIC X.",
        "FD  IR.",
        "01  IR-REC.",
        "    05  FILLER PIC X.",
        "    05  IR-KEY PIC XX.",
        "    05  FILLER PIC X.",
    ),
    working_storage=("01  FS-IX PIC XX.", "01  FS-IR PIC XX."),
    shared={"IR": "ix.dat"},
)
_RELATIVE = FileProgram(
    selects=(
        "    SELECT RL ASSIGN TO RLDD ORGANIZATION RELATIVE",
        "        ACCESS MODE IS SEQUENTIAL RELATIVE KEY IS RL-NO",
        "        FILE STATUS IS FS-RL.",
    ),
    fds=("FD  RL.", "01  RL-REC PIC X."),
    working_storage=(
        "01  FS-RL PIC XX.",
        "01  RL-NO PIC 9.",
        "01  NO-SEEN PIC 99.",
    ),
)


def _ix(statement: str) -> Step:
    return Step(statement, ("FS-IX",))


@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
@covers(CobolFeature.DELETE_RECORD)
def test_sequential_access_to_an_indexed_file_follows_its_prime_key(
    tmp_path: Path,
) -> None:
    statuses = _INDEXED.statuses(
        tmp_path,
        (
            _ix("OPEN OUTPUT IX."),
            *(
                _ix(f"MOVE '{record}' TO IX-REC WRITE IX-REC.")
                for record in ("A10A", "B20B", "C15C", "D20D", "E30E")
            ),
            _ix("CLOSE IX."),
            _ix("OPEN I-O IX."),
            _ix("MOVE 'X10X' TO IX-REC REWRITE IX-REC."),
            _ix("READ IX."),
            _ix("MOVE 'X20X' TO IX-REC REWRITE IX-REC."),
            _ix("DELETE IX."),
            _ix("READ IX."),
            _ix("MOVE 'Y20Y' TO IX-REC REWRITE IX-REC."),
            _ix("CLOSE IX."),
            Step("OPEN I-O IR.", ("FS-IR",)),
            Step("MOVE 'Z30Z' TO IR-REC REWRITE IR-REC.", ("FS-IR",)),
            Step("CLOSE IR.", ("FS-IR",)),
        ),
    )
    assert (statuses, (tmp_path / "ix.dat").read_bytes()) == (
        [
            "00",
            "00",
            "00",
            "21",
            "22",
            "00",
            "00",
            "00",
            "43",
            "00",
            "21",
            "43",
            "00",
            "00",
            "00",
            "00",
            "00",
            "00",
        ],
        "A10AY20YZ30Z".encode("cp037"),
    )


@covers(CobolFeature.READ)
def test_a_sequential_read_past_the_relative_keys_size_is_status_14(
    tmp_path: Path,
) -> None:
    statuses = _RELATIVE.statuses(
        tmp_path,
        (
            Step("OPEN OUTPUT RL.", ("FS-RL",)),
            *(
                Step(f"MOVE '{record}' TO RL-REC WRITE RL-REC.", ("FS-RL",))
                for record in "ABCDEFGHIJK"
            ),
            Step("CLOSE RL.", ("FS-RL",)),
            Step("OPEN INPUT RL.", ("FS-RL",)),
            *(
                Step("READ RL MOVE RL-NO TO NO-SEEN.", ("FS-RL", "NO-SEEN"))
                for _ in range(11)
            ),
        ),
    )
    assert statuses == ["00"] * 14 + [
        *(status for n in range(1, 10) for status in ("00", f"0{n}")),
        "14",
        "09",
        "46",
        "09",
    ]
