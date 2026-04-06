"""External test: compare symbolic vs LLM-plausible resolution strategies.

Verifies that symbolic resolution produces SymbolicValue instances while
LLM-plausible resolution produces concrete values for the same source.

Ported from scripts/demo_unresolved_call.py with proper value assertions.

Run with: poetry run python -m pytest -m external tests/external/test_llm_symbolic_vs_plausible.py -v
"""

import pytest

from interpreter.constants import Language
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
"""


def _get_locals(vm):
    frame = vm.call_stack[0]
    return {
        str(k): v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


@pytest.mark.external
class TestSymbolicVsPlausible:
    def test_symbolic_produces_symbolic_values(self):
        vm = run(
            _SOURCE,
            language=Language.PYTHON,
            unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = _get_locals(vm)
        # math.sqrt and math.floor are unresolved — should be symbolic
        assert isinstance(locals_["x"], SymbolicValue)
        assert isinstance(locals_["z"], SymbolicValue)

    def test_llm_produces_concrete_values(self):
        vm = run(
            _SOURCE,
            language=Language.PYTHON,
            backend="claude",
            unresolved_call_strategy=UnresolvedCallStrategy.LLM,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = _get_locals(vm)
        # LLM resolver should produce concrete values
        assert not isinstance(locals_["x"], SymbolicValue)
        assert abs(locals_["x"] - 4.0) < 0.01
        assert not isinstance(locals_["z"], SymbolicValue)
        assert locals_["z"] == 7 or locals_["z"] == 7.0

    def test_llm_arithmetic_flows_through(self):
        vm = run(
            _SOURCE,
            language=Language.PYTHON,
            backend="claude",
            unresolved_call_strategy=UnresolvedCallStrategy.LLM,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = _get_locals(vm)
        # y = x + 1 should be concrete 5.0 (4.0 + 1)
        assert not isinstance(locals_["y"], SymbolicValue)
        assert abs(locals_["y"] - 5.0) < 0.01
