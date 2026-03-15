"""Tests for Tier 3 type inference enhancements.

Converted from scripts/demo_type_inference_tier3.py.
Exercises 3 features:
  1. self/this class typing  (param:self/this → class name)
  2. CALL_UNKNOWN resolution (indirect calls through registers)
  3. STORE_INDEX / LOAD_INDEX (array element type tracking)
"""

from interpreter.api import lower_and_infer
from interpreter.default_conversion_rules import DefaultTypeConversionRules
from interpreter.func_ref import FuncRef
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment_builder import TypeEnvironmentBuilder
from interpreter.type_expr import parse_type, scalar
from interpreter.type_inference import infer_types
from interpreter.type_resolver import TypeResolver


def _resolver():
    return TypeResolver(DefaultTypeConversionRules())


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
                operands=["func_add_0"],
            ),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["add", "%3"]),
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%4", operands=["add"]),
            IRInstruction(
                opcode=Opcode.CALL_UNKNOWN,
                result_reg="%5",
                operands=["%4", "%6", "%7"],
            ),
        ]

        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": scalar("Int")},
            func_param_types={
                "func_add_0": [("a", scalar("Int")), ("b", scalar("Int"))]
            },
            register_types={"%0": scalar("Int"), "%1": scalar("Int")},
        )
        func_st = {"func_add_0": FuncRef(name="add", label="func_add_0")}
        env = infer_types(
            instructions,
            _resolver(),
            type_env_builder=builder,
            func_symbol_table=func_st,
        )

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

        assert env.register_types["%0"] == "Array[Int]"
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


class TestArrayElementTypePromotion:
    """Unit tests for Array → Array[ElementType] promotion in type inference."""

    def test_array_register_promoted_to_array_of_int(self):
        """NEW_ARRAY + STORE_INDEX with Int value → register type is Array[Int]."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%arr"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%val", operands=["42"]),
            IRInstruction(opcode=Opcode.CONST, result_reg="%idx", operands=["0"]),
            IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%arr", "%idx", "%val"]),
        ]
        env = infer_types(instructions, _resolver())
        assert env.register_types["%arr"] == "Array[Int]"

    def test_array_var_promoted_to_array_of_int(self):
        """STORE_VAR of an array with Int elements → var type is Array[Int]."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%arr"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%val", operands=["42"]),
            IRInstruction(opcode=Opcode.CONST, result_reg="%idx", operands=["0"]),
            IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%arr", "%idx", "%val"]),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["nums", "%arr"]),
        ]
        env = infer_types(instructions, _resolver())
        assert env.var_types["nums"] == "Array[Int]"

    def test_array_var_promoted_to_array_of_string(self):
        """STORE_VAR of an array with String elements → var type is Array[String]."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%arr"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%val", operands=['"hello"']),
            IRInstruction(opcode=Opcode.CONST, result_reg="%idx", operands=["0"]),
            IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%arr", "%idx", "%val"]),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["names", "%arr"]),
        ]
        env = infer_types(instructions, _resolver())
        assert env.var_types["names"] == "Array[String]"

    def test_element_type_propagated_through_load_var(self):
        """Array element types propagate through STORE_VAR → LOAD_VAR → LOAD_INDEX."""
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%arr"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%val", operands=["42"]),
            IRInstruction(opcode=Opcode.CONST, result_reg="%idx", operands=["0"]),
            IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%arr", "%idx", "%val"]),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["nums", "%arr"]),
            # Load the variable into a new register
            IRInstruction(
                opcode=Opcode.LOAD_VAR, result_reg="%loaded", operands=["nums"]
            ),
            IRInstruction(opcode=Opcode.CONST, result_reg="%i", operands=["0"]),
            IRInstruction(
                opcode=Opcode.LOAD_INDEX, result_reg="%elem", operands=["%loaded", "%i"]
            ),
        ]
        env = infer_types(instructions, _resolver())
        assert env.register_types["%elem"] == "Int"

    def test_seeded_type_not_overwritten_by_inference(self):
        """Seeded var type from declaration takes precedence over inferred type."""
        builder = TypeEnvironmentBuilder(
            var_types={"items": parse_type("List[String]")}
        )
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%val", operands=["obj"]),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["items", "%val"]),
        ]
        env = infer_types(instructions, _resolver(), type_env_builder=builder)
        assert env.var_types["items"] == "List[String]"
