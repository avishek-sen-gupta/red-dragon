"""Integration tests: TypeScript import x = require('./module') cross-module linking.

Verifies that import_require_clause lowers to IR, resolves via the linker,
and the linked program contains both modules' code. Full namespace-based
dispatch (utils.add()) requires deeper linker support (module namespace objects)
which is tracked separately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.ir import Opcode
from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from tests.covers import covers
from interpreter.frontends.typescript.features import TypeScriptFeature

# ── Source fixtures ────────────────────────────────────────────────

_UTILS_TS = """\
function add(a: number, b: number): number {
    return a + b;
}
"""

_MAIN_REQUIRE_FUNC_TS = """\
import utils = require('./utils');
let answer: number = utils.add(3, 4);
"""

_GREETER_TS = """\
class Greeter {
    prefix: string;

    constructor(p: string) {
        this.prefix = p;
    }

    greet(name: string): string {
        return this.prefix + name;
    }
}
"""

_MAIN_REQUIRE_CLASS_TS = """\
import greeter = require('./greeter');
let g = new greeter.Greeter("Hello ");
let answer: string = g.greet("world");
"""


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def ts_func_project(tmp_path: Path) -> Path:
    """Two-file TS project: main requires utils with a function."""
    (tmp_path / "utils.ts").write_text(_UTILS_TS)
    (tmp_path / "main.ts").write_text(_MAIN_REQUIRE_FUNC_TS)
    return tmp_path


@pytest.fixture
def ts_class_project(tmp_path: Path) -> Path:
    """Two-file TS project: main requires greeter with a class."""
    (tmp_path / "greeter.ts").write_text(_GREETER_TS)
    (tmp_path / "main.ts").write_text(_MAIN_REQUIRE_CLASS_TS)
    return tmp_path


def _execute_linked(linked: LinkedProgram, max_steps: int = 500):
    strategies = ExecutionStrategies(
        func_symbol_table=linked.func_symbol_table,
        class_symbol_table=linked.class_symbol_table,
    )
    config = VMConfig(max_steps=max_steps)
    return execute_cfg(
        linked.merged_cfg,
        linked.merged_cfg.entry,
        linked.merged_registry,
        config,
        strategies,
    )


def _local_vars(vm):
    frame = vm.call_stack[0]
    return {
        k: v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


# ── Tests: function import via require ─────────────────────────────


class TestTsImportRequireFunction:
    """import utils = require('./utils'); — linking and IR generation."""

    @covers(TypeScriptFeature.REQUIRE_IMPORT)
    def test_linked_ir_contains_dependency_function(self, ts_func_project: Path):
        """After linking, merged IR should contain the 'add' function from utils.ts."""
        linked = compile_directory(ts_func_project, Language.TYPESCRIPT)
        assert isinstance(linked, LinkedProgram)
        ir_labels = [
            str(inst.label)
            for inst in linked.merged_ir
            if hasattr(inst, "label") and inst.label is not None
        ]
        assert any(
            "add" in label for label in ir_labels
        ), f"'add' function not in linked IR labels: {ir_labels[:20]}"

    @covers(TypeScriptFeature.REQUIRE_IMPORT)
    def test_require_stores_variable(self, ts_func_project: Path):
        """The require() call should store 'utils' in scope (even as symbolic)."""
        linked = compile_directory(ts_func_project, Language.TYPESCRIPT)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert (
            VarName("utils") in lvars
        ), f"'utils' not in scope after require: {list(lvars.keys())}"

    @covers(TypeScriptFeature.REQUIRE_IMPORT)
    def test_answer_variable_in_scope(self, ts_func_project: Path):
        """The downstream variable 'answer' should exist in scope."""
        linked = compile_directory(ts_func_project, Language.TYPESCRIPT)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert (
            VarName("answer") in lvars
        ), f"'answer' not in scope: {list(lvars.keys())}"

    @covers(TypeScriptFeature.REQUIRE_IMPORT)
    def test_require_emits_call_function_in_ir(self, ts_func_project: Path):
        """Merged IR should contain a CALL_FUNCTION for 'require'."""
        linked = compile_directory(ts_func_project, Language.TYPESCRIPT)
        require_calls = [
            inst
            for inst in linked.merged_ir
            if inst.opcode == Opcode.CALL_FUNCTION
            and len(inst.operands) >= 1
            and str(inst.operands[0]) == "require"
        ]
        assert len(require_calls) >= 1, "No CALL_FUNCTION require in merged IR"


# ── Tests: class import via require ────────────────────────────────


class TestTsImportRequireClass:
    """import greeter = require('./greeter'); — linking and IR generation."""

    @covers(TypeScriptFeature.REQUIRE_IMPORT)
    def test_linked_ir_contains_class(self, ts_class_project: Path):
        """After linking, merged IR should contain the 'Greeter' class."""
        linked = compile_directory(ts_class_project, Language.TYPESCRIPT)
        assert isinstance(linked, LinkedProgram)
        ir_labels = [
            str(inst.label)
            for inst in linked.merged_ir
            if hasattr(inst, "label") and inst.label is not None
        ]
        assert any(
            "Greeter" in label for label in ir_labels
        ), f"'Greeter' class not in linked IR labels: {ir_labels[:20]}"

    @covers(TypeScriptFeature.REQUIRE_IMPORT)
    def test_require_stores_variable(self, ts_class_project: Path):
        """The require() call should store 'greeter' in scope."""
        linked = compile_directory(ts_class_project, Language.TYPESCRIPT)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert (
            VarName("greeter") in lvars
        ), f"'greeter' not in scope after require: {list(lvars.keys())}"

    @covers(TypeScriptFeature.REQUIRE_IMPORT)
    def test_g_variable_in_scope(self, ts_class_project: Path):
        """The Greeter instance 'g' should exist in scope."""
        linked = compile_directory(ts_class_project, Language.TYPESCRIPT)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert (
            VarName("g") in lvars
        ), f"'g' (Greeter instance) not in scope: {list(lvars.keys())}"
