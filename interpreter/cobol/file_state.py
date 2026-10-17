"""The variables holding one program's run-time state of one of its files: its open mode,
whether it was closed WITH LOCK, and where its position indicator stands."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.var_name import VarName


@dataclass(frozen=True)
class FileState:
    mode: VarName
    locked: VarName
    position: VarName


def file_state(program: str, file_name: str) -> FileState:
    prefix = f"__cobol_file_{program}_{file_name.upper()}"
    return FileState(
        mode=VarName(f"{prefix}_mode"),
        locked=VarName(f"{prefix}_locked"),
        position=VarName(f"{prefix}_position"),
    )
