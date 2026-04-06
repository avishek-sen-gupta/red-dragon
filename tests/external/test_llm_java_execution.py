"""External test: LLM plausible resolver on Java with stdlib calls.

Verifies that the LLM execution strategy produces correct concrete values
for unresolvable Java stdlib calls (Math.sqrt, String.valueOf, .length()).

Run with: poetry run python -m pytest -m external tests/external/test_llm_java_execution.py -v
"""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig, UnresolvedCallStrategy
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import SymbolicValue

_JAVA_SOURCE = """\
double x = 42;
double y = 50;
double z = Math.sqrt(y);
String s = String.valueOf(z);
int len = s.length();
"""


@pytest.fixture
def java_project(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "main" / "java" / "Main.java"
    src.parent.mkdir(parents=True)
    src.write_text(_JAVA_SOURCE)
    return tmp_path


def _get_locals(vm):
    frame = vm.call_stack[0]
    return {
        str(k): v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


@pytest.mark.external
class TestLLMJavaExecution:
    """LLM plausible resolver produces correct concrete values for Java stdlib."""

    def test_all_values_concrete(self, java_project: Path):
        linked = compile_directory(java_project, Language.JAVA)
        config = VMConfig(
            max_steps=500,
            unresolved_call_strategy=UnresolvedCallStrategy.LLM,
            backend="claude",
            source_language="java",
        )
        strategies = ExecutionStrategies(
            func_symbol_table=linked.func_symbol_table,
            class_symbol_table=linked.class_symbol_table,
        )
        vm, stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            config,
            strategies,
        )

        locals_ = _get_locals(vm)

        # x and y are plain constants — always concrete
        assert locals_["x"] == 42
        assert locals_["y"] == 50

        # z = Math.sqrt(50) — LLM should return correct value
        assert not isinstance(locals_["z"], SymbolicValue)
        assert abs(locals_["z"] - 7.0710678118654755) < 0.01

        # s = String.valueOf(z) — LLM should return a string
        assert not isinstance(locals_["s"], SymbolicValue)
        assert isinstance(locals_["s"], str)

        # len = s.length() — resolved locally as string builtin
        assert not isinstance(locals_["len"], SymbolicValue)
        assert isinstance(locals_["len"], int)
        assert locals_["len"] == len(locals_["s"])

    def test_llm_calls_counted(self, java_project: Path):
        linked = compile_directory(java_project, Language.JAVA)
        config = VMConfig(
            max_steps=500,
            unresolved_call_strategy=UnresolvedCallStrategy.LLM,
            backend="claude",
            source_language="java",
        )
        strategies = ExecutionStrategies(
            func_symbol_table=linked.func_symbol_table,
            class_symbol_table=linked.class_symbol_table,
        )
        _, stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            config,
            strategies,
        )

        # At least 2 LLM calls: Math.sqrt and String.valueOf
        # .length() should resolve locally as a string builtin
        assert stats.llm_calls >= 2
