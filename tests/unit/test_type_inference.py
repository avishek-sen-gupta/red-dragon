"""Unit tests for the static type inference pass."""

import pytest

from interpreter.constants import TypeName
from interpreter.conversion_result import IDENTITY_CONVERSION
from interpreter.default_conversion_rules import DefaultConversionRules
from interpreter.ir import IRInstruction, Opcode
from interpreter.null_type_resolver import NullTypeResolver
from interpreter.type_inference import infer_types, _infer_const_type
from interpreter.type_resolver import TypeResolver


def _make_inst(opcode, result_reg="", operands=None, type_hint="", label=""):
    return IRInstruction(
        opcode=opcode,
        result_reg=result_reg or None,
        operands=operands or [],
        type_hint=type_hint,
        label=label or None,
    )


def _default_resolver():
    return TypeResolver(DefaultConversionRules())


def _null_resolver():
    return NullTypeResolver()


# ---------------------------------------------------------------------------
# _infer_const_type
# ---------------------------------------------------------------------------


class TestInferConstType:
    def test_int_literal(self):
        assert _infer_const_type("42") == TypeName.INT

    def test_negative_int_literal(self):
        assert _infer_const_type("-7") == TypeName.INT

    def test_float_literal(self):
        assert _infer_const_type("3.14") == TypeName.FLOAT

    def test_bool_true(self):
        assert _infer_const_type("True") == TypeName.BOOL

    def test_bool_false(self):
        assert _infer_const_type("False") == TypeName.BOOL

    def test_none(self):
        assert _infer_const_type("None") == ""

    def test_func_ref(self):
        assert _infer_const_type("<function:add@func_add_0>") == ""

    def test_class_ref(self):
        assert _infer_const_type("<class:Dog@class_Dog_0>") == ""

    def test_quoted_string(self):
        assert _infer_const_type('"hello"') == TypeName.STRING

    def test_single_quoted_string(self):
        assert _infer_const_type("'world'") == TypeName.STRING

    def test_unrecognised_literal(self):
        assert _infer_const_type("some_identifier") == ""


# ---------------------------------------------------------------------------
# SYMBOLIC
# ---------------------------------------------------------------------------


class TestSymbolicInference:
    def test_symbolic_with_type_hint(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"], type_hint="Int"
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == "Int"

    def test_symbolic_without_type_hint(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%0" not in env.register_types


# ---------------------------------------------------------------------------
# CONST
# ---------------------------------------------------------------------------


class TestConstInference:
    def test_const_int(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.INT

    def test_const_float(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3.14"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.FLOAT

    def test_const_bool(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["True"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.BOOL

    def test_const_string(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"hello"']),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.STRING

    def test_const_none_not_typed(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["None"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%0" not in env.register_types

    def test_const_func_ref_not_typed(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.CONST, result_reg="%0", operands=["<function:add@func_add_0>"]
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%0" not in env.register_types


# ---------------------------------------------------------------------------
# STORE_VAR
# ---------------------------------------------------------------------------


class TestStoreVarInference:
    def test_store_var_with_explicit_type_hint(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"], type_hint="Int"),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.var_types["x"] == "Int"

    def test_store_var_inherits_register_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3.14"]),
            _make_inst(Opcode.STORE_VAR, operands=["pi", "%0"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.var_types["pi"] == TypeName.FLOAT

    def test_store_var_explicit_type_overrides_register(self):
        """Declared type takes precedence over inferred register type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"], type_hint="Float"),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.var_types["x"] == "Float"


# ---------------------------------------------------------------------------
# LOAD_VAR
# ---------------------------------------------------------------------------


class TestLoadVarInference:
    def test_load_var_inherits_variable_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"], type_hint="Int"),
            _make_inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%1"] == "Int"

    def test_load_var_unknown_variable(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.LOAD_VAR, result_reg="%0", operands=["unknown"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%0" not in env.register_types


# ---------------------------------------------------------------------------
# BINOP
# ---------------------------------------------------------------------------


class TestBinopInference:
    def test_int_plus_int(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["4"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%2"] == TypeName.INT

    def test_int_plus_float(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["1.5"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%2"] == TypeName.FLOAT

    def test_int_div_int_produces_int(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["7"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["2"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["/", "%0", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%2"] == TypeName.INT

    def test_comparison_produces_bool(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["4"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["<", "%0", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%2"] == TypeName.BOOL

    def test_untyped_operands_no_result_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["None"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["None"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%2" not in env.register_types


# ---------------------------------------------------------------------------
# UNOP
# ---------------------------------------------------------------------------


class TestUnopInference:
    def test_unop_inherits_operand_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["-", "%0"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%1"] == TypeName.INT


# ---------------------------------------------------------------------------
# NEW_OBJECT / NEW_ARRAY
# ---------------------------------------------------------------------------


class TestNewObjectArrayInference:
    def test_new_object(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == "Dog"

    def test_new_array(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%0", operands=["array", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.ARRAY


# ---------------------------------------------------------------------------
# Full chain
# ---------------------------------------------------------------------------


class TestFullChain:
    def test_const_store_load_binop_store(self):
        """CONST → STORE_VAR → LOAD_VAR → BINOP → STORE_VAR."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            # int x = 7
            _make_inst(Opcode.CONST, result_reg="%0", operands=["7"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"], type_hint="Int"),
            # int y = 2
            _make_inst(Opcode.CONST, result_reg="%1", operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "%1"], type_hint="Int"),
            # z = x / y
            _make_inst(Opcode.LOAD_VAR, result_reg="%2", operands=["x"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%3", operands=["y"]),
            _make_inst(Opcode.BINOP, result_reg="%4", operands=["/", "%2", "%3"]),
            _make_inst(Opcode.STORE_VAR, operands=["z", "%4"], type_hint="Int"),
        ]
        env = infer_types(instructions, _default_resolver())

        assert env.register_types["%0"] == TypeName.INT
        assert env.register_types["%1"] == TypeName.INT
        assert env.register_types["%2"] == "Int"
        assert env.register_types["%3"] == "Int"
        assert env.register_types["%4"] == TypeName.INT
        assert env.var_types["x"] == "Int"
        assert env.var_types["y"] == "Int"
        assert env.var_types["z"] == "Int"


# ---------------------------------------------------------------------------
# NullTypeResolver
# ---------------------------------------------------------------------------


class TestNullTypeResolver:
    def test_instruction_level_types_still_propagated(self):
        """NullTypeResolver should still propagate SYMBOLIC/CONST/STORE_VAR hints."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"], type_hint="Int"
            ),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"], type_hint="Int"),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["3.14"]),
        ]
        env = infer_types(instructions, _null_resolver())
        assert env.register_types["%0"] == "Int"
        assert env.register_types["%1"] == TypeName.FLOAT
        assert env.var_types["x"] == "Int"

    def test_binop_result_type_empty(self):
        """NullTypeResolver produces no result type for BINOP."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["7"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["2"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["/", "%0", "%1"]),
        ]
        env = infer_types(instructions, _null_resolver())
        # CONST types are still inferred
        assert env.register_types["%0"] == TypeName.INT
        assert env.register_types["%1"] == TypeName.INT
        # But BINOP result has no type (NullTypeResolver returns empty result_type)
        assert "%2" not in env.register_types


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_type_environment_is_frozen(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
        ]
        env = infer_types(instructions, _default_resolver())
        with pytest.raises(TypeError):
            env.register_types["%99"] = "Bogus"
