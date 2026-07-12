"""Integration tests for Python comprehension variable scoping.

Verifies end-to-end that comprehension loop variables do not leak
to the enclosing scope through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from interpreter.frontends.python.features import PythonFeature
from interpreter.types.typed_value import unwrap
from interpreter.var_name import VarName
from tests.covers import covers
from tests.unit.rosetta.conftest import execute_for_language


class TestListComprehensionScopingExecution:
    @covers(PythonFeature.LIST_COMPREHENSION)
    def test_outer_var_preserved_after_comprehension(self):
        """x=99 should survive [x for x in [1,2,3]]."""
        vm, stats = execute_for_language(
            "python",
            """\
x = 99
result = [x for x in [1, 2, 3]]
answer = x
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars[VarName("answer")]) == 99


class TestDictComprehensionScopingExecution:
    @covers(PythonFeature.DICT_COMPREHENSION)
    def test_outer_var_preserved_after_dict_comprehension(self):
        """k=99 should survive {k: k for k in [1,2,3]}."""
        vm, stats = execute_for_language(
            "python",
            """\
k = 99
result = {k: k for k in [1, 2, 3]}
answer = k
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars[VarName("answer")]) == 99


class TestSetComprehensionScopingExecution:
    @covers(PythonFeature.SET_COMPREHENSION)
    def test_outer_var_preserved_after_set_comprehension(self):
        """x=99 should survive {x for x in [1,2,3]}."""
        vm, stats = execute_for_language(
            "python",
            """\
x = 99
result = {x for x in [1, 2, 3]}
answer = x
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars[VarName("answer")]) == 99


class TestGeneratorExpressionScopingExecution:
    @covers(PythonFeature.GENERATOR_EXPRESSION)
    def test_outer_var_preserved_after_generator(self):
        """x=99 should survive list(x for x in [1,2,3])."""
        vm, stats = execute_for_language(
            "python",
            """\
x = 99
result = list(x for x in [1, 2, 3])
answer = x
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars[VarName("answer")]) == 99
