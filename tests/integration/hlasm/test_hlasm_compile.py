# pyright: standard
"""HLASM compiled to unit files, linked and run through the shared linker."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hlasm_asg.hlasm_bridge_parser import BRIDGE_ENV_VAR, make_hlasm_parser
from interpreter.constants import Language
from interpreter.project.hlasm_compile import compile_hlasm, lower_hlasm_program
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
def test_the_bridge_is_found_from_any_working_directory(tmp_path: Path):
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
    }

    ran = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, env=env, capture_output=True
    )

    assert (ran.returncode, ran.stderr) == (0, b"")
    assert (
        sum(1 for p in (tmp_path / "work").iterdir() if p.name.endswith(".unit.json"))
        == 1
    )
