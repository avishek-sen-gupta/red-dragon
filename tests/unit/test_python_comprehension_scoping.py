"""Unit tests for Python comprehension variable scoping.

Python 3 scopes comprehension loop variables to the comprehension itself.
Variables like `x` in `[x for x in items]` should not leak to the
enclosing scope. At the IR level, this means the comprehension loop body
should use enter_block_scope/exit_block_scope to declare loop variables.
"""

from __future__ import annotations

from interpreter.ir import Opcode
from interpreter.typed_value import unwrap
from tests.unit.rosetta.conftest import parse_for_language, execute_for_language


class TestListComprehensionScoping:
    def test_loop_var_does_not_shadow_outer(self):
        """Comprehension var 'x' should not overwrite outer 'x'."""
        vm, stats = execute_for_language(
            "python",
            """\
x = 99
result = [x for x in [1, 2, 3]]
answer = x
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars["answer"]) == 99, (
            f"Comprehension variable 'x' leaked to outer scope: "
            f"answer={unwrap(frame.local_vars['answer'])}"
        )

    def test_loop_var_is_mangled_in_comprehension(self):
        """Comprehension var should be mangled to avoid leaking."""
        ir = parse_for_language(
            "python",
            """\
result = [item for item in [1, 2, 3]]
""",
        )
        store_vars = [
            str(inst.operands[0])
            for inst in ir
            if inst.opcode == Opcode.DECL_VAR and inst.operands
        ]
        # 'item' should be mangled (e.g. 'item$1'), not stored as raw 'item'
        item_vars = [v for v in store_vars if v.startswith("item")]
        assert len(item_vars) >= 1, f"No item var found in {store_vars}"
        assert all(
            "$" in v for v in item_vars
        ), f"Expected mangled item var (e.g. item$1), got: {item_vars}"


class TestDictComprehensionScoping:
    def test_loop_var_does_not_shadow_outer(self):
        """Dict comprehension var should not overwrite outer variable."""
        vm, stats = execute_for_language(
            "python",
            """\
k = 99
result = {k: k for k in [1, 2, 3]}
answer = k
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars["answer"]) == 99, (
            f"Dict comprehension variable 'k' leaked: "
            f"answer={unwrap(frame.local_vars['answer'])}"
        )


class TestSetComprehensionScoping:
    def test_loop_var_does_not_shadow_outer(self):
        """Set comprehension var should not overwrite outer variable."""
        vm, stats = execute_for_language(
            "python",
            """\
x = 99
result = {x for x in [1, 2, 3]}
answer = x
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars["answer"]) == 99, (
            f"Set comprehension variable 'x' leaked: "
            f"answer={unwrap(frame.local_vars['answer'])}"
        )


class TestGeneratorExpressionScoping:
    def test_loop_var_does_not_shadow_outer(self):
        """Generator expression var should not overwrite outer variable."""
        vm, stats = execute_for_language(
            "python",
            """\
x = 99
result = list(x for x in [1, 2, 3])
answer = x
""",
        )
        frame = vm.call_stack[0]
        assert unwrap(frame.local_vars["answer"]) == 99, (
            f"Generator expression variable 'x' leaked: "
            f"answer={unwrap(frame.local_vars['answer'])}"
        )
