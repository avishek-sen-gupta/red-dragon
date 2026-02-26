"""Tests for IR statistics: count_opcodes (pure) and ir_stats (API wrapper)."""

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.ir_stats import count_opcodes
from interpreter.api import ir_stats

SIMPLE_SOURCE = "x = 42\n"

FUNCTION_SOURCE = """\
def greet(name):
    return name

greet("world")
"""


class TestCountOpcodes:
    def test_empty_list_returns_empty_dict(self):
        assert count_opcodes([]) == {}

    def test_single_instruction(self):
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=[42], result_reg="r0")
        ]
        result = count_opcodes(instructions)
        assert result == {"CONST": 1}

    def test_multiple_distinct_opcodes(self):
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=[42], result_reg="r0"),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "r0"]),
            IRInstruction(opcode=Opcode.LOAD_VAR, operands=["x"], result_reg="r1"),
        ]
        result = count_opcodes(instructions)
        assert result == {"CONST": 1, "STORE_VAR": 1, "LOAD_VAR": 1}

    def test_repeated_opcodes_are_summed(self):
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=[1], result_reg="r0"),
            IRInstruction(opcode=Opcode.CONST, operands=[2], result_reg="r1"),
            IRInstruction(opcode=Opcode.CONST, operands=[3], result_reg="r2"),
            IRInstruction(
                opcode=Opcode.BINOP, operands=["+", "r0", "r1"], result_reg="r3"
            ),
        ]
        result = count_opcodes(instructions)
        assert result == {"CONST": 3, "BINOP": 1}

    def test_all_opcodes_counted(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.CONST, operands=[True], result_reg="r0"),
            IRInstruction(opcode=Opcode.BRANCH_IF, operands=["r0"], label="then"),
            IRInstruction(opcode=Opcode.BRANCH, label="end"),
            IRInstruction(opcode=Opcode.LABEL, label="then"),
            IRInstruction(opcode=Opcode.RETURN, operands=["r0"]),
            IRInstruction(opcode=Opcode.LABEL, label="end"),
        ]
        result = count_opcodes(instructions)
        assert result == {
            "LABEL": 3,
            "CONST": 1,
            "BRANCH_IF": 1,
            "BRANCH": 1,
            "RETURN": 1,
        }

    def test_returns_dict_of_str_to_int(self):
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=[0], result_reg="r0")
        ]
        result = count_opcodes(instructions)
        assert all(isinstance(k, str) for k in result)
        assert all(isinstance(v, int) for v in result.values())


class TestIrStats:
    def test_simple_assignment_has_const_and_store(self):
        result = ir_stats(SIMPLE_SOURCE)
        assert result["CONST"] >= 1
        assert result["STORE_VAR"] >= 1

    def test_function_source_has_call_and_return(self):
        result = ir_stats(FUNCTION_SOURCE)
        assert (
            result.get("CALL_FUNCTION", 0)
            + result.get("CALL_METHOD", 0)
            + result.get("CALL_UNKNOWN", 0)
            >= 1
        )
        assert result["RETURN"] >= 1

    def test_returns_dict(self):
        result = ir_stats(SIMPLE_SOURCE)
        assert isinstance(result, dict)

    def test_language_parameter(self):
        js_source = "let x = 42;\n"
        result = ir_stats(js_source, language="javascript")
        assert result["CONST"] >= 1
        assert result["STORE_VAR"] >= 1

    def test_all_counts_are_positive(self):
        result = ir_stats(SIMPLE_SOURCE)
        assert all(v > 0 for v in result.values())
