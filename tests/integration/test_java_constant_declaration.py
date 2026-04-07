"""Integration test for Java ``public static final`` constant_declaration lowering.

Java's ``constant_declaration`` node (``public static final Type NAME = expr``)
is not yet supported by the Java frontend. This test documents the gap: when
a class declares ``public static final String`` constants, the frontend emits
``Symbolic(hint='unsupported:constant_declaration')`` instead of lowering the
initialiser expression.

This affects real-world code such as padding constants::

    public static final String PAD1 = "                ";
    public static final String PAD2 = PAD1 + PAD1 + PAD1 + PAD1;
"""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.vm_types import SymbolicValue

_CONSTANTS_JAVA = """\
public class Constants {
    public static final String GREETING = "hello";
    public static final int MAX_SIZE = 100;
    public static final String PADDED = "  " + "  ";
}

String g = Constants.GREETING;
int m = Constants.MAX_SIZE;
"""


@pytest.fixture
def constants_project(tmp_path: Path) -> Path:
    main_file = tmp_path / "src" / "main" / "java" / "Constants.java"
    main_file.parent.mkdir(parents=True, exist_ok=True)
    main_file.write_text(_CONSTANTS_JAVA)
    return tmp_path


class TestJavaConstantDeclaration:
    def test_static_final_constants_are_concrete(self, constants_project: Path):
        """public static final fields should lower to concrete values."""
        linked = compile_directory(constants_project, Language.JAVA)

        strategies = ExecutionStrategies(
            func_symbol_table=linked.func_symbol_table,
            class_symbol_table=linked.class_symbol_table,
            symbol_table=linked.symbol_table,
        )
        config = VMConfig(max_steps=500)
        vm, stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            config,
            strategies,
        )

        frame = vm.call_stack[0]
        local_vars = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in frame.local_vars.items()
        }

        # All constant_declaration values should be concrete
        symbolics = [
            (str(k), v.name)
            for k, v in local_vars.items()
            if isinstance(v, SymbolicValue)
        ]
        assert symbolics == [], f"Expected no symbolics: {symbolics}"

        assert local_vars.get(VarName("g")) == "hello"
        assert local_vars.get(VarName("m")) == 100
