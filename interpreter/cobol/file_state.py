"""The variables holding the run-time state of a file connector, one program's own or, for
an EXTERNAL file, the run unit's: its open mode,
whether it was closed WITH LOCK, where its position indicator stands, whether it is an
OPTIONAL file opened INPUT while absent, the prime key of its last record read or
written, and which verbs its open mode refuses."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.asg_types import CobolASG
from interpreter.cobol.global_names import file_owner
from interpreter.cobol.program_object import program_name
from interpreter.var_name import VarName


@dataclass(frozen=True)
class FileState:
    mode: VarName
    locked: VarName
    position: VarName
    absent: VarName
    last_key: VarName
    read_refused: VarName
    write_refused: VarName
    update_refused: VarName


def file_state(program: str, file_name: str) -> FileState:
    return _state(f"__cobol_file_{program}_{file_name.upper()}")


def external_file_state(file_name: str) -> FileState:
    """The state of an EXTERNAL file's connector, one per run unit."""
    return _state(f"__cobol_external_file_{file_name.upper()}")


def file_state_of(asg: CobolASG, file_name: str) -> FileState:
    """The state the program's verbs on ``file_name`` act on: the run unit's for an
    EXTERNAL file, else that of the program whose SELECT declares it, the program
    itself or the containing program it is GLOBAL in."""
    owner = file_owner(asg, file_name)
    if file_name.upper() in owner.external_file_names():
        return external_file_state(file_name)
    return file_state(program_name(owner), file_name)


def _state(prefix: str) -> FileState:
    return FileState(
        mode=VarName(f"{prefix}_mode"),
        locked=VarName(f"{prefix}_locked"),
        position=VarName(f"{prefix}_position"),
        absent=VarName(f"{prefix}_absent"),
        last_key=VarName(f"{prefix}_last_key"),
        read_refused=VarName(f"{prefix}_read_refused"),
        write_refused=VarName(f"{prefix}_write_refused"),
        update_refused=VarName(f"{prefix}_update_refused"),
    )
