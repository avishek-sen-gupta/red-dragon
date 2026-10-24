# pyright: standard
"""HLASM compiled to unit files, linked and run through the shared linker."""

import logging
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hlasm_asg.assembly_clock import AssemblyClock
from hlasm_asg.assembly_input import AssemblyInput
from hlasm_asg.assembly_inputs import AssemblyInputs
from hlasm_asg.hlasm_ast_parser import HlasmAstParser
from hlasm_asg.hlasm_bridge_not_found import HlasmBridgeNotFound
from hlasm_asg.hlasm_bridge_parser import (
    BRIDGE_ENV_VAR,
    HlasmBridgeParser,
    bridge_executable,
    make_hlasm_parser,
    resolve_bridge,
)
from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.missing_syslib_directory import MissingSyslibDirectory
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.real_subprocess_runner import RealSubprocessRunner
from interpreter.constants import Language
from interpreter.project.hlasm_compile import (
    HLASM_FRONTEND_LOGGER,
    compile_hlasm,
    lower_hlasm_program,
)
from interpreter.project.hlasm_compile_options import HlasmCompileOptions
from interpreter.project.types import LinkedProgram
from interpreter.run import run
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import (
    MAX_STEPS,
    HlasmRun,
    hlasm_run_of,
    run_hlasm,
)

RETURNS_SEVEN = (
    "HELLO    CSECT\n"
    "         LA    15,7\n"
    "         BR    14\n"
    "         END   HELLO\n"
)
SEVEN = RETURNS_SEVEN.encode("utf-8")
REPO_ROOT = Path(__file__).resolve().parents[3]
AN_HOUR_AHEAD = timezone(timedelta(hours=1))


@dataclass(frozen=True)
class _FixedClock(AssemblyClock):
    at: datetime

    def now(self) -> datetime:
        return self.at


AT_HALF_PAST_MIDNIGHT = _FixedClock(
    datetime(2026, 1, 2, 0, 30, 15, 123456, tzinfo=AN_HOUR_AHEAD)
)


@pytest.fixture
def syslib(tmp_path: Path) -> Path:
    directory = tmp_path / "lib"
    directory.mkdir()
    return directory


def _artifacts(work_dir: Path) -> dict[str, int]:
    return {p.name: p.stat().st_mtime_ns for p in work_dir.iterdir()}


def _kinds(work_dir: Path) -> list[str]:
    return sorted(p.name.split(".", 1)[1] for p in work_dir.iterdir())


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_returns_r15_as_return_code():
    assert run_hlasm(RETURNS_SEVEN) == HlasmRun(return_code=7, abend="", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_enters_hlasm_at_its_entry_point():
    vm = run(RETURNS_SEVEN, language=Language.HLASM, max_steps=MAX_STEPS)

    assert hlasm_run_of(vm, "") == HlasmRun(return_code=7, abend="", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_entry_defaults_to_first_csect():
    source = (
        "FIRST    CSECT\n"
        "         LA    15,7\n"
        "         BR    14\n"
        "SECOND   CSECT\n"
        "         LA    15,8\n"
        "         BR    14\n"
        "         END\n"
    )

    assert run_hlasm(source) == HlasmRun(return_code=7, abend="", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_second_compile_reuses_unit_files(tmp_path: Path, syslib: Path):
    work_dir = tmp_path / "work"

    compile_hlasm(SEVEN, parser=make_hlasm_parser(), work_dir=work_dir)
    first = _artifacts(work_dir)
    compile_hlasm(SEVEN, parser=make_hlasm_parser(), work_dir=work_dir)
    second = _artifacts(work_dir)
    lowered = lower_hlasm_program(SEVEN, parser=make_hlasm_parser(), work_dir=work_dir)
    compile_hlasm(SEVEN, parser=make_hlasm_parser([syslib]), work_dir=work_dir)

    assert second == first
    assert [p.name for p in lowered] == [n for n in first if n.endswith(".unit.json")]
    assert _kinds(work_dir) == [
        "ast.json",
        "ast.json",
        "linked.json",
        "linked.json",
        "unit.json",
        "unit.json",
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_balr_and_br_round_trip():
    source = (
        "MAIN     CSECT\n"
        "         LR    11,15\n"
        "         USING MAIN,11\n"
        "         LR    12,14\n"
        "         LA    15,SUB\n"
        "         BALR  14,15\n"
        "         LR    14,12\n"
        "         BR    14\n"
        "SUB      LA    15,9\n"
        "         BR    14\n"
        "         END   MAIN\n"
    )

    assert run_hlasm(source) == HlasmRun(return_code=9, abend="", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_wild_branch_abends_s0c1():
    source = (
        "WILD     CSECT\n"
        "         LA    1,4095\n"
        "         BR    1\n"
        "         END   WILD\n"
    )

    assert run_hlasm(source) == HlasmRun(return_code=0, abend="S0C1", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_assembly_inputs_and_the_clock_reach_the_program():
    source = (
        "         MACRO\n"
        "         SHOW\n"
        "         WTO   '&SYSCLOCK &SYSIN_DSN &SYSIN_MEMBER &SYSSEQF'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         WTO   '&SYSPARM &SYSJOB &SYSSTEP'\n"
        "         WTO   '&SYSDATE &SYSDATC &SYSTIME'\n"
        "         SHOW" + " " * 59 + "SEQ00010\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n"
    )
    options = HlasmCompileOptions(
        names={
            AssemblyInput.SYSPARM: "DEBUG",
            AssemblyInput.SYSJOB: "JOB1",
            AssemblyInput.SYSSTEP: "STEP1",
            AssemblyInput.SYSIN_DSN: "MY.SOURCE",
            AssemblyInput.SYSIN_MEMBER: "MAIN",
        },
        clock=AT_HALF_PAST_MIDNIGHT,
    )

    assert run_hlasm(source, options) == HlasmRun(
        0,
        "",
        "DEBUG JOB1 STEP1\n"
        "01/02/26 20260102 00.30\n"
        "2026-01-01 23:30:15.123456 MY.SOURCE MAIN SEQ00010\n",
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_assembly_input_not_given_is_refused():
    source = "MAIN     CSECT\n         WTO   '&SYSJOB'\n         END   MAIN\n"

    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(source)

    assert [(d.code, d.line, d.message) for d in refused.value.diagnostics] == [
        ("E010", 2, "Unknown variable: SYSJOB")
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_unsupplied_sysparm_is_the_null_string():
    source = (
        "MAIN     CSECT\n"
        "         WTO   'P=&SYSPARM'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n"
    )

    assert run_hlasm(source) == HlasmRun(0, "", "P=\n")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_missing_syslib_directory_is_refused(tmp_path: Path):
    missing = tmp_path / "no-such-lib"

    with pytest.raises(MissingSyslibDirectory) as from_compile:
        compile_hlasm(SEVEN, parser=make_hlasm_parser([missing]))
    with pytest.raises(MissingSyslibDirectory) as from_run:
        run(RETURNS_SEVEN, language=Language.HLASM, copybook_dirs=[missing])

    assert (from_compile.value.directory, from_run.value.directory) == (
        missing,
        missing,
    )
    assert str(from_run.value) == f"SYSLIB directory {missing} does not exist"


def _units(work_dir: Path) -> int:
    return sum(1 for p in work_dir.iterdir() if p.name.endswith(".unit.json"))


@pytest.fixture
def wrapped_bridge(tmp_path: Path, syslib: Path) -> HlasmBridgeParser:
    wrapper = tmp_path / "bridge"
    wrapper.write_text(f'#!/bin/sh\nexec "{bridge_executable()}" "$@"\n')
    wrapper.chmod(0o755)
    return HlasmBridgeParser(RealSubprocessRunner(), str(wrapper), [syslib])


def _units_after(
    work_dir: Path, parser: HlasmBridgeParser, options: HlasmCompileOptions
) -> int:
    compile_hlasm(SEVEN, parser=parser, options=options, work_dir=work_dir)
    return _units(work_dir)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unit_reuse_follows_inputs_syslib_members_and_bridge_but_not_the_clock(
    tmp_path: Path, syslib: Path, wrapped_bridge: HlasmBridgeParser
):
    work = tmp_path / "work"
    parser = make_hlasm_parser([syslib])
    later = _FixedClock(datetime(2027, 6, 1, 12, 0, tzinfo=AN_HOUR_AHEAD))
    parm = HlasmCompileOptions({AssemblyInput.SYSPARM: "X"}, AT_HALF_PAST_MIDNIGHT)
    (syslib / "GREET.mac").write_bytes(
        b"         MACRO\n         GREET\n         MEND\n"
    )

    before_edit = (
        _units_after(work, parser, HlasmCompileOptions(clock=AT_HALF_PAST_MIDNIGHT)),
        _units_after(work, parser, HlasmCompileOptions(clock=later)),
        _units_after(work, parser, parm),
    )
    (syslib / "GREET.mac").write_bytes(
        b"         MACRO\n         GREET\n         LA    1,1\n         MEND\n"
    )
    after_edit = (
        _units_after(work, parser, parm),
        _units_after(work, wrapped_bridge, parm),
    )

    assert before_edit + after_edit == (1, 1, 2, 3, 4)


def _assemble_elsewhere(tmp_path: Path, bridge: Mapping[str, str]) -> int:
    script = tmp_path / "assemble.py"
    script.write_text(
        "from pathlib import Path\n"
        "from hlasm_asg.hlasm_bridge_parser import make_hlasm_parser\n"
        "from interpreter.project.hlasm_compile import compile_hlasm\n"
        f"compile_hlasm({SEVEN!r}, parser=make_hlasm_parser(), work_dir=Path('work'))\n"
    )
    env = {
        **{k: v for k, v in os.environ.items() if k != BRIDGE_ENV_VAR},
        "PYTHONPATH": str(REPO_ROOT),
        **bridge,
    }

    ran = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, env=env, capture_output=True
    )

    assert (ran.returncode, ran.stderr) == (0, b"")
    return _units(tmp_path / "work")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_bridge_is_found_from_any_working_directory(tmp_path: Path):
    assert _assemble_elsewhere(tmp_path, {}) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_bridge_named_without_a_path_is_found_on_path(tmp_path: Path):
    bridge = Path(bridge_executable())
    on_path = {
        BRIDGE_ENV_VAR: bridge.name,
        "PATH": f"{bridge.parent}{os.pathsep}{os.environ['PATH']}",
    }

    with pytest.raises(HlasmBridgeNotFound) as missing:
        resolve_bridge("no-such-hlasm-bridge")

    assert _assemble_elsewhere(tmp_path, on_path) == 1
    assert str(missing.value) == "hlasm_ast_bridge not found: no-such-hlasm-bridge"


CAREFUL_MACRO = (
    b"         MACRO\n"
    b"         CAREFUL\n"
    b"         MNOTE 4,'MIND THE GAP'\n"
    b"         MNOTE 0,'ALL CLEAR'\n"
    b"         MNOTE *,'ASIDE'\n"
    b"         MNOTE 2,BARE\n"
    b"         MEND\n"
)
WARNED = (
    b"MAIN     CSECT\n"
    b"         CAREFUL\n"
    b"         SR    15,15\n"
    b"         BR    14\n"
    b"BIG      DC    2EB'1E39'\n"
    b"         END   MAIN\n"
)


class _AssemblyNotExpected(Exception):
    pass


@dataclass(frozen=True)
class _CachedOnly(HlasmAstParser):
    libraries: tuple[Path, ...]
    bridge: str

    @property
    def syslib(self) -> tuple[Path, ...]:
        return self.libraries

    @property
    def identity(self) -> str:
        return self.bridge

    def parse_to_file(
        self, source: bytes, source_name: str, out_path: Path, inputs: AssemblyInputs
    ) -> Path:
        raise _AssemblyNotExpected(source_name)

    def read(self, path: Path) -> HlasmProgram:
        raise _AssemblyNotExpected(str(path))


def _logged(
    caplog: pytest.LogCaptureFixture,
    step: Callable[[], LinkedProgram | tuple[Path, ...]],
) -> list[tuple[int, str]]:
    start = len(caplog.records)
    step()
    return [(r.levelno, r.getMessage()) for r in caplog.records[start:]]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_warnings_are_logged_and_logged_again_from_a_reused_unit(
    tmp_path: Path, syslib: Path, caplog: pytest.LogCaptureFixture
):
    (syslib / "CAREFUL.mac").write_bytes(CAREFUL_MACRO)
    work = tmp_path / "work"
    caplog.set_level(logging.INFO, logger=HLASM_FRONTEND_LOGGER)
    parser = make_hlasm_parser([syslib])
    cached = _CachedOnly(parser.syslib, parser.identity)

    first = _logged(caplog, lambda: compile_hlasm(WARNED, parser=parser, work_dir=work))
    reused = _logged(
        caplog, lambda: compile_hlasm(WARNED, parser=cached, work_dir=work)
    )
    lowered = _logged(
        caplog, lambda: lower_hlasm_program(WARNED, parser=cached, work_dir=work)
    )

    assert first == [
        (
            logging.WARNING,
            "CAREFUL:3: MNOTE 4,MIND THE GAP (called from __main__.asm:2)",
        ),
        (logging.INFO, "CAREFUL:4: MNOTE 0,ALL CLEAR (called from __main__.asm:2)"),
        (logging.INFO, "CAREFUL:5: MNOTE *,ASIDE (called from __main__.asm:2)"),
        (
            logging.WARNING,
            "CAREFUL:6: A300 Warning at MNOTE instruction: operand not properly"
            " enclosed in quotes (called from __main__.asm:2)",
        ),
        (logging.INFO, "CAREFUL:6: MNOTE 2,BARE (called from __main__.asm:2)"),
        (logging.WARNING, "__main__.asm:5: EB'1E39' overflow"),
    ]
    assert (reused, lowered, _units(work)) == (first, first, 1)
