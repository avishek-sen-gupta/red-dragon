# pyright: standard
"""Runs a program under z390 and reads its LOG: stdout is the run's lines minus z390's own EZ390 messages and register dumps."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hlasm_asg.subprocess_runner import SubprocessRunner
from tests.integration.hlasm.hlasm_helpers import NO_RETURN_CODE, HlasmRun
from tests.z390.z390_assembly_failed import Z390AssemblyFailed

PROGRAM = "PROG"
NO_ABEND = ""
RUN_START = re.compile(r"^EZ390I options = ")
RUN_END = re.compile(r"^EZ390I instructions/sec")
ENDED = re.compile(r" EZ390 ENDED +RC= *(\d+) ")
ABEND = re.compile(r"^EZ390E error +\d+ program aborting due to abend (\S+)$")
Z390_MESSAGE = re.compile(r"^(EZ390|\s*R[0-9A-F]-R[0-9A-F] )")


def _run_lines(log: Sequence[str]) -> Sequence[str]:
    start = next(i for i, line in enumerate(log) if RUN_START.match(line))
    end = next(i for i, line in enumerate(log) if RUN_END.match(line))
    return log[start + 1 : end]


def _ended_rc(log: Sequence[str]) -> int:
    return next(int(m.group(1)) for line in log if (m := ENDED.search(line)))


def _abend(lines: Sequence[str]) -> str:
    return next((m.group(1) for line in lines if (m := ABEND.match(line))), NO_ABEND)


def _stdout(lines: Sequence[str]) -> str:
    return "".join(f"{line}\n" for line in lines if not Z390_MESSAGE.match(line))


def _return_code(ended_rc: int, abend: str) -> int:
    match abend:
        case "":
            return ended_rc
        case _:
            return NO_RETURN_CODE


def hlasm_run_of_log(log: Sequence[str]) -> HlasmRun:
    lines = _run_lines(log)
    abend = _abend(lines)
    return HlasmRun(_return_code(_ended_rc(log), abend), abend, _stdout(lines))


@dataclass(frozen=True)
class Z390Runner:
    """Assembles, links and executes with z390's asmlg against z390's own macro library."""

    home: Path
    runner: SubprocessRunner

    def run(self, source: str, tmp: Path) -> HlasmRun:
        program = tmp / PROGRAM
        program.with_suffix(".MLC").write_text(source, encoding="ascii")
        ran = self.runner.run([str(self.home / "bash" / "asmlg"), str(program)])
        log = program.with_suffix(".LOG")
        if not log.exists():
            err = program.with_suffix(".ERR").read_text(encoding="latin-1")
            raise Z390AssemblyFailed(log.name, ran.returncode, err)
        return hlasm_run_of_log(log.read_text(encoding="latin-1").splitlines())
