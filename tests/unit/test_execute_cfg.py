"""Tests for execute_cfg — calling the VM execution loop directly with hand-built CFGs."""

import logging

import pytest

from interpreter.var_name import VarName
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.cfg import CFG, BasicBlock, build_cfg
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.run import execute_cfg, VMConfig, ExecutionStats
from interpreter.types.typed_value import unwrap


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
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 42

    def test_returns_execution_stats(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
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
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
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

    def test_execution_records_steps_and_entry(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [99]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert unwrap(vm.current_frame.local_vars[VarName("result")]) == 99
        assert stats.steps > 0, "execution must have taken at least one step"
        assert cfg.entry == "entry", f"CFG entry should be 'entry', got {cfg.entry}"

    def test_invalid_entry_point_raises(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        with pytest.raises(ValueError, match="not found in CFG"):
            execute_cfg(cfg, "nonexistent_label", registry)

    def test_empty_registry_works_for_simple_programs(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [7]}),
            (Opcode.STORE_VAR, {"operands": ["v", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg = build_cfg(instructions)
        empty_registry = FunctionRegistry()

        vm, stats = execute_cfg(cfg, "entry", empty_registry)

        assert unwrap(vm.current_frame.local_vars[VarName("v")]) == 7

    def test_unconditional_branch_jumps_to_target(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.BRANCH, {"label": CodeLabel("target")}),
            (Opcode.LABEL, {"label": CodeLabel("target")}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert unwrap(vm.current_frame.local_vars[VarName("result")]) == 42

    def test_conditional_branch_takes_true_path(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [True]}),
            (
                Opcode.BRANCH_IF,
                {
                    "operands": ["%0"],
                    "branch_targets": [
                        CodeLabel("then_block"),
                        CodeLabel("else_block"),
                    ],
                },
            ),
            (Opcode.LABEL, {"label": CodeLabel("then_block")}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [10]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%1"]}),
            (Opcode.RETURN, {"operands": ["%1"]}),
            (Opcode.LABEL, {"label": CodeLabel("else_block")}),
            (Opcode.CONST, {"result_reg": "%2", "operands": [20]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%2"]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert unwrap(vm.current_frame.local_vars[VarName("result")]) == 10

    def test_stats_reports_zero_llm_calls_for_local_execution(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [5]}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [3]}),
            (Opcode.BINOP, {"result_reg": "%2", "operands": ["+", "%0", "%1"]}),
            (Opcode.STORE_VAR, {"operands": ["sum", "%2"]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert stats.llm_calls == 0
        assert unwrap(vm.current_frame.local_vars[VarName("sum")]) == 8

    def test_verbose_mode_produces_step_log(self, caplog):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        # Run without verbose — capture baseline logs
        with caplog.at_level(logging.INFO, logger="interpreter.run"):
            execute_cfg(cfg, "entry", registry, VMConfig(verbose=False))
        quiet_log = caplog.text
        caplog.clear()

        # Run with verbose — should produce additional output
        with caplog.at_level(logging.INFO, logger="interpreter.run"):
            execute_cfg(cfg, "entry", registry, VMConfig(verbose=True))
        verbose_log = caplog.text

        assert "step" in verbose_log.lower()
        assert len(verbose_log) > len(quiet_log)
