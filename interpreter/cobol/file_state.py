"""The variables holding one program's run-time state of one of its files: its open mode,
whether it was closed WITH LOCK, where its position indicator stands, whether it is an
OPTIONAL file opened INPUT while absent, the prime key of its last record read or
written, and which verbs its open mode refuses."""

from __future__ import annotations

from dataclasses import dataclass

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
    prefix = f"__cobol_file_{program}_{file_name.upper()}"
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
