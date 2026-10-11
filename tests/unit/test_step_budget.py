"""A run that reaches its step budget before the program ends is BudgetExhausted."""

from __future__ import annotations

from pathlib import Path

from interpreter.constants import Language
from interpreter.ir import CodeLabel, Opcode
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.register import Register
from interpreter.run import (
    BudgetExhausted,
    Completed,
    initial_vm_state,
    run_linked_resumable,
    run_resumable,
)
from interpreter.run_types import VMConfig
from tests.covers import NotLanguageFeature, covers
from tests.unit.cfg_helpers import build_simple_cfg, make_instructions


def _three_steps():
    return make_instructions(
        (Opcode.LABEL, {"label": CodeLabel("entry")}),
        (Opcode.CONST, {"result_reg": Register("%0"), "operands": [1]}),
        (Opcode.CONST, {"result_reg": Register("%1"), "operands": [2]}),
        (Opcode.RETURN, {"operands": ["%1"]}),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_run_stopped_by_its_budget_is_budget_exhausted_not_completed():
    cfg, registry = build_simple_cfg(_three_steps())

    def outcome(max_steps: int):
        return run_resumable(
            cfg,
            "entry",
            registry,
            VMConfig(max_steps=max_steps),
            vm=initial_vm_state(),
        )

    short, ample = outcome(2), outcome(100)
    assert isinstance(short, BudgetExhausted)
    assert (short.stats.steps, type(ample)) == (2, Completed)


def _program(directory: Path, source: str) -> Path:
    directory.mkdir()
    (directory / "main.py").write_text(source)
    return directory


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_program_that_never_ends_is_budget_exhausted(tmp_path: Path):
    def outcome(directory: Path):
        linked = compile_directory(directory, Language.PYTHON)
        result = run_linked_resumable(
            linked, EntryPoint.top_level(), max_steps=50, initial_vm=initial_vm_state()
        )
        return linked, result

    looping, runaway = outcome(
        _program(tmp_path / "loops", "x = 0\nwhile True:\n    x = x + 1\n")
    )
    _, ended = outcome(_program(tmp_path / "ends", "x = 1\n"))
    assert isinstance(runaway, BudgetExhausted)
    assert (runaway.vm.data_layout is looping.data_layout, type(ended)) == (
        True,
        Completed,
    )
