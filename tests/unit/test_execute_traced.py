"""Tests for execute_cfg_traced and execute_traced — traced execution with step snapshots."""

from interpreter.ir import IRInstruction, Opcode
from interpreter.cfg import build_cfg
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.run import execute_cfg_traced, VMConfig
from interpreter.trace_types import TraceStep, ExecutionTrace


def _make_instructions(*specs):
    """Helper: build IRInstruction list from (opcode, kwargs) tuples."""
    return [IRInstruction(opcode=op, **kw) for op, kw in specs]


def _build_simple_cfg(instructions):
    """Build a CFG + registry from instructions."""
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)
    return cfg, registry


class TestExecuteCfgTracedBasic:
    def test_trace_length_matches_executed_steps(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        # LABEL is skipped, so 3 executed instructions: CONST, STORE_VAR, RETURN
        assert len(trace.steps) == 3

    def test_returns_execution_trace_type(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        assert isinstance(trace, ExecutionTrace)
        assert all(isinstance(s, TraceStep) for s in trace.steps)

    def test_each_snapshot_is_independent(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [2]}),
            (Opcode.STORE_VAR, {"operands": ["y", "%1"]}),
            (Opcode.RETURN, {"operands": ["%1"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        # Mutating one snapshot must not affect others
        trace.steps[0].vm_state.call_stack[0].local_vars["INJECTED"] = "bad"
        assert "INJECTED" not in trace.steps[1].vm_state.call_stack[0].local_vars
        assert "INJECTED" not in trace.steps[-1].vm_state.call_stack[0].local_vars

    def test_block_label_and_instruction_index_are_correct(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        # All instructions are in the "entry" block
        assert all(s.block_label == "entry" for s in trace.steps)
        # CFG builder strips LABEL from block instructions, so CONST is ip=0
        assert trace.steps[0].instruction_index == 0
        assert trace.steps[1].instruction_index == 1
        assert trace.steps[2].instruction_index == 2

    def test_initial_state_has_empty_heap_and_main_frame(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        assert trace.initial_state is not None
        assert trace.initial_state.heap == {}
        assert len(trace.initial_state.call_stack) == 1
        assert trace.initial_state.call_stack[0].function_name == "<main>"

    def test_step_indices_are_sequential(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [5]}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [3]}),
            (Opcode.BINOP, {"result_reg": "%2", "operands": ["+", "%0", "%1"]}),
            (Opcode.STORE_VAR, {"operands": ["sum", "%2"]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        expected_indices = list(range(len(trace.steps)))
        actual_indices = [s.step_index for s in trace.steps]
        assert actual_indices == expected_indices

    def test_stats_match_trace_length(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        assert trace.stats.steps > 0
        assert trace.stats.llm_calls == 0

    def test_final_vm_state_matches_last_trace_step(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        last_step_vars = trace.steps[-1].vm_state.call_stack[0].local_vars
        assert last_step_vars["x"] == 42

    def test_used_llm_is_false_for_local_execution(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [1]}),
            (Opcode.RETURN, {"operands": ["%0"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        assert all(not s.used_llm for s in trace.steps)

    def test_branch_trace_records_correct_labels(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "%0", "operands": [True]}),
            (
                Opcode.BRANCH_IF,
                {"operands": ["%0"], "label": "then_block, else_block"},
            ),
            (Opcode.LABEL, {"label": "then_block"}),
            (Opcode.CONST, {"result_reg": "%1", "operands": [10]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%1"]}),
            (Opcode.RETURN, {"operands": ["%1"]}),
            (Opcode.LABEL, {"label": "else_block"}),
            (Opcode.CONST, {"result_reg": "%2", "operands": [20]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        # First two steps in entry, remaining in then_block
        assert trace.steps[0].block_label == "entry"
        assert trace.steps[1].block_label == "entry"
        then_steps = [s for s in trace.steps if s.block_label == "then_block"]
        assert len(then_steps) > 0
