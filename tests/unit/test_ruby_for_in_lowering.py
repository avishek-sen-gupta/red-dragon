"""Unit tests for Ruby for-in loop lowering.

Verifies that the Ruby for-in loop correctly lowers the iterable
expression rather than lowering the 'in' AST wrapper node as a
string constant.
"""

from __future__ import annotations

from interpreter.ir import Opcode
from tests.unit.rosetta.conftest import parse_for_language


class TestRubyForInLoweringProducesCorrectIR:
    def test_iterable_is_not_const_string(self):
        """The iterable should be a LOAD_VAR for 'arr', not a CONST 'in arr'."""
        ir = parse_for_language(
            "ruby",
            """\
arr = [10, 5, 3]
answer = 0
for x in arr
    answer = answer + x
end
""",
        )
        const_operands = [
            str(inst.operands[0])
            for inst in ir
            if inst.opcode == Opcode.CONST and inst.operands
        ]
        assert "in arr" not in const_operands, (
            f"Found 'in arr' as CONST — the 'in' node is being lowered "
            f"as a string constant instead of unwrapping the iterable"
        )

    def test_iterable_is_loaded_from_variable(self):
        """The loop should LOAD_VAR 'arr' to get the iterable."""
        ir = parse_for_language(
            "ruby",
            """\
arr = [10, 5, 3]
answer = 0
for x in arr
    answer = answer + x
end
""",
        )
        load_var_operands = [
            str(inst.operands[0])
            for inst in ir
            if inst.opcode == Opcode.LOAD_VAR and inst.operands
        ]
        assert "arr" in load_var_operands, (
            f"Expected LOAD_VAR 'arr' for the iterable, " f"got: {load_var_operands}"
        )

    def test_len_receives_array_not_string(self):
        """len() should be called on the array register, not a string constant."""
        ir = parse_for_language(
            "ruby",
            """\
arr = [10, 5, 3]
answer = 0
for x in arr
    answer = answer + x
end
""",
        )
        # Find the CALL_FUNCTION for len — its second operand should be
        # a register that was loaded from the 'arr' variable, not a CONST
        len_calls = [
            inst
            for inst in ir
            if inst.opcode == Opcode.CALL_FUNCTION
            and inst.operands
            and str(inst.operands[0]) == "len"
        ]
        assert len(len_calls) >= 1, "Expected at least one len() call"
        # The len call's argument should be a register (starts with %)
        len_arg = str(len_calls[0].operands[1])
        assert len_arg.startswith(
            "%"
        ), f"Expected len() argument to be a register, got: {len_arg}"
