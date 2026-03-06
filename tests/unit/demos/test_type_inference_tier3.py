"""Tests for Tier 3 type inference enhancements.

Converted from scripts/demo_type_inference_tier3.py.
Exercises 3 features:
  1. self/this class typing  (param:self/this → class name)
  2. CALL_UNKNOWN resolution (indirect calls through registers)
  3. STORE_INDEX / LOAD_INDEX (array element type tracking)
"""

from interpreter.api import lower_and_infer
from interpreter.default_conversion_rules import DefaultConversionRules
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment_builder import TypeEnvironmentBuilder
from interpreter.type_inference import infer_types
from interpreter.type_resolver import TypeResolver


def _resolver():
    return TypeResolver(DefaultConversionRules())


def _lower_and_infer(source: str, language: str):
    return lower_and_infer(source, language=language)


class TestSelfThisTyping:
    def test_self_typing_python(self):
        source = """\
class Dog:
    def __init__(self):
        self.age = 5
        self.name = "Rex"

    def get_age(self):
        return self.age
"""
        instructions, env = _lower_and_infer(source, "python")

        # All param:self symbolic registers should be typed as Dog
        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC
            and i.operands
            and str(i.operands[0]) == "param:self"
        ]
        assert len(symbolics) >= 2
        for sym in symbolics:
            assert env.register_types[sym.result_reg] == "Dog"

        # LOAD_FIELD through typed self should resolve field types
        load_fields = [i for i in instructions if i.opcode == Opcode.LOAD_FIELD]
        age_loads = [
            i
            for i in load_fields
            if len(i.operands) >= 2 and str(i.operands[1]) == "age"
        ]
        assert len(age_loads) >= 1
        assert env.register_types[age_loads[0].result_reg] == "Int"

    def test_this_typing_java(self):
        source = """\
class Cat {
    int lives;
    int getLives() { return this.lives; }
}
"""
        instructions, env = _lower_and_infer(source, "java")

        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC
            and i.operands
            and str(i.operands[0]) == "param:this"
        ]
        assert len(symbolics) >= 1
        for sym in symbolics:
            assert env.register_types[sym.result_reg] == "Cat"


class TestCallUnknownResolution:
    def test_call_unknown_resolution(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.BRANCH, label="end_add_0"),
            IRInstruction(opcode=Opcode.LABEL, label="func_add_0"),
            IRInstruction(
                opcode=Opcode.SYMBOLIC,
                result_reg="%0",
                operands=["param:a"],
            ),
            IRInstruction(
                opcode=Opcode.SYMBOLIC,
                result_reg="%1",
                operands=["param:b"],
            ),
            IRInstruction(opcode=Opcode.RETURN, operands=["%2"]),
            IRInstruction(opcode=Opcode.LABEL, label="end_add_0"),
            IRInstruction(
                opcode=Opcode.CONST,
                result_reg="%3",
                operands=["<function:add@func_add_0>"],
            ),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["add", "%3"]),
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%4", operands=["add"]),
            IRInstruction(
                opcode=Opcode.CALL_UNKNOWN,
                result_reg="%5",
                operands=["%4", "%6", "%7"],
            ),
        ]

        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": "Int"},
            func_param_types={"func_add_0": [("a", "Int"), ("b", "Int")]},
            register_types={"%0": "Int", "%1": "Int"},
        )
        env = infer_types(instructions, _resolver(), type_env_builder=builder)

        assert env.register_types["%5"] == "Int"


class TestStoreLoadIndex:
    def test_store_load_index(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%0"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"]),
            IRInstruction(opcode=Opcode.CONST, result_reg="%2", operands=["0"]),
            IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%0", "%2", "%1"]),
            IRInstruction(opcode=Opcode.CONST, result_reg="%3", operands=["1"]),
            IRInstruction(
                opcode=Opcode.LOAD_INDEX, result_reg="%4", operands=["%0", "%3"]
            ),
        ]

        env = infer_types(instructions, _resolver())

        assert env.register_types["%0"] == "Array"
        assert env.register_types["%1"] == "Int"
        assert env.register_types["%4"] == "Int"

    def test_store_load_index_last_write_wins(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%0"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"]),
            IRInstruction(opcode=Opcode.CONST, result_reg="%idx", operands=["0"]),
            IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%0", "%idx", "%1"]),
            IRInstruction(opcode=Opcode.CONST, result_reg="%2", operands=['"hello"']),
            IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%0", "%idx", "%2"]),
            IRInstruction(
                opcode=Opcode.LOAD_INDEX, result_reg="%3", operands=["%0", "%idx"]
            ),
        ]

        env = infer_types(instructions, _resolver())

        assert env.register_types["%3"] == "String"
