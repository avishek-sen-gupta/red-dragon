"""Integration tests for Python comprehension variable scoping.

Verifies end-to-end that comprehension loop variables do not leak
to the enclosing scope through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language
from interpreter.typed_value import unwrap


class TestListComprehensionScopingExecution:
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
        assert unwrap(frame.local_vars["answer"]) == 99


class TestDictComprehensionScopingExecution:
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
        assert unwrap(frame.local_vars["answer"]) == 99


class TestSetComprehensionScopingExecution:
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
        assert unwrap(frame.local_vars["answer"]) == 99


class TestGeneratorExpressionScopingExecution:
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
        assert unwrap(frame.local_vars["answer"]) == 99
