"""Runs a COBOL program of file statements through the lowering and the VM, recording the
FILE STATUS each statement leaves."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.record_io.run_inputs import RunInputs
from interpreter.run import run
from tests.integration.cobol_helpers import first_region, to_fixed

_STATUS_BYTES = 2
_MAX_STEPS = 200_000


@dataclass(frozen=True)
class Step:
    """One statement, its lines split at newlines, and the two-character items logged
    after it: its FILE STATUS item first."""

    statement: str
    logged: Sequence[str]


def _entries(steps: Sequence[Step]) -> int:
    return sum(len(step.logged) for step in steps)


def _firsts(steps: Sequence[Step]) -> list[int]:
    return [1 + _entries(steps[:n]) for n in range(len(steps))]


@dataclass(frozen=True)
class FileProgram:
    """The FILE-CONTROL entries, FD entries and WORKING-STORAGE items of a program
    whose procedure is a list of steps. A file is named after its SELECT, lower case,
    with suffix .dat, unless ``shared`` names the file it opens instead."""

    selects: Sequence[str]
    fds: Sequence[str]
    working_storage: Sequence[str] = ()
    shared: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def _lines(self, steps: Sequence[Step]) -> list[str]:
        return [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FSTEST.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            *self.selects,
            "DATA DIVISION.",
            "FILE SECTION.",
            *self.fds,
            "WORKING-STORAGE SECTION.",
            "01  STATUS-LOG.",
            f"    05  LOGGED PIC XX OCCURS {max(_entries(steps), 1)} TIMES.",
            *self.working_storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *(
                line
                for step, first in zip(steps, _firsts(steps), strict=True)
                for line in (
                    *(f"    {part}" for part in step.statement.split("\n")),
                    *(
                        f"    MOVE {item} TO LOGGED({first + n})."
                        for n, item in enumerate(step.logged)
                    ),
                )
            ),
            "    STOP RUN.",
        ]

    def statuses(self, tmp_path: Path, steps: Sequence[Step]) -> list[str]:
        vm = run(
            to_fixed(self._lines(steps)),
            language="cobol",
            io_provider=RealFileIOProvider(
                base_dir=tmp_path,
                inputs=RunInputs(
                    path_overrides={
                        name: tmp_path / file for name, file in self.shared.items()
                    }
                ),
            ),
            max_steps=_MAX_STEPS,
        )
        log = bytes(first_region(vm)[: _STATUS_BYTES * _entries(steps)]).decode("cp037")
        return [log[i : i + _STATUS_BYTES] for i in range(0, len(log), _STATUS_BYTES)]
