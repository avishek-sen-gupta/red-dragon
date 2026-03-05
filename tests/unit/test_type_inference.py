"""Unit tests for the static type inference pass."""

import pytest

from interpreter.constants import TypeName
from interpreter.conversion_result import IDENTITY_CONVERSION
from interpreter.default_conversion_rules import DefaultConversionRules
from interpreter.ir import IRInstruction, Opcode
from interpreter.null_type_resolver import NullTypeResolver
from interpreter.function_signature import FunctionSignature
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

    def test_not_produces_bool(self):
        """UNOP `not` → Bool regardless of operand type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["not", "%0"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%1"] == TypeName.BOOL

    def test_bang_produces_bool(self):
        """UNOP `!` → Bool regardless of operand type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["!", "%0"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%1"] == TypeName.BOOL

    def test_hash_produces_int(self):
        """UNOP `#` (Lua length) → Int."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"hello"']),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["#", "%0"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%1"] == TypeName.INT

    def test_negation_passes_through(self):
        """UNOP `-` passes through operand type (unchanged behaviour)."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3.14"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["-", "%0"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%1"] == TypeName.FLOAT

    def test_not_on_untyped_operand_still_produces_bool(self):
        """UNOP `not` with untyped operand → Bool."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["not", "%0"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%1"] == TypeName.BOOL


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


# ---------------------------------------------------------------------------
# CALL_FUNCTION
# ---------------------------------------------------------------------------


class TestCallFunctionInference:
    def test_call_function_with_type_hint_sets_register_type(self):
        """Constructor CALL_FUNCTION with type_hint → register gets that type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["Dog", "%1", "%2"],
                type_hint="Dog",
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == "Dog"

    def test_call_function_without_type_hint_leaves_register_untyped(self):
        """Regular CALL_FUNCTION (no type_hint) → register has no type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["someFunction", "%1"],
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%0" not in env.register_types


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Return type inference via LABEL → CALL_FUNCTION
# ---------------------------------------------------------------------------


class TestReturnTypeInference:
    def test_label_with_type_hint_records_return_type(self):
        """LABEL with type_hint records the function's return type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="func_add_0", type_hint="Int"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_add_0"),
        ]
        env = infer_types(instructions, _default_resolver())
        # Return type is recorded internally — verify via full chain below
        # LABEL itself produces no register type
        assert len(env.register_types) == 0

    def test_full_chain_label_const_call_function(self):
        """LABEL → CONST func ref → CALL_FUNCTION → result register gets return type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            # Function definition with return type
            _make_inst(Opcode.BRANCH, label="end_add_0"),
            _make_inst(Opcode.LABEL, label="func_add_0", type_hint="Int"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_add_0"),
            # Store function ref: add → func_add_0
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:add@func_add_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%1"]),
            # Call add(x, y) → result in %4
            _make_inst(Opcode.CONST, result_reg="%2", operands=["3"]),
            _make_inst(Opcode.CONST, result_reg="%3", operands=["4"]),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%4",
                operands=["add", "%2", "%3"],
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%4"] == "Int"

    def test_constructor_type_hint_overrides_return_type(self):
        """CALL_FUNCTION with explicit type_hint (constructor) overrides inferred return type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.LABEL, label="func_Dog_0", type_hint="void"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_Dog_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:Dog@func_Dog_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["Dog", "%1"]),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["Dog", "%1"],
                type_hint="Dog",
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        # Explicit type_hint on CALL_FUNCTION wins
        assert env.register_types["%2"] == "Dog"

    def test_unknown_function_stays_untyped(self):
        """CALL_FUNCTION for an unknown function leaves register untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["unknownFunc", "%1"],
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%0" not in env.register_types


# ---------------------------------------------------------------------------
# Builtin return types
# ---------------------------------------------------------------------------


class TestBuiltinReturnTypes:
    def test_len_returns_int(self):
        """CALL_FUNCTION `len` → Int via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["len", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.INT

    def test_str_returns_string(self):
        """CALL_FUNCTION `str` → String via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["str", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.STRING

    def test_range_returns_array(self):
        """CALL_FUNCTION `range` → Array via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["range", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.ARRAY

    def test_int_builtin_returns_int(self):
        """CALL_FUNCTION `int` → Int via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["int", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.INT

    def test_float_builtin_returns_float(self):
        """CALL_FUNCTION `float` → Float via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["float", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.FLOAT

    def test_bool_builtin_returns_bool(self):
        """CALL_FUNCTION `bool` → Bool via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["bool", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.BOOL

    def test_abs_returns_number(self):
        """CALL_FUNCTION `abs` → Number via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["abs", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.NUMBER

    def test_unknown_function_stays_untyped_with_builtins(self):
        """Unknown function not in builtin table → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.CALL_FUNCTION, result_reg="%0", operands=["myFunc", "%1"]
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%0" not in env.register_types

    def test_type_hint_takes_precedence_over_builtin(self):
        """Explicit type_hint on CALL_FUNCTION overrides builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["len", "%1"],
                type_hint="CustomType",
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == "CustomType"

    def test_user_defined_function_takes_precedence_over_builtin(self):
        """User-defined `len` function overrides builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.LABEL, label="func_len_0", type_hint="String"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_len_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:len@func_len_0>"],
            ),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%2", operands=["len", "%3"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%2"] == "String"


# ---------------------------------------------------------------------------
# RETURN backfill
# ---------------------------------------------------------------------------


class TestReturnBackfill:
    def test_unannotated_function_returning_typed_const_gets_return_type(self):
        """Unannotated function returning a typed CONST → func_return_types populated."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_double_0"),
            _make_inst(Opcode.LABEL, label="func_double_0"),  # no type_hint
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_double_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:double@func_double_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["double", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "double" in env.func_signatures
        assert env.func_signatures["double"].return_type == TypeName.INT

    def test_call_function_picks_up_backfilled_return_type(self):
        """CALL_FUNCTION picks up the backfilled return type from RETURN."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_double_0"),
            _make_inst(Opcode.LABEL, label="func_double_0"),  # no type_hint
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_double_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:double@func_double_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["double", "%1"]),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["double", "%3"],
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%2"] == TypeName.INT

    def test_annotated_function_not_overwritten_by_return(self):
        """Annotated function's return type should NOT be overwritten by RETURN backfill."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_add_0"),
            _make_inst(Opcode.LABEL, label="func_add_0", type_hint="Float"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_add_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:add@func_add_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        # Float (from annotation) should NOT be overwritten by Int (from CONST 42)
        assert env.func_signatures["add"].return_type == "Float"

    def test_return_with_untyped_register_does_not_backfill(self):
        """RETURN with an untyped register does not backfill."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_f_0"),
            _make_inst(Opcode.LABEL, label="func_f_0"),  # no type_hint
            _make_inst(Opcode.RETURN, operands=["%0"]),  # %0 has no type
            _make_inst(Opcode.LABEL, label="end_f_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:f@func_f_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["f", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.func_signatures["f"].return_type == ""


# ---------------------------------------------------------------------------
# CALL_METHOD return types
# ---------------------------------------------------------------------------


class TestCallMethodReturnTypes:
    def test_class_method_return_type_from_typed_function(self):
        """Class with typed method → CALL_METHOD on typed object → result typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            # class Dog { getAge(): Int }
            _make_inst(Opcode.LABEL, label="class_Dog_0"),
            _make_inst(Opcode.BRANCH, label="end_getAge_0"),
            _make_inst(Opcode.LABEL, label="func_getAge_0", type_hint="Int"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_getAge_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:getAge@func_getAge_0>"],
            ),
            _make_inst(Opcode.LABEL, label="end_class_Dog_0"),
            # obj = new Dog()
            _make_inst(Opcode.NEW_OBJECT, result_reg="%2", operands=["Dog"]),
            # obj.getAge()
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%2", "getAge"],
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%3"] == "Int"

    def test_unknown_method_stays_untyped(self):
        """CALL_METHOD on unknown method → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%1",
                operands=["%0", "unknownMethod"],
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%1" not in env.register_types

    def test_fallback_to_func_return_types_for_unique_method(self):
        """CALL_METHOD falls back to func_return_types when object type unknown."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            # Define function getAge with return type Int
            _make_inst(Opcode.BRANCH, label="end_getAge_0"),
            _make_inst(Opcode.LABEL, label="func_getAge_0", type_hint="Int"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_getAge_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:getAge@func_getAge_0>"],
            ),
            # Call method on untyped object
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%2", "getAge"],
            ),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%3"] == "Int"

    def test_class_scope_reset_on_new_class(self):
        """When a new class_ label is hit, scope switches to the new class."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            # class Cat { speak(): String }
            _make_inst(Opcode.LABEL, label="class_Cat_0"),
            _make_inst(Opcode.BRANCH, label="end_speak_0"),
            _make_inst(Opcode.LABEL, label="func_speak_0", type_hint="String"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_speak_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:speak@func_speak_0>"],
            ),
            _make_inst(Opcode.LABEL, label="end_class_Cat_0"),
            # class Dog { bark(): Int }
            _make_inst(Opcode.LABEL, label="class_Dog_0"),
            _make_inst(Opcode.BRANCH, label="end_bark_0"),
            _make_inst(Opcode.LABEL, label="func_bark_0", type_hint="Int"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_bark_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%2",
                operands=["<function:bark@func_bark_0>"],
            ),
            _make_inst(Opcode.LABEL, label="end_class_Dog_0"),
            # cat.speak() → String
            _make_inst(Opcode.NEW_OBJECT, result_reg="%3", operands=["Cat"]),
            _make_inst(Opcode.CALL_METHOD, result_reg="%4", operands=["%3", "speak"]),
            # dog.bark() → Int
            _make_inst(Opcode.NEW_OBJECT, result_reg="%5", operands=["Dog"]),
            _make_inst(Opcode.CALL_METHOD, result_reg="%6", operands=["%5", "bark"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%4"] == "String"
        assert env.register_types["%6"] == "Int"


# ---------------------------------------------------------------------------
# Field type table (STORE_FIELD / LOAD_FIELD)
# ---------------------------------------------------------------------------


class TestFieldTypeTable:
    def test_store_field_then_load_field_typed(self):
        """STORE_FIELD typed value → LOAD_FIELD same class/field → typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            # Different object of same class
            _make_inst(Opcode.NEW_OBJECT, result_reg="%2", operands=["Dog"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%3", operands=["%2", "age"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%3"] == TypeName.INT

    def test_load_field_unknown_class_untyped(self):
        """LOAD_FIELD on untyped object → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%1", operands=["%0", "x"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%1" not in env.register_types

    def test_load_field_unknown_field_untyped(self):
        """LOAD_FIELD on known class but unknown field → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%2", operands=["%0", "name"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "%2" not in env.register_types

    def test_multiple_fields_on_same_class(self):
        """Multiple fields stored on same class → each loaded with correct type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=['"Rex"']),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "name", "%2"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%3", operands=["%0", "age"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%4", operands=["%0", "name"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%3"] == TypeName.INT
        assert env.register_types["%4"] == TypeName.STRING


# ---------------------------------------------------------------------------
# ALLOC_REGION / LOAD_REGION
# ---------------------------------------------------------------------------


class TestRegionInference:
    def test_alloc_region_produces_region_type(self):
        """ALLOC_REGION → register typed as 'Region'."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.ALLOC_REGION, result_reg="%0", operands=["100"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == "Region"

    def test_load_region_produces_array_type(self):
        """LOAD_REGION → register typed as Array."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.LOAD_REGION, result_reg="%0", operands=["%1", "0", "10"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.register_types["%0"] == TypeName.ARRAY


class TestImmutability:
    def test_type_environment_is_frozen(self):
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
        ]
        env = infer_types(instructions, _default_resolver())
        with pytest.raises(TypeError):
            env.register_types["%99"] = "Bogus"


# ---------------------------------------------------------------------------
# Function signatures (param types + return type)
# ---------------------------------------------------------------------------


class TestFunctionSignatures:
    def test_typed_params_collected(self):
        """LABEL → SYMBOLIC params → CONST func ref → signatures include param types."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_add_0"),
            _make_inst(Opcode.LABEL, label="func_add_0", type_hint="Int"),
            _make_inst(
                Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"], type_hint="Int"
            ),
            _make_inst(
                Opcode.SYMBOLIC, result_reg="%1", operands=["param:b"], type_hint="Int"
            ),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label="end_add_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["<function:add@func_add_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%3"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig == FunctionSignature(
            params=(("a", "Int"), ("b", "Int")), return_type="Int"
        )

    def test_untyped_params_collected_with_empty_type(self):
        """SYMBOLIC params without type_hint → param name with empty type."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_greet_0"),
            _make_inst(Opcode.LABEL, label="func_greet_0"),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:name"]),
            _make_inst(Opcode.RETURN, operands=["%1"]),
            _make_inst(Opcode.LABEL, label="end_greet_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%2",
                operands=["<function:greet@func_greet_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["greet", "%2"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "greet" in env.func_signatures
        sig = env.func_signatures["greet"]
        assert sig == FunctionSignature(params=(("name", ""),), return_type="")

    def test_no_internal_labels_in_signatures(self):
        """Internal labels like func_add_0 should NOT appear in func_signatures."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_add_0"),
            _make_inst(Opcode.LABEL, label="func_add_0", type_hint="Int"),
            _make_inst(
                Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"], type_hint="Int"
            ),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_add_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:add@func_add_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert "func_add_0" not in env.func_signatures
        assert "add" in env.func_signatures

    def test_function_with_no_params(self):
        """Function with no parameters → empty params tuple."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_main_0"),
            _make_inst(Opcode.LABEL, label="func_main_0", type_hint="void"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_main_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:main@func_main_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["main", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.func_signatures["main"] == FunctionSignature(
            params=(), return_type="void"
        )

    def test_multiple_functions(self):
        """Multiple function definitions → each gets its own signature."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            # func add
            _make_inst(Opcode.BRANCH, label="end_add_0"),
            _make_inst(Opcode.LABEL, label="func_add_0", type_hint="Int"),
            _make_inst(
                Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"], type_hint="Int"
            ),
            _make_inst(
                Opcode.SYMBOLIC, result_reg="%1", operands=["param:b"], type_hint="Int"
            ),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label="end_add_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["<function:add@func_add_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%3"]),
            # func greet
            _make_inst(Opcode.BRANCH, label="end_greet_0"),
            _make_inst(Opcode.LABEL, label="func_greet_0", type_hint="String"),
            _make_inst(
                Opcode.SYMBOLIC,
                result_reg="%4",
                operands=["param:name"],
                type_hint="String",
            ),
            _make_inst(Opcode.RETURN, operands=["%5"]),
            _make_inst(Opcode.LABEL, label="end_greet_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%6",
                operands=["<function:greet@func_greet_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["greet", "%6"]),
        ]
        env = infer_types(instructions, _default_resolver())
        assert env.func_signatures["add"] == FunctionSignature(
            params=(("a", "Int"), ("b", "Int")), return_type="Int"
        )
        assert env.func_signatures["greet"] == FunctionSignature(
            params=(("name", "String"),), return_type="String"
        )

    def test_func_signatures_is_immutable(self):
        """func_signatures should be a read-only mapping."""
        instructions = [
            _make_inst(Opcode.LABEL, label="entry"),
            _make_inst(Opcode.BRANCH, label="end_f_0"),
            _make_inst(Opcode.LABEL, label="func_f_0", type_hint="Int"),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label="end_f_0"),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["<function:f@func_f_0>"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["f", "%1"]),
        ]
        env = infer_types(instructions, _default_resolver())
        with pytest.raises(TypeError):
            env.func_signatures["bogus"] = FunctionSignature(params=(), return_type="")
