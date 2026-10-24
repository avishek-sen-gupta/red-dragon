# pyright: standard
"""Runs a program under z390 and reads its LOG: stdout is the run's lines minus z390's own EZ390 messages and register dumps; an abend's dump gives the registers and CC."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hlasm_asg.subprocess_runner import SubprocessRunner
from tests.integration.hlasm.hlasm_helpers import NO_RETURN_CODE
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_assembly_failed import Z390AssemblyFailed

PROGRAM = "PROG"
NO_ABEND = ""
RUN_START = re.compile(r"^EZ390I options = ")
RUN_END = re.compile(r"^EZ390I instructions/sec")
ENDED = re.compile(r" EZ390 ENDED +RC= *(\d+) ")
ABEND = re.compile(r"^EZ390E error +\d+ program aborting due to abend (\S+)$")
Z390_MESSAGE = re.compile(r"^(EZ390|\s*R[0-9A-F]-R[0-9A-F] )")
ABEND_PSW = re.compile(r" ABEND PSW=([0-9A-F]{8})(?:[0-9A-F]{8})? ")
REGISTER_DUMP = re.compile(r"^ R([0-9A-F])-R[0-9A-F] ((?:[0-9A-F]{16} ?){4})$")
PSW_CC_SHIFT = 12
CC_MASK = 0b11
HEX = 16


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


def _abend_cc(lines: Sequence[str]) -> int:
    psw = next(int(m.group(1), HEX) for line in lines if (m := ABEND_PSW.search(line)))
    return (psw >> PSW_CC_SHIFT) & CC_MASK


def _dumped_registers(line: str) -> dict[int, int]:
    match REGISTER_DUMP.match(line):
        case None:
            return {}
        case dump:
            first = int(dump.group(1), HEX)
            values = dump.group(2).split()
            return {first + i: int(value, HEX) for i, value in enumerate(values)}


def hlasm_machine_of_log(log: Sequence[str]) -> HlasmMachine:
    lines = _run_lines(log)
    gprs = {r: v for line in lines for r, v in _dumped_registers(line).items()}
    return HlasmMachine(hlasm_run_of_log(log), _abend_cc(lines), gprs)


@dataclass(frozen=True)
class Z390Runner:
    """Assembles, links and executes with z390's asmlg against z390's own macro library."""

    home: Path
    runner: SubprocessRunner

    def run(self, source: str, tmp: Path, options: Sequence[str] = ()) -> HlasmRun:
        return hlasm_run_of_log(self._log(source, tmp, options))

    def assemble_object(self, name: str, source: str, tmp: Path) -> Path:
        program = tmp / name
        program.with_suffix(".MLC").write_text(source, encoding="ascii")
        self.runner.run([str(self.home / "bash" / "asm"), str(program)])
        return program.with_suffix(".OBJ")

    def assemble_load_module(self, name: str, source: str, tmp: Path) -> Path:
        program = tmp / name
        program.with_suffix(".MLC").write_text(source, encoding="ascii")
        self.runner.run([str(self.home / "bash" / "asml"), str(program)])
        return program.with_suffix(".390")

    def run_machine(
        self, source: str, tmp: Path, environment: Mapping[str, str] = {}
    ) -> HlasmMachine:
        return hlasm_machine_of_log(self._log(source, tmp, (), environment))

    def _log(
        self,
        source: str,
        tmp: Path,
        options: Sequence[str] = (),
        environment: Mapping[str, str] = {},
    ) -> Sequence[str]:
        program = tmp / PROGRAM
        program.with_suffix(".MLC").write_text(source, encoding="ascii")
        settings = [f"{name}={value}" for name, value in environment.items()]
        ran = self.runner.run(
            [
                "env",
                *settings,
                str(self.home / "bash" / "asmlg"),
                str(program),
                *options,
            ]
        )
        log = program.with_suffix(".LOG")
        if not log.exists():
            err = program.with_suffix(".ERR").read_text(encoding="latin-1")
            raise Z390AssemblyFailed(log.name, ran.returncode, err)
        return log.read_text(encoding="latin-1").splitlines()
