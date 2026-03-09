"""Unit tests for Lua generic for loop lowering.

Verifies that ipairs()/pairs() wrapper calls are stripped at lowering
time, so the iterable is used directly for index-based iteration.
"""

from __future__ import annotations

from interpreter.ir import Opcode
from tests.unit.rosetta.conftest import parse_for_language


class TestLuaGenericForStripsIpairs:
    def test_no_ipairs_call_in_ir(self):
        """ipairs() should be stripped — no CALL_FUNCTION 'ipairs' in IR."""
        ir = parse_for_language(
            "lua",
            """\
local arr = {10, 5, 3}
local answer = 0
for _, x in ipairs(arr) do
    answer = answer + x
end
""",
        )
        ipairs_calls = [
            inst
            for inst in ir
            if inst.opcode == Opcode.CALL_FUNCTION
            and inst.operands
            and str(inst.operands[0]) == "ipairs"
        ]
        assert (
            len(ipairs_calls) == 0
        ), f"Expected ipairs() to be stripped, found {len(ipairs_calls)} calls"

    def test_len_called_on_array_not_symbolic(self):
        """len() should receive the array register directly."""
        ir = parse_for_language(
            "lua",
            """\
local arr = {10, 5, 3}
local answer = 0
for _, x in ipairs(arr) do
    answer = answer + x
end
""",
        )
        len_calls = [
            inst
            for inst in ir
            if inst.opcode == Opcode.CALL_FUNCTION
            and inst.operands
            and str(inst.operands[0]) == "len"
        ]
        assert len(len_calls) >= 1
        # The len argument should be a register loaded from 'arr',
        # not the result of calling ipairs
        len_arg = str(len_calls[0].operands[1])
        assert len_arg.startswith("%")


class TestLuaGenericForStripsPairs:
    def test_no_pairs_call_in_ir(self):
        """pairs() should be stripped — no CALL_FUNCTION 'pairs' in IR."""
        ir = parse_for_language(
            "lua",
            """\
local t = {a = 1, b = 2}
for k, v in pairs(t) do
    local x = k
end
""",
        )
        pairs_calls = [
            inst
            for inst in ir
            if inst.opcode == Opcode.CALL_FUNCTION
            and inst.operands
            and str(inst.operands[0]) == "pairs"
        ]
        assert (
            len(pairs_calls) == 0
        ), f"Expected pairs() to be stripped, found {len(pairs_calls)} calls"
