"""Tests for execute_cfg — calling the VM execution loop directly with hand-built CFGs."""

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.cfg import CFG, BasicBlock, build_cfg
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.run import execute_cfg, VMConfig, ExecutionStats


def _make_instructions(*specs):
    """Helper: build IRInstruction list from (opcode, kwargs) tuples."""
    return [IRInstruction(opcode=op, **kw) for op, kw in specs]


def _build_simple_cfg(instructions):
    """Build a CFG + registry from instructions."""
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)
    return cfg, registry


class TestExecuteCfgBasic:
    def test_const_and_store_sets_variable(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert vm.current_frame.local_vars["x"] == 42

    def test_returns_execution_stats(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert isinstance(stats, ExecutionStats)
        assert stats.steps > 0
        assert stats.llm_calls == 0

    def test_max_steps_limits_execution(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [2]}),
            (Opcode.STORE_VAR, {"operands": ["y", "%1"]}),
            (Opcode.CONST, {"result_reg": "%2", "operands": [3]}),
            (Opcode.STORE_VAR, {"operands": ["z", "%2"]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)
        config = VMConfig(max_steps=3)

        vm, stats = execute_cfg(cfg, "entry", registry, config)

        assert stats.steps == 3

    def test_default_config_uses_sensible_defaults(self):
        config = VMConfig()
        assert config.backend == "claude"
        assert config.max_steps == 100
        assert config.verbose is False

    def test_config_is_frozen(self):
        config = VMConfig()
        with pytest.raises(AttributeError):
            config.backend = "openai"

    def test_entry_point_resolution(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [99]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert vm.current_frame.local_vars["result"] == 99

    def test_invalid_entry_point_raises(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        with pytest.raises(ValueError, match="not found in CFG"):
            execute_cfg(cfg, "nonexistent_label", registry)

    def test_empty_registry_works_for_simple_programs(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [7]}),
            (Opcode.STORE_VAR, {"operands": ["v", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg = build_cfg(instructions)
        empty_registry = FunctionRegistry()

        vm, stats = execute_cfg(cfg, "entry", empty_registry)

        assert vm.current_frame.local_vars["v"] == 7

    def test_unconditional_branch_jumps_to_target(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.BRANCH, {"label": "target"}),
            (Opcode.LABEL, {"label": "target"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert vm.current_frame.local_vars["result"] == 42

    def test_conditional_branch_takes_true_path(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [True]}),
            (Opcode.BRANCH_IF, {"operands": ["%0"], "label": "then_block, else_block"}),
            (Opcode.LABEL, {"label": "then_block"}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [10]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%1"]}),
            (Opcode.RETURN, {"operands": ["%1"]}),
            (Opcode.LABEL, {"label": "else_block"}),
            (Opcode.CONST, {"result_reg": "%2", "operands": [20]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%2"]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert vm.current_frame.local_vars["result"] == 10

    def test_stats_reports_zero_llm_calls_for_local_execution(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [5]}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [3]}),
            (Opcode.BINOP, {"result_reg": "%2", "operands": ["+", "%0", "%1"]}),
            (Opcode.STORE_VAR, {"operands": ["sum", "%2"]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert stats.llm_calls == 0
        assert vm.current_frame.local_vars["sum"] == 8

    def test_verbose_mode_produces_output(self, capsys):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)
        config = VMConfig(verbose=True)

        execute_cfg(cfg, "entry", registry, config)

        captured = capsys.readouterr()
        assert "step" in captured.out.lower()
