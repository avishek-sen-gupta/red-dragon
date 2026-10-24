# pyright: standard
"""Control across modules in RedDragon and in z390, whose linker autolinks the other modules' objects from SYSOBJ: a linking call that returns through R14, and a return that skips a level."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import far_branch_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390


def _both(
    z390: Z390Runner, tmp_path: Path, main: str, others: Mapping[str, str]
) -> tuple[int, int]:
    tmp_path.mkdir()
    _ = [z390.assemble_object(name, text, tmp_path) for name, text in others.items()]
    z390_run = z390.run(main, tmp_path, (f"SYSOBJ({tmp_path})",))
    ours = run_hlasm_machine(
        main, tuple(programs.module(name, text) for name, text in others.items())
    ).run
    assert (ours.abend, z390_run.abend) == ("", "")
    return ours.return_code, z390_run.return_code


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_call_and_a_return_that_skips_a_level_agree_with_z390(
    z390: Z390Runner, tmp_path: Path
):
    called = _both(z390, tmp_path / "call", programs.CALLER, {"SUB": programs.CALLEE})
    skipped = _both(
        z390,
        tmp_path / "skip",
        programs.SKIPPER,
        {"B": programs.MIDDLE, "C": programs.INNER},
    )

    assert (called, skipped) == ((142, 142), (77, 77))
