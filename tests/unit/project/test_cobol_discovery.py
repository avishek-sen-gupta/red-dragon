"""discover_callee_programs: the shell step that turns a main program and ordered
search directories into the list of programs to compile."""

import itertools
from pathlib import Path

from interpreter.project.cobol_discovery import discover_callee_programs
from interpreter.project.source_file import SourceFile
from tests.covers import NotLanguageFeature, covers


def _program(program_id: str, *calls: str) -> bytes:
    call_lines = "".join(f"           CALL '{c}'.\n" for c in calls)
    return (
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {program_id}.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-NAME PIC X(8) VALUE 'DYNAMIC'.\n"
        "       PROCEDURE DIVISION.\n"
        f"{call_lines}"
        "           CALL WS-NAME.\n"
        "           GOBACK.\n"
    ).encode()


def _exit_program(source: str) -> str:
    return source.replace("GOBACK", "EXIT PROGRAM")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_discovery_follows_static_calls_through_ordered_directories(tmp_path: Path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "MID.cbl").write_bytes(_program("MID", "LEAF"))
    (second / "MID.cbl").write_bytes(_program("SHADOWED"))
    (second / "LEAF.cbl").write_bytes(_program("LEAF"))
    (second / "DYNAMIC.cbl").write_bytes(_program("DYNAMIC"))

    found = discover_callee_programs(
        _program("MAIN", "MID"), (first, second), _exit_program
    )

    assert {f.path.name: f for f in found} == {
        "LEAF.cbl": SourceFile(
            (second / "LEAF.cbl").resolve(),
            _program("LEAF").replace(b"GOBACK", b"EXIT PROGRAM"),
        ),
        "MID.cbl": SourceFile(
            (first / "MID.cbl").resolve(),
            _program("MID", "LEAF").replace(b"GOBACK", b"EXIT PROGRAM"),
        ),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_discovery_without_search_directories_finds_nothing():
    assert discover_callee_programs(_program("MAIN", "MID"), ()) == ()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_discovery_follows_a_call_chain_longer_than_the_recursion_limit(
    tmp_path: Path,
):
    names = tuple(f"P{i:05d}" for i in range(1200))
    for name, callee in itertools.pairwise(names):
        (tmp_path / f"{name}.cbl").write_bytes(_program(name, callee))
    (tmp_path / f"{names[-1]}.cbl").write_bytes(_program(names[-1]))

    found = discover_callee_programs(_program("MAIN", names[0]), (tmp_path,))

    assert tuple(f.path.stem for f in found) == names
