"""Tests for run_linked_traced() — traced execution of LinkedProgram."""

from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.frontend import get_frontend
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter.project.entry_point import EntryPoint
from interpreter.project.types import LinkedProgram
from interpreter.run import run_linked_traced
from interpreter.trace_types import ExecutionTrace


def _build_linked_program(source: str, language: Language) -> LinkedProgram:
    """Helper to build a LinkedProgram from source code."""
    frontend = get_frontend(language)
    instructions = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(instructions)
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    return LinkedProgram(
        modules={},
        merged_ir=list(instructions),
        merged_cfg=cfg,
        merged_registry=registry,
        language=language,
        import_graph={},
        type_env_builder=frontend.type_env_builder,
        symbol_table=frontend.symbol_table,
        data_layout=frontend.data_layout,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )


class TestRunLinkedTraced:
    """Tests for run_linked_traced() with top-level and function entry points."""

    def test_top_level_returns_trace(self):
        """Verify top-level execution produces a trace with steps."""
        source = "x = 1 + 2\n"
        linked = _build_linked_program(source, Language.PYTHON)

        vm, trace = run_linked_traced(
            linked,
            entry_point=EntryPoint.top_level(),
            max_steps=100,
        )

        # Verify trace is returned
        assert isinstance(trace, ExecutionTrace)
        # Verify we got some execution steps
        assert len(trace.steps) > 0
        # Verify initial state is set
        assert trace.initial_state is not None
        # Verify final VM state has the variable
        assert vm.current_frame.local_vars[VarName("x")].value == 3

    def test_function_entry_returns_trace(self):
        """Verify function entry point execution produces a trace."""
        source = """
def add(a, b):
    return a + b

def main():
    result = add(3, 7)
"""
        linked = _build_linked_program(source, Language.PYTHON)

        vm, trace = run_linked_traced(
            linked,
            entry_point=EntryPoint.function(lambda f: f.name == FuncName("main")),
            max_steps=100,
        )

        # Verify trace is returned
        assert isinstance(trace, ExecutionTrace)
        # Verify we got some execution steps
        assert len(trace.steps) > 0
        # Verify initial state is set
        assert trace.initial_state is not None
        # Verify final VM state has the result
        assert vm.current_frame.local_vars[VarName("result")].value == 10

    def test_two_phase_concatenates_traces(self):
        """Verify two-phase execution (preamble + dispatch) concatenates traces."""
        source = """
def multiply(x, y):
    return x * y

def test():
    answer = multiply(6, 7)
"""
        linked = _build_linked_program(source, Language.PYTHON)

        vm, trace = run_linked_traced(
            linked,
            entry_point=EntryPoint.function(lambda f: f.name == FuncName("test")),
            max_steps=200,
        )

        # Verify trace is returned
        assert isinstance(trace, ExecutionTrace)
        # Verify we got steps (preamble + dispatch)
        assert len(trace.steps) > 0
        # Verify step indices are properly ordered (0, 1, 2, ...)
        step_indices = [s.step_index for s in trace.steps]
        assert step_indices == list(range(len(trace.steps)))
        # Verify final state has the result
        assert vm.current_frame.local_vars[VarName("answer")].value == 42
        # Verify initial state is preserved (from preamble)
        assert trace.initial_state is not None
