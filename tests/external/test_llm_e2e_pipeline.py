"""External test: end-to-end LLM IR generation + LLM VM execution pipeline.

Exercises both LLM integration points:
  1. LLM Frontend — source lowered to IR by the LLM (not tree-sitter)
  2. LLM Backend  — VM uses LLM to resolve unresolved external calls

Ported from scripts/demo_llm_e2e.py with proper value assertions.

Run with: poetry run python -m pytest -m external tests/external/test_llm_e2e_pipeline.py -v
"""

import pytest

from interpreter.constants import Language, FRONTEND_LLM, FRONTEND_DETERMINISTIC
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run
from interpreter.run_types import UnresolvedCallStrategy
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import SymbolicValue

_SOURCE = """\
import math

x = math.sqrt(16)
y = x + 1
z = math.floor(7.8)
total = x + y + z
"""


def _get_locals(vm):
    frame = vm.call_stack[0]
    return {
        str(k): v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


@pytest.mark.external
class TestLLMFrontendWithSymbolicExecution:
    """LLM frontend lowers source to IR; external calls stay symbolic."""

    def test_produces_ir_and_executes(self):
        vm = run(
            _SOURCE,
            language=Language.PYTHON,
            backend="claude",
            frontend_type=FRONTEND_LLM,
            unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = _get_locals(vm)
        # x = math.sqrt(16) should be symbolic (unresolved)
        assert isinstance(locals_.get("x"), SymbolicValue)


@pytest.mark.external
class TestDeterministicFrontendWithLLMResolver:
    """Deterministic frontend + LLM resolver produces concrete values."""

    def test_math_calls_resolve_to_concrete(self):
        vm = run(
            _SOURCE,
            language=Language.PYTHON,
            backend="claude",
            frontend_type=FRONTEND_DETERMINISTIC,
            unresolved_call_strategy=UnresolvedCallStrategy.LLM,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = _get_locals(vm)

        # math.sqrt(16) should be concrete 4.0
        assert not isinstance(locals_.get("x"), SymbolicValue)
        assert abs(locals_["x"] - 4.0) < 0.01

        # math.floor(7.8) should be concrete 7
        assert not isinstance(locals_.get("z"), SymbolicValue)
        assert locals_["z"] == 7 or locals_["z"] == 7.0
