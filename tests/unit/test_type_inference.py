"""Unit tests for the static type inference pass."""

import pytest

from interpreter.constants import TypeName
from interpreter.types.coercion.conversion_result import IDENTITY_CONVERSION
from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)
from interpreter.ir import IRInstruction, Opcode, CodeLabel, NO_LABEL
from interpreter.instructions import InstructionBase
from interpreter.types.null_type_resolver import NullTypeResolver
from interpreter.types.function_kind import FunctionKind
from interpreter.types.function_signature import FunctionSignature
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.types.type_expr import (
    TypeExpr,
    ScalarType,
    ParameterizedType,
    UnionType,
    UnknownType,
    FunctionType,
    UNBOUND,
    UNKNOWN,
    parse_type,
    scalar,
    union_of,
    fn_type,
    tuple_of,
)
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.types.type_inference import infer_types, _infer_const_type
from interpreter.types.type_resolver import TypeResolver
from interpreter.register import Register


def _make_inst(
    opcode,
    result_reg="",
    operands=None,
    label=NO_LABEL,
    branch_targets: list[CodeLabel] = [],
):
    return IRInstruction(
        opcode=opcode,
        result_reg=result_reg or None,
        operands=operands or [],
        label=label,
        branch_targets=branch_targets,
    )


import re as _re

_FUNC_LABEL_RE = _re.compile(r"^func_(.+?)_(\d+)$")


def _build_func_symbol_table(
    instructions: list[InstructionBase],
) -> dict[str, FuncRef]:
    """Auto-build a func_symbol_table from CONST instructions with func_ labels."""
    table: dict[str, FuncRef] = {}
    for inst in instructions:
        if inst.opcode != Opcode.CONST or not inst.operands:
            continue
        operand = str(inst.operands[0])
        m = _FUNC_LABEL_RE.match(operand)
        if m:
            name = m.group(1)
            table[operand] = FuncRef(name=name, label=CodeLabel(operand))
    return table


def _default_resolver():
    return TypeResolver(DefaultTypeConversionRules())


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
        func_st = {"func_add_0": FuncRef(name="add", label=CodeLabel("func_add_0"))}
        assert _infer_const_type("func_add_0", func_symbol_table=func_st) == ""

    def test_class_ref(self):
        class_st = {
            "class_Dog_0": ClassRef(
                name="Dog", label=CodeLabel("class_Dog_0"), parents=()
            )
        }
        assert _infer_const_type("class_Dog_0", class_symbol_table=class_st) == ""

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
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
        ]
        builder = TypeEnvironmentBuilder(register_types={Register("%0"): scalar("Int")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "Int"

    def test_symbolic_without_type_hint(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types


# ---------------------------------------------------------------------------
# CONST
# ---------------------------------------------------------------------------


class TestConstInference:
    def test_const_int(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.INT

    def test_const_float(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3.14"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.FLOAT

    def test_const_bool(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["True"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.BOOL

    def test_const_string(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"hello"']),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.STRING

    def test_const_none_not_typed(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["None"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types

    def test_const_func_ref_not_typed(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["func_add_0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types


# ---------------------------------------------------------------------------
# STORE_VAR
# ---------------------------------------------------------------------------


class TestStoreVarInference:
    def test_store_var_with_explicit_type_hint(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
        ]
        builder = TypeEnvironmentBuilder(var_types={"x": scalar("Int")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["x"] == "Int"

    def test_store_var_inherits_register_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3.14"]),
            _make_inst(Opcode.STORE_VAR, operands=["pi", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["pi"] == TypeName.FLOAT

    def test_store_var_explicit_type_overrides_register(self):
        """Declared type (pre-seeded) takes precedence over inferred register type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
        ]
        builder = TypeEnvironmentBuilder(var_types={"x": scalar("Float")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["x"] == "Float"


# ---------------------------------------------------------------------------
# LOAD_VAR
# ---------------------------------------------------------------------------


class TestLoadVarInference:
    def test_load_var_inherits_variable_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
        ]
        builder = TypeEnvironmentBuilder(var_types={"x": scalar("Int")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == "Int"

    def test_load_var_unknown_variable(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LOAD_VAR, result_reg="%0", operands=["unknown"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types


# ---------------------------------------------------------------------------
# BINOP
# ---------------------------------------------------------------------------


class TestBinopInference:
    def test_int_plus_int(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["4"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == TypeName.INT

    def test_int_plus_float(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["1.5"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == TypeName.FLOAT

    def test_int_div_int_produces_int(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["7"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["2"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["/", "%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == TypeName.INT

    def test_comparison_produces_bool(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["4"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["<", "%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == TypeName.BOOL

    def test_untyped_operands_no_result_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["None"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["None"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%2") not in env.register_types


# ---------------------------------------------------------------------------
# UNOP
# ---------------------------------------------------------------------------


class TestUnopInference:
    def test_unop_inherits_operand_type(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["-", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.INT

    def test_not_produces_bool(self):
        """UNOP `not` → Bool regardless of operand type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["not", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.BOOL

    def test_bang_produces_bool(self):
        """UNOP `!` → Bool regardless of operand type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["!", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.BOOL

    def test_hash_produces_int(self):
        """UNOP `#` (Lua length) → Int."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"hello"']),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["#", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.INT

    def test_negation_passes_through(self):
        """UNOP `-` passes through operand type (unchanged behaviour)."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3.14"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["-", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.FLOAT

    def test_not_on_untyped_operand_still_produces_bool(self):
        """UNOP `not` with untyped operand → Bool."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["not", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.BOOL

    def test_bitwise_not_produces_int(self):
        """UNOP `~` → Int regardless of operand type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["~", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.INT

    def test_bitwise_not_on_untyped_operand_still_produces_int(self):
        """UNOP `~` with untyped operand → Int."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["~", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.INT


# ---------------------------------------------------------------------------
# NEW_OBJECT / NEW_ARRAY
# ---------------------------------------------------------------------------


class TestNewObjectArrayInference:
    def test_new_object(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "Dog"

    def test_new_array(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%0", operands=["array", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.ARRAY


# ---------------------------------------------------------------------------
# Full chain
# ---------------------------------------------------------------------------


class TestFullChain:
    def test_const_store_load_binop_store(self):
        """CONST → STORE_VAR → LOAD_VAR → BINOP → STORE_VAR."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # int x = 7
            _make_inst(Opcode.CONST, result_reg="%0", operands=["7"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            # int y = 2
            _make_inst(Opcode.CONST, result_reg="%1", operands=["2"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "%1"]),
            # z = x / y
            _make_inst(Opcode.LOAD_VAR, result_reg="%2", operands=["x"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%3", operands=["y"]),
            _make_inst(Opcode.BINOP, result_reg="%4", operands=["/", "%2", "%3"]),
            _make_inst(Opcode.STORE_VAR, operands=["z", "%4"]),
        ]
        builder = TypeEnvironmentBuilder(
            var_types={"x": scalar("Int"), "y": scalar("Int"), "z": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )

        assert env.register_types[Register("%0")] == TypeName.INT
        assert env.register_types[Register("%1")] == TypeName.INT
        assert env.register_types[Register("%2")] == "Int"
        assert env.register_types[Register("%3")] == "Int"
        assert env.register_types[Register("%4")] == TypeName.INT
        assert env.var_types["x"] == "Int"
        assert env.var_types["y"] == "Int"
        assert env.var_types["z"] == "Int"


# ---------------------------------------------------------------------------
# NullTypeResolver
# ---------------------------------------------------------------------------


class TestNullTypeResolver:
    def test_instruction_level_types_still_propagated(self):
        """NullTypeResolver should still propagate pre-seeded and CONST types."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:x"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["3.14"]),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar("Int")},
            var_types={"x": scalar("Int")},
        )
        env = infer_types(
            instructions,
            _null_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "Int"
        assert env.register_types[Register("%1")] == TypeName.FLOAT
        assert env.var_types["x"] == "Int"

    def test_binop_result_type_empty(self):
        """NullTypeResolver produces no result type for BINOP."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["7"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["2"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["/", "%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # CONST types are still inferred
        assert env.register_types[Register("%0")] == TypeName.INT
        assert env.register_types[Register("%1")] == TypeName.INT
        # But BINOP result has no type (NullTypeResolver returns empty result_type)
        assert Register("%2") not in env.register_types


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CALL_FUNCTION
# ---------------------------------------------------------------------------


class TestCallFunctionInference:
    def test_call_function_with_type_hint_sets_register_type(self):
        """Constructor CALL_FUNCTION with pre-seeded type → register gets that type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["Dog", "%1", "%2"],
            ),
        ]
        builder = TypeEnvironmentBuilder(register_types={Register("%0"): scalar("Dog")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "Dog"

    def test_call_function_without_type_hint_leaves_register_untyped(self):
        """Regular CALL_FUNCTION (no type_hint) → register has no type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["someFunction", "%1"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types


# ---------------------------------------------------------------------------
# Forward reference resolution (fixpoint)
# ---------------------------------------------------------------------------


class TestForwardReferenceResolution:
    def test_call_before_definition_resolves_return_type(self):
        """main() calls helper() which is defined later → %0 gets helper's return type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # main calls helper (defined later)
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_main_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_main_0")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["helper"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_main_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_main_0"],
            ),
            # helper defined after main
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_helper_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_helper_0")),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_helper_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["func_helper_0"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.INT

    def test_forward_ref_cascades_to_caller_return_type(self):
        """main() returns helper() result → main's return type also resolves."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_main_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_main_0")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["helper"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_main_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_main_0"],
            ),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_helper_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_helper_0")),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_helper_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["func_helper_0"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.get_func_signature("main").return_type == TypeName.INT

    def test_forward_ref_store_var_propagates(self):
        """result = helper() where helper is defined later → var_types["result"] typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["helper"]),
            _make_inst(Opcode.STORE_VAR, operands=["result", "%0"]),
            # helper defined later
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_helper_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_helper_0")),
            _make_inst(Opcode.CONST, result_reg="%1", operands=['"hello"']),
            _make_inst(Opcode.RETURN, operands=["%1"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_helper_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%2",
                operands=["func_helper_0"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.STRING
        assert env.var_types["result"] == TypeName.STRING

    def test_three_function_chain_resolves(self):
        """a() calls b() calls c() — all defined in reverse order → all resolve."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # a calls b
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_a_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_a_0")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["b"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_a_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_a_0"],
            ),
            # b calls c
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_b_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_b_0")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%2", operands=["c"]),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_b_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["func_b_0"],
            ),
            # c returns a constant
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_c_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_c_0")),
            _make_inst(Opcode.CONST, result_reg="%4", operands=["3.14"]),
            _make_inst(Opcode.RETURN, operands=["%4"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_c_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%5",
                operands=["func_c_0"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.get_func_signature("c").return_type == TypeName.FLOAT
        assert env.get_func_signature("b").return_type == TypeName.FLOAT
        assert env.get_func_signature("a").return_type == TypeName.FLOAT

    def test_no_forward_ref_converges_in_one_pass(self):
        """When all definitions precede calls, inference still works (no regression)."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_helper_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_helper_0")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_helper_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_helper_0"],
            ),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%2", operands=["helper"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == TypeName.INT


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Return type inference via LABEL → CALL_FUNCTION
# ---------------------------------------------------------------------------


class TestReturnTypeInference:
    def test_label_with_pre_seeded_return_type(self):
        """Pre-seeded func_return_types → recorded internally."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # LABEL itself produces no register type
        assert len(env.register_types) == 0

    def test_full_chain_label_const_call_function(self):
        """LABEL → CONST func ref → CALL_FUNCTION → result register gets return type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # Function definition with return type
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            # Store function ref: add → func_add_0
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_add_0"],
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
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%4")] == "Int"

    def test_constructor_pre_seeded_type_overrides_return_type(self):
        """Pre-seeded register type (constructor) overrides inferred return type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_Dog_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_Dog_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_Dog_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["Dog", "%1"]),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["Dog", "%1"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_Dog_0": scalar("void")},
            register_types={Register("%2"): scalar("Dog")},
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # Pre-seeded register type wins
        assert env.register_types[Register("%2")] == "Dog"

    def test_unknown_function_stays_untyped(self):
        """CALL_FUNCTION for an unknown function leaves register untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["unknownFunc", "%1"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types


# ---------------------------------------------------------------------------
# Builtin return types
# ---------------------------------------------------------------------------


class TestBuiltinReturnTypes:
    def test_len_returns_int(self):
        """CALL_FUNCTION `len` → Int via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["len", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.INT

    def test_str_returns_string(self):
        """CALL_FUNCTION `str` → String via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["str", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.STRING

    def test_range_returns_array(self):
        """CALL_FUNCTION `range` → Array via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["range", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.ARRAY

    def test_int_builtin_returns_int(self):
        """CALL_FUNCTION `int` → Int via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["int", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.INT

    def test_float_builtin_returns_float(self):
        """CALL_FUNCTION `float` → Float via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["float", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.FLOAT

    def test_bool_builtin_returns_bool(self):
        """CALL_FUNCTION `bool` → Bool via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["bool", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.BOOL

    def test_abs_returns_number(self):
        """CALL_FUNCTION `abs` → Number via builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%0", operands=["abs", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.NUMBER

    def test_unknown_function_stays_untyped_with_builtins(self):
        """Unknown function not in builtin table → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.CALL_FUNCTION, result_reg="%0", operands=["myFunc", "%1"]
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types

    def test_pre_seeded_type_takes_precedence_over_builtin(self):
        """Pre-seeded register type on CALL_FUNCTION overrides builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["len", "%1"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar("CustomType")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "CustomType"

    def test_user_defined_function_takes_precedence_over_builtin(self):
        """User-defined `len` function overrides builtin table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_len_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_len_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_len_0"],
            ),
            _make_inst(Opcode.CALL_FUNCTION, result_reg="%2", operands=["len", "%3"]),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_len_0": scalar("String")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == "String"


# ---------------------------------------------------------------------------
# RETURN backfill
# ---------------------------------------------------------------------------


class TestReturnBackfill:
    def test_unannotated_function_returning_typed_const_gets_return_type(self):
        """Unannotated function returning a typed CONST → func_return_types populated."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_double_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_double_0")),  # no type_hint
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_double_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_double_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["double", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert "double" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("double").return_type == TypeName.INT

    def test_call_function_picks_up_backfilled_return_type(self):
        """CALL_FUNCTION picks up the backfilled return type from RETURN."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_double_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_double_0")),  # no type_hint
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_double_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_double_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["double", "%1"]),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["double", "%3"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == TypeName.INT

    def test_annotated_function_not_overwritten_by_return(self):
        """Annotated function's return type should NOT be overwritten by RETURN backfill."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_add_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%1"]),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": scalar("Float")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # Float (from annotation) should NOT be overwritten by Int (from CONST 42)
        assert env.get_func_signature("add").return_type == "Float"

    def test_return_with_untyped_register_does_not_backfill(self):
        """RETURN with an untyped register does not backfill."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),  # no type_hint
            _make_inst(Opcode.RETURN, operands=["%0"]),  # %0 has no type
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_f_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["f", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.get_func_signature("f").return_type == ""


# ---------------------------------------------------------------------------
# CALL_METHOD return types
# ---------------------------------------------------------------------------


class TestCallMethodReturnTypes:
    def test_class_method_return_type_from_typed_function(self):
        """Class with typed method → CALL_METHOD on typed object → result typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # class Dog { getAge(): Int }
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Dog_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_getAge_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_getAge_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_getAge_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_getAge_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Dog_0")),
            # obj = new Dog()
            _make_inst(Opcode.NEW_OBJECT, result_reg="%2", operands=["Dog"]),
            # obj.getAge()
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%2", "getAge"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_getAge_0": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%3")] == "Int"

    def test_unknown_method_stays_untyped(self):
        """CALL_METHOD on unknown method → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%1",
                operands=["%0", "unknownMethod"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%1") not in env.register_types

    def test_fallback_to_func_return_types_for_unique_method(self):
        """CALL_METHOD falls back to func_return_types when object type unknown."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # Define function getAge with return type Int
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_getAge_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_getAge_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_getAge_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_getAge_0"],
            ),
            # Call method on untyped object
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%2", "getAge"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_getAge_0": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%3")] == "Int"

    def test_builtin_string_method_upper_returns_string(self):
        """CALL_METHOD .upper() on any object → String."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"hello"']),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%1",
                operands=["%0", "upper"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.STRING

    def test_builtin_string_method_split_returns_array(self):
        """CALL_METHOD .split() → Array."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"a,b,c"']),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%1",
                operands=["%0", "split"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.ARRAY

    def test_builtin_method_keys_returns_array(self):
        """CALL_METHOD .keys() → Array."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%1",
                operands=["%0", "keys"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.ARRAY

    def test_builtin_method_find_returns_int(self):
        """CALL_METHOD .find() → Int."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"hello"']),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%1",
                operands=["%0", "find"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.INT

    def test_builtin_method_startswith_returns_bool(self):
        """CALL_METHOD .startswith() → Bool."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"hello"']),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%1",
                operands=["%0", "startswith"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == TypeName.BOOL

    def test_user_defined_method_takes_priority_over_builtin(self):
        """User-defined class method return type overrides builtin method table."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Widget_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_split_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_split_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_split_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_split_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Widget_0")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%2", operands=["Widget"]),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%2", "split"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_split_0": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # User-defined Widget.split() returns Int, not the builtin Array
        assert env.register_types[Register("%3")] == "Int"

    def test_class_scope_reset_on_new_class(self):
        """When a new class_ label is hit, scope switches to the new class."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # class Cat { speak(): String }
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Cat_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_speak_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_speak_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_speak_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_speak_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Cat_0")),
            # class Dog { bark(): Int }
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Dog_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_bark_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_bark_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_bark_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%2",
                operands=["func_bark_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Dog_0")),
            # cat.speak() → String
            _make_inst(Opcode.NEW_OBJECT, result_reg="%3", operands=["Cat"]),
            _make_inst(Opcode.CALL_METHOD, result_reg="%4", operands=["%3", "speak"]),
            # dog.bark() → Int
            _make_inst(Opcode.NEW_OBJECT, result_reg="%5", operands=["Dog"]),
            _make_inst(Opcode.CALL_METHOD, result_reg="%6", operands=["%5", "bark"]),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={
                "func_speak_0": scalar("String"),
                "func_bark_0": scalar("Int"),
            }
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%4")] == "String"
        assert env.register_types[Register("%6")] == "Int"


# ---------------------------------------------------------------------------
# Field type table (STORE_FIELD / LOAD_FIELD)
# ---------------------------------------------------------------------------


class TestFieldTypeTable:
    def test_store_field_then_load_field_typed(self):
        """STORE_FIELD typed value → LOAD_FIELD same class/field → typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            # Different object of same class
            _make_inst(Opcode.NEW_OBJECT, result_reg="%2", operands=["Dog"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%3", operands=["%2", "age"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%3")] == TypeName.INT

    def test_load_field_unknown_class_untyped(self):
        """LOAD_FIELD on untyped object → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%1", operands=["%0", "x"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%1") not in env.register_types

    def test_load_field_unknown_field_untyped(self):
        """LOAD_FIELD on known class but unknown field → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%2", operands=["%0", "name"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%2") not in env.register_types

    def test_multiple_fields_on_same_class(self):
        """Multiple fields stored on same class → each loaded with correct type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=['"Rex"']),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "name", "%2"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%3", operands=["%0", "age"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%4", operands=["%0", "name"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%3")] == TypeName.INT
        assert env.register_types[Register("%4")] == TypeName.STRING


# ---------------------------------------------------------------------------
# ALLOC_REGION / LOAD_REGION
# ---------------------------------------------------------------------------


class TestRegionInference:
    def test_alloc_region_produces_region_type(self):
        """ALLOC_REGION → register typed as 'Region'."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.ALLOC_REGION, result_reg="%0", operands=["100"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "Region"

    def test_load_region_produces_array_type(self):
        """LOAD_REGION → register typed as Array."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LOAD_REGION, result_reg="%0", operands=["%1", "0", "10"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.ARRAY


class TestImmutability:
    def test_type_environment_is_frozen(self):
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        with pytest.raises(TypeError):
            env.register_types[Register("%99")] = "Bogus"


# ---------------------------------------------------------------------------
# Function signatures (param types + return type)
# ---------------------------------------------------------------------------


class TestFunctionSignatures:
    def test_typed_params_collected(self):
        """Pre-seeded func types → signatures include param types."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"]),
            _make_inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:b"]),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["func_add_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%3"]),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={
                Register("%0"): scalar("Int"),
                Register("%1"): scalar("Int"),
            },
            func_return_types={"func_add_0": scalar("Int")},
            func_param_types={
                "func_add_0": [("a", scalar("Int")), ("b", scalar("Int"))]
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig == FunctionSignature(
            params=(("a", "Int"), ("b", "Int")), return_type="Int"
        )

    def test_untyped_params_collected_with_empty_type(self):
        """SYMBOLIC params without type_hint → param name with empty type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_greet_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_greet_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:name"]),
            _make_inst(Opcode.RETURN, operands=["%1"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_greet_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%2",
                operands=["func_greet_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["greet", "%2"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert "greet" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("greet")
        assert sig == FunctionSignature(params=(("name", ""),), return_type="")

    def test_no_internal_labels_in_signatures(self):
        """Internal labels like func_add_0 should NOT appear in func_signatures."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_add_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%1"]),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar("Int")},
            func_return_types={"func_add_0": scalar("Int")},
            func_param_types={"func_add_0": [("a", scalar("Int"))]},
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert "func_add_0" not in env.method_signatures.get(UNBOUND, {})
        assert "add" in env.method_signatures.get(UNBOUND, {})

    def test_function_with_no_params(self):
        """Function with no parameters → empty params tuple."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_main_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_main_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_main_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_main_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["main", "%1"]),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_main_0": scalar("void")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.get_func_signature("main") == FunctionSignature(
            params=(), return_type="void"
        )

    def test_multiple_functions(self):
        """Multiple function definitions → each gets its own signature."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # func add
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"]),
            _make_inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:b"]),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["func_add_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%3"]),
            # func greet
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_greet_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_greet_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%4", operands=["param:name"]),
            _make_inst(Opcode.RETURN, operands=["%5"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_greet_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%6",
                operands=["func_greet_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["greet", "%6"]),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={
                Register("%0"): scalar("Int"),
                Register("%1"): scalar("Int"),
                Register("%4"): scalar("String"),
            },
            func_return_types={
                "func_add_0": scalar("Int"),
                "func_greet_0": scalar("String"),
            },
            func_param_types={
                "func_add_0": [("a", scalar("Int")), ("b", scalar("Int"))],
                "func_greet_0": [("name", scalar("String"))],
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.get_func_signature("add") == FunctionSignature(
            params=(("a", "Int"), ("b", "Int")), return_type="Int"
        )
        assert env.get_func_signature("greet") == FunctionSignature(
            params=(("name", "String"),), return_type="String"
        )

    def test_func_signatures_is_immutable(self):
        """func_signatures should be a read-only mapping."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_f_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["f", "%1"]),
        ]
        builder = TypeEnvironmentBuilder(func_return_types={"func_f_0": scalar("Int")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        with pytest.raises(TypeError):
            env.method_signatures["bogus"] = FunctionSignature(
                params=(), return_type=""
            )


# ---------------------------------------------------------------------------
# self/this typing in class methods
# ---------------------------------------------------------------------------


class TestSelfThisTyping:
    def test_param_self_inside_class_typed_as_class_name(self):
        """param:self inside class_Dog scope → register typed as 'Dog'."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Dog_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end___init___0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func___init___0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:self"]),
            _make_inst(Opcode.RETURN, operands=[]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end___init___0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%9",
                operands=["func___init___0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Dog_0")),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "Dog"

    def test_param_this_inside_class_typed_as_class_name(self):
        """param:this inside class_Cat scope → register typed as 'Cat'."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Cat_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_getAge_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_getAge_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:this"]),
            _make_inst(Opcode.RETURN, operands=[]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_getAge_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%9",
                operands=["func_getAge_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Cat_0")),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "Cat"

    def test_param_dollar_this_inside_class_typed_as_class_name(self):
        """param:$this inside class_User scope → register typed as 'User' (PHP)."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_User_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_getName_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_getName_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:$this"]),
            _make_inst(Opcode.RETURN, operands=[]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_getName_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%9",
                operands=["func_getName_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_User_0")),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == "User"

    def test_param_self_outside_class_not_typed(self):
        """param:self outside any class scope → no type assigned."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:self"]),
            _make_inst(Opcode.RETURN, operands=[]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%9",
                operands=["func_f_0"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types

    def test_self_typing_enables_field_tracking(self):
        """param:self typed → STORE_FIELD on self register → field_types populated."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Dog_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end___init___0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func___init___0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:self"]),
            _make_inst(Opcode.STORE_VAR, operands=["self", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            _make_inst(Opcode.RETURN, operands=[]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end___init___0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%9",
                operands=["func___init___0"],
            ),
            # get_age method — load self, load field
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_get_age_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_get_age_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%2", operands=["param:self"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%3", operands=["%2", "age"]),
            _make_inst(Opcode.RETURN, operands=["%3"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_get_age_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%8",
                operands=["func_get_age_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Dog_0")),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # self register typed as Dog
        assert env.register_types[Register("%0")] == "Dog"
        assert env.register_types[Register("%2")] == "Dog"
        # LOAD_FIELD on self.age → Int
        assert env.register_types[Register("%3")] == TypeName.INT

    def test_param_self_with_pre_seeded_type_uses_pre_seeded(self):
        """If param:self already has a pre-seeded type, that takes priority."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Dog_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:self"]),
            _make_inst(Opcode.RETURN, operands=[]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%9",
                operands=["func_f_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Dog_0")),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar("SpecialDog")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # Pre-seeded type takes priority over class name
        assert env.register_types[Register("%0")] == "SpecialDog"


# ---------------------------------------------------------------------------
# CALL_UNKNOWN
# ---------------------------------------------------------------------------


class TestCallUnknown:
    def test_target_resolves_to_known_function_via_var_types(self):
        """CALL_UNKNOWN target register → var_types → func_return_types → typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # Define function 'add' with return type Int
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_add_0"],
            ),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%1"]),
            # Load 'add' into a register, then CALL_UNKNOWN on it
            _make_inst(Opcode.LOAD_VAR, result_reg="%2", operands=["add"]),
            _make_inst(
                Opcode.CALL_UNKNOWN,
                result_reg="%3",
                operands=["%2", "%4"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%3")] == "Int"

    def test_target_resolves_to_builtin(self):
        """CALL_UNKNOWN target register → var_types name → builtin → typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.STORE_VAR, operands=["len", "%0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%1", operands=["len"]),
            _make_inst(
                Opcode.CALL_UNKNOWN,
                result_reg="%2",
                operands=["%1", "%3"],
            ),
        ]
        # var_types needs 'len' → store it via CONST + STORE_VAR
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:len"]),
            _make_inst(Opcode.STORE_VAR, operands=["len", "%0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%1", operands=["len"]),
            _make_inst(
                Opcode.CALL_UNKNOWN,
                result_reg="%2",
                operands=["%1", "%3"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # 'len' is in _BUILTIN_RETURN_TYPES → Int
        assert env.register_types[Register("%2")] == TypeName.INT

    def test_unknown_target_stays_untyped(self):
        """CALL_UNKNOWN with unresolvable target → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(
                Opcode.CALL_UNKNOWN,
                result_reg="%1",
                operands=["%0"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%1") not in env.register_types

    def test_no_result_reg_leaves_state_clean(self):
        """CALL_UNKNOWN without result_reg does not pollute register or var types."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CALL_UNKNOWN, operands=["%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%0") not in env.register_types
        assert len(env.var_types) == 0


# ---------------------------------------------------------------------------
# STORE_INDEX / LOAD_INDEX
# ---------------------------------------------------------------------------


class TestStoreIndexLoadIndex:
    def test_store_then_load_same_array_register(self):
        """STORE_INDEX typed value → LOAD_INDEX same array register → typed."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%0"),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["0"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%0", "%2", "%1"]),
            _make_inst(Opcode.LOAD_INDEX, result_reg="%3", operands=["%0", "%2"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%3")] == TypeName.INT

    def test_load_index_unknown_array_untyped(self):
        """LOAD_INDEX on array with no prior STORE_INDEX → untyped."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%0"),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["0"]),
            _make_inst(Opcode.LOAD_INDEX, result_reg="%2", operands=["%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%2") not in env.register_types

    def test_last_store_wins(self):
        """Multiple STORE_INDEX with different types → last one wins."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%0"),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["0"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%0", "%2", "%1"]),
            # Now store a string
            _make_inst(Opcode.CONST, result_reg="%3", operands=['"hello"']),
            _make_inst(Opcode.STORE_INDEX, operands=["%0", "%2", "%3"]),
            _make_inst(Opcode.LOAD_INDEX, result_reg="%4", operands=["%0", "%2"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%4")] == TypeName.STRING

    def test_store_index_untyped_value_no_tracking(self):
        """STORE_INDEX with untyped value → no element type tracked."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%0"),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["0"]),
            # %1 is untyped
            _make_inst(Opcode.STORE_INDEX, operands=["%0", "%2", "%1"]),
            _make_inst(Opcode.LOAD_INDEX, result_reg="%3", operands=["%0", "%2"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%3") not in env.register_types

    def test_store_index_no_result_reg(self):
        """STORE_INDEX never produces a result register."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%0"),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["0"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%0", "%2", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # STORE_INDEX should not add any new register beyond %0, %1, %2
        assert set(env.register_types.keys()) == {
            Register("%0"),
            Register("%1"),
            Register("%2"),
        }


# ---------------------------------------------------------------------------
# Variable type scoping per function
# ---------------------------------------------------------------------------


class TestVarTypeScoping:
    def test_same_var_name_different_types_in_two_functions(self):
        """Variable 'x' in function f is Int, in function g is String."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # function f: x = 42
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%1", operands=["x"]),
            _make_inst(Opcode.RETURN, operands=["%1"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f")),
            # function g: x = "hello"
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_g")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_g_1")),
            _make_inst(Opcode.CONST, result_reg="%2", operands=['"hello"']),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%2"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%3", operands=["x"]),
            _make_inst(Opcode.RETURN, operands=["%3"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_g")),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.INT
        assert env.register_types[Register("%2")] == TypeName.STRING
        # LOAD_VAR x in f should be Int, in g should be String
        assert env.register_types[Register("%1")] == TypeName.INT
        assert env.register_types[Register("%3")] == TypeName.STRING

    def test_global_var_visible_inside_function(self):
        """A top-level variable should be visible from within a function."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # global: y = 99
            _make_inst(Opcode.CONST, result_reg="%0", operands=["99"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "%0"]),
            # function f: loads y
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.LOAD_VAR, result_reg="%1", operands=["y"]),
            _make_inst(Opcode.RETURN, operands=["%1"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f")),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.INT
        # y loaded inside f should inherit the global type
        assert env.register_types[Register("%1")] == TypeName.INT

    def test_function_var_does_not_leak_to_global(self):
        """A variable defined inside a function should not affect global scope."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # function f: z = 3.14
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["3.14"]),
            _make_inst(Opcode.STORE_VAR, operands=["z", "%0"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f")),
            # global: load z (should NOT get Float from f's scope)
            _make_inst(Opcode.LOAD_VAR, result_reg="%1", operands=["z"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%0")] == TypeName.FLOAT
        # z at global scope was never defined, so %1 should have no type
        assert Register("%1") not in env.register_types


# ---------------------------------------------------------------------------
# TypeExpr emission — inference engine returns TypeExpr, not strings
# ---------------------------------------------------------------------------


class TestInferConstTypeReturnsTypeExpr:
    """_infer_const_type returns TypeExpr objects, not raw strings."""

    def test_int_literal_returns_scalar_type(self):
        result = _infer_const_type("42")
        assert isinstance(result, ScalarType)
        assert result == TypeName.INT

    def test_float_literal_returns_scalar_type(self):
        result = _infer_const_type("3.14")
        assert isinstance(result, ScalarType)
        assert result == TypeName.FLOAT

    def test_bool_literal_returns_scalar_type(self):
        result = _infer_const_type("True")
        assert isinstance(result, ScalarType)
        assert result == TypeName.BOOL

    def test_string_literal_returns_scalar_type(self):
        result = _infer_const_type('"hello"')
        assert isinstance(result, ScalarType)
        assert result == TypeName.STRING

    def test_none_returns_unknown(self):
        result = _infer_const_type("None")
        assert isinstance(result, UnknownType)
        assert result is UNKNOWN

    def test_func_ref_returns_unknown(self):
        func_st = {"func_add_0": FuncRef(name="add", label=CodeLabel("func_add_0"))}
        result = _infer_const_type("func_add_0", func_symbol_table=func_st)
        assert isinstance(result, UnknownType)

    def test_class_ref_returns_unknown(self):
        class_st = {
            "class_Dog_0": ClassRef(
                name="Dog", label=CodeLabel("class_Dog_0"), parents=()
            )
        }
        result = _infer_const_type("class_Dog_0", class_symbol_table=class_st)
        assert isinstance(result, UnknownType)

    def test_unrecognised_literal_returns_unknown(self):
        result = _infer_const_type("some_identifier")
        assert isinstance(result, UnknownType)


class TestInferenceInternalTypeExpr:
    """Verify inference engine stores TypeExpr internally, not strings."""

    def test_const_stores_type_expr_in_register(self):
        """CONST instruction should store a TypeExpr in register_types."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        reg_type = env.register_types[Register("%0")]
        assert isinstance(reg_type, TypeExpr)
        assert isinstance(reg_type, ScalarType)

    def test_new_array_then_store_index_produces_parameterized_type(self):
        """Array promotion should produce ParameterizedType, not a string."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%arr"),
            _make_inst(Opcode.CONST, result_reg="%val", operands=["42"]),
            _make_inst(Opcode.CONST, result_reg="%idx", operands=["0"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%arr", "%idx", "%val"]),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        arr_type = env.register_types[Register("%arr")]
        assert isinstance(arr_type, ParameterizedType)
        assert arr_type.constructor == "Array"
        assert arr_type.arguments == (ScalarType("Int"),)

    def test_binop_result_is_type_expr(self):
        """BINOP result type from TypeResolver should be stored as TypeExpr."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["10"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["20"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.register_types[Register("%2")], ScalarType)
        assert env.register_types[Register("%2")] == TypeName.INT

    def test_store_var_type_is_type_expr(self):
        """Variable types stored during inference should be TypeExpr."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.var_types["x"], ScalarType)
        assert env.var_types["x"] == TypeName.INT

    def test_seeded_register_type_becomes_type_expr(self):
        """Seeded string types from builder should be parsed to TypeExpr."""
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): parse_type("List[String]")}
        )
        instructions = [_make_inst(Opcode.LABEL, label=CodeLabel("entry"))]
        env = infer_types(
            instructions,
            _null_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        reg_type = env.register_types[Register("%0")]
        assert isinstance(reg_type, ParameterizedType)
        assert reg_type.constructor == "List"
        assert reg_type.arguments == (ScalarType("String"),)

    def test_seeded_var_type_becomes_type_expr(self):
        """Seeded var types from builder should be parsed to TypeExpr."""
        builder = TypeEnvironmentBuilder(
            var_types={"items": parse_type("Map[String, Int]")}
        )
        instructions = [_make_inst(Opcode.LABEL, label=CodeLabel("entry"))]
        env = infer_types(
            instructions,
            _null_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        var_type = env.var_types["items"]
        assert isinstance(var_type, ParameterizedType)
        assert var_type.constructor == "Map"

    def test_new_object_class_name_is_scalar_type(self):
        """NEW_OBJECT stores class name as ScalarType."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.register_types[Register("%0")], ScalarType)
        assert env.register_types[Register("%0")] == "Dog"

    def test_unop_fixed_type_is_type_expr(self):
        """UNOP with fixed result type (e.g., 'not' → Bool) stores TypeExpr."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["True"]),
            _make_inst(Opcode.UNOP, result_reg="%1", operands=["not", "%0"]),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.register_types[Register("%1")], ScalarType)
        assert env.register_types[Register("%1")] == TypeName.BOOL

    def test_alloc_region_is_scalar_type(self):
        """ALLOC_REGION stores 'Region' as ScalarType."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.ALLOC_REGION, result_reg="%0"),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.register_types[Register("%0")], ScalarType)
        assert env.register_types[Register("%0")] == "Region"

    def test_load_region_is_scalar_type(self):
        """LOAD_REGION stores 'Array' as ScalarType."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.ALLOC_REGION, result_reg="%0"),
            _make_inst(Opcode.LOAD_REGION, result_reg="%1", operands=["%0", "field"]),
        ]
        env = infer_types(
            instructions,
            _null_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.register_types[Register("%1")], ScalarType)
        assert env.register_types[Register("%1")] == TypeName.ARRAY


# ---------------------------------------------------------------------------
# TypeExpr keys in field_types / class_method_types (no str() roundtrip)
# ---------------------------------------------------------------------------


class TestFieldTypeTableUsesTypeExprKeys:
    """Verify field_types and class_method_types use TypeExpr keys, not strings."""

    def test_store_field_uses_type_expr_class_key(self):
        """STORE_FIELD on typed object → field lookup works with TypeExpr key."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.NEW_OBJECT, result_reg="%0", operands=["Dog"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%2", operands=["%0", "age"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # The result type should be TypeExpr, not str
        assert isinstance(env.register_types[Register("%2")], TypeExpr)
        assert env.register_types[Register("%2")] == "Int"

    def test_self_typed_field_store_uses_type_expr_key(self):
        """param:self typed as Dog → STORE_FIELD → LOAD_FIELD uses TypeExpr class key."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Dog_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end___init___0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func___init___0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:self"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["5"]),
            _make_inst(Opcode.STORE_FIELD, operands=["%0", "age", "%1"]),
            _make_inst(Opcode.RETURN, operands=[]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end___init___0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%9",
                operands=["func___init___0"],
            ),
            # get_age method
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_get_age_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_get_age_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%2", operands=["param:self"]),
            _make_inst(Opcode.LOAD_FIELD, result_reg="%3", operands=["%2", "age"]),
            _make_inst(Opcode.RETURN, operands=["%3"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_get_age_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%8",
                operands=["func_get_age_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Dog_0")),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # self registers typed as TypeExpr Dog
        assert isinstance(env.register_types[Register("%0")], ScalarType)
        assert env.register_types[Register("%0")] == "Dog"
        # LOAD_FIELD result is TypeExpr
        assert isinstance(env.register_types[Register("%3")], TypeExpr)
        assert env.register_types[Register("%3")] == "Int"

    def test_class_method_type_resolution_uses_type_expr_key(self):
        """CALL_METHOD on typed object → resolves return type via TypeExpr class key."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Cat_0")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_get_lives_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_get_lives_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_get_lives_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_get_lives_0"],
            ),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Cat_0")),
            # Call get_lives on a Cat object
            _make_inst(Opcode.NEW_OBJECT, result_reg="%2", operands=["Cat"]),
            _make_inst(
                Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%2", "get_lives"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_get_lives_0": scalar("Int")}
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # Method return type resolved as TypeExpr
        assert isinstance(env.register_types[Register("%3")], TypeExpr)
        assert env.register_types[Register("%3")] == "Int"


# ---------------------------------------------------------------------------
# Union-aware variable type widening
# ---------------------------------------------------------------------------


class TestUnionAwareVarTyping:
    """Variable assigned different types across instructions → union type."""

    def test_var_assigned_int_then_string_produces_union(self):
        """STORE_VAR x with Int, then STORE_VAR x with String → Union[Int, String]."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=['"hello"']),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.var_types["x"], UnionType)
        assert env.var_types["x"] == "Union[Int, String]"

    def test_var_assigned_same_type_twice_no_union(self):
        """STORE_VAR x with Int twice → stays Int (no trivial union)."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=["99"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["x"] == "Int"
        assert not isinstance(env.var_types["x"], UnionType)

    def test_seeded_type_not_widened_to_union(self):
        """Seeded var type from builder is NOT widened by inference."""
        builder = TypeEnvironmentBuilder(
            var_types={"items": parse_type("List[String]")}
        )
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["obj"]),
            _make_inst(Opcode.STORE_VAR, operands=["items", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["items"] == "List[String]"

    def test_three_types_produce_three_member_union(self):
        """Three different types → Union[Bool, Int, String]."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%1", operands=['"hello"']),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%1"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["True"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%2"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert isinstance(env.var_types["x"], UnionType)
        assert env.var_types["x"] == "Union[Bool, Int, String]"


# ---------------------------------------------------------------------------
# FunctionType inference from CONST function references
# ---------------------------------------------------------------------------


class TestFunctionTypeInference:
    def test_const_func_ref_infers_function_type_when_known(self):
        """CONST <function:add@func_add_0> with seeded params and return → FunctionType."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # Define function with known param types and return type
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"]),
            _make_inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:b"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["func_add_0"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={
                Register("%0"): scalar("Int"),
                Register("%1"): scalar("Int"),
            },
            func_return_types={"func_add_0": scalar("Int")},
            func_param_types={
                "func_add_0": [("a", scalar("Int")), ("b", scalar("Int"))]
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert Register("%3") in env.register_types
        expected = fn_type([scalar("Int"), scalar("Int")], scalar("Int"))
        assert env.register_types[Register("%3")] == expected

    def test_const_func_ref_no_params_known(self):
        """CONST func ref with no param types known → no FunctionType inferred."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_f_0"],
            ),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # Without known param or return types, no FunctionType is produced
        assert Register("%1") not in env.register_types

    def test_const_func_ref_only_return_known_infers_function_type(self):
        """CONST func ref with return type but no param types → FunctionType with empty params."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_g_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_g_0")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_g_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_g_0"],
            ),
        ]
        builder = TypeEnvironmentBuilder(func_return_types={"func_g_0": scalar("Int")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        # With return type known, FunctionType should be inferred
        assert Register("%1") in env.register_types
        expected = fn_type([], scalar("Int"))
        assert env.register_types[Register("%1")] == expected

    def test_call_unknown_with_function_type_uses_return_type(self):
        """CALL_UNKNOWN on register with FunctionType → result gets return_type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            # Define function
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_add_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, result_reg="%0", operands=["param:a"]),
            _make_inst(Opcode.SYMBOLIC, result_reg="%1", operands=["param:b"]),
            _make_inst(Opcode.BINOP, result_reg="%2", operands=["+", "%0", "%1"]),
            _make_inst(Opcode.RETURN, operands=["%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_add_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%3",
                operands=["func_add_0"],
            ),
            # Load add into a variable, then call via CALL_UNKNOWN
            _make_inst(Opcode.STORE_VAR, operands=["add", "%3"]),
            _make_inst(Opcode.LOAD_VAR, result_reg="%4", operands=["add"]),
            _make_inst(
                Opcode.CALL_UNKNOWN,
                result_reg="%5",
                operands=["%4", "%6", "%7"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            register_types={
                Register("%0"): scalar("Int"),
                Register("%1"): scalar("Int"),
            },
            func_return_types={"func_add_0": scalar("Int")},
            func_param_types={
                "func_add_0": [("a", scalar("Int")), ("b", scalar("Int"))]
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%5")] == "Int"

    def test_call_unknown_uses_function_type_from_register(self):
        """CALL_UNKNOWN on register with FunctionType (no var name) → uses return_type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.BRANCH, label=CodeLabel("end_f_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_f_0"],
            ),
            # Call via CALL_UNKNOWN directly on register
            _make_inst(
                Opcode.CALL_UNKNOWN,
                result_reg="%2",
                operands=["%1"],
            ),
        ]
        builder = TypeEnvironmentBuilder(func_return_types={"func_f_0": scalar("Bool")})
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == "Bool"


class TestTupleTypeInference:
    """Unit tests for tuple type inference from IR instructions."""

    def test_new_array_tuple_typed_as_tuple(self):
        """NEW_ARRAY with 'tuple' operand produces Tuple type, not Array."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["2"]),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%1", operands=["tuple", "%0"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%1")] == "Tuple"

    def test_tuple_promotion_with_element_types(self):
        """Tuple register promoted to Tuple[Int, String] after STORE_INDEX."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["2"]),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%1", operands=["tuple", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["42"]),
            _make_inst(Opcode.CONST, result_reg="%3", operands=["0"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%1", "%3", "%2"]),
            _make_inst(Opcode.CONST, result_reg="%4", operands=['"hello"']),
            _make_inst(Opcode.CONST, result_reg="%5", operands=["1"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%1", "%5", "%4"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%1"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["x"] == tuple_of(scalar("Int"), scalar("String"))

    def test_tuple_load_index_resolves_per_element(self):
        """LOAD_INDEX on a tuple at known index resolves to that element type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["2"]),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%1", operands=["tuple", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["42"]),
            _make_inst(Opcode.CONST, result_reg="%3", operands=["0"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%1", "%3", "%2"]),
            _make_inst(Opcode.CONST, result_reg="%4", operands=['"hello"']),
            _make_inst(Opcode.CONST, result_reg="%5", operands=["1"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%1", "%5", "%4"]),
            # Load element at index 0 → should be Int
            _make_inst(Opcode.CONST, result_reg="%6", operands=["0"]),
            _make_inst(Opcode.LOAD_INDEX, result_reg="%7", operands=["%1", "%6"]),
            _make_inst(Opcode.STORE_VAR, operands=["y", "%7"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["y"] == scalar("Int")

    def test_tuple_var_propagation(self):
        """Tuple element types propagate through STORE_VAR → LOAD_VAR."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["2"]),
            _make_inst(Opcode.NEW_ARRAY, result_reg="%1", operands=["tuple", "%0"]),
            _make_inst(Opcode.CONST, result_reg="%2", operands=["42"]),
            _make_inst(Opcode.CONST, result_reg="%3", operands=["0"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%1", "%3", "%2"]),
            _make_inst(Opcode.CONST, result_reg="%4", operands=['"hi"']),
            _make_inst(Opcode.CONST, result_reg="%5", operands=["1"]),
            _make_inst(Opcode.STORE_INDEX, operands=["%1", "%5", "%4"]),
            _make_inst(Opcode.STORE_VAR, operands=["t", "%1"]),
            # Load variable t into new register, then index
            _make_inst(Opcode.LOAD_VAR, result_reg="%6", operands=["t"]),
            _make_inst(Opcode.CONST, result_reg="%7", operands=["1"]),
            _make_inst(Opcode.LOAD_INDEX, result_reg="%8", operands=["%6", "%7"]),
            _make_inst(Opcode.STORE_VAR, operands=["val", "%8"]),
        ]
        env = infer_types(
            instructions,
            _default_resolver(),
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["t"] == tuple_of(scalar("Int"), scalar("String"))
        assert env.var_types["val"] == scalar("String")


class TestTypeAliasInference:
    """Unit tests for type alias resolution during inference."""

    def test_alias_resolves_in_var_type(self):
        """Variable seeded with alias name resolves to the aliased type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.STORE_VAR, operands=["x", "%0"]),
        ]
        builder = TypeEnvironmentBuilder(
            var_types={"x": scalar("UserId")},
            type_aliases={"UserId": scalar("Int")},
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["x"] == scalar("Int")

    def test_alias_resolves_transitively(self):
        """Chained aliases resolve fully: Km → Distance → Int."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["10"]),
            _make_inst(Opcode.STORE_VAR, operands=["d", "%0"]),
        ]
        builder = TypeEnvironmentBuilder(
            var_types={"d": scalar("Km")},
            type_aliases={
                "Km": scalar("Distance"),
                "Distance": scalar("Int"),
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["d"] == scalar("Int")

    def test_alias_resolves_parameterized(self):
        """Alias to parameterized type: StringMap → Map[String, String]."""
        from interpreter.types.type_expr import map_of

        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=['"key"']),
            _make_inst(Opcode.STORE_VAR, operands=["m", "%0"]),
        ]
        builder = TypeEnvironmentBuilder(
            var_types={"m": scalar("StringMap")},
            type_aliases={"StringMap": map_of(scalar("String"), scalar("String"))},
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.var_types["m"] == map_of(scalar("String"), scalar("String"))

    def test_aliases_exposed_in_environment(self):
        """TypeEnvironment includes alias registry."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
        ]
        builder = TypeEnvironmentBuilder(
            type_aliases={"UserId": scalar("Int")},
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert "UserId" in env.type_aliases
        assert env.type_aliases["UserId"] == scalar("Int")

    def test_func_return_alias_resolves(self):
        """Function return type seeded as alias resolves to concrete type."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.CONST, result_reg="%0", operands=["42"]),
            _make_inst(Opcode.RETURN, operands=["%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_f_0")),
            _make_inst(
                Opcode.CONST,
                result_reg="%1",
                operands=["func_f_0"],
            ),
            _make_inst(
                Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["f"],
            ),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_f_0": scalar("UserId")},
            type_aliases={"UserId": scalar("Int")},
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        assert env.register_types[Register("%2")] == scalar("Int")


# ---------------------------------------------------------------------------
# Class-scoped method signatures
# ---------------------------------------------------------------------------


class TestMethodSignatures:
    """method_signatures should be scoped by class TypeExpr."""

    def test_single_class_single_method(self):
        """A class with one method should appear in method_signatures."""
        instructions = [
            _make_inst(Opcode.CONST, "%0", ["<class:Calc@class_Calc_0>"]),
            _make_inst(Opcode.STORE_VAR, operands=["Calc", "%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Calc_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, "%1", ["param:this"]),
            _make_inst(Opcode.SYMBOLIC, "%2", ["param:a"]),
            _make_inst(Opcode.SYMBOLIC, "%3", ["param:b"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_add_0")),
            _make_inst(Opcode.CONST, "%4", ["func_add_0"]),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%4"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Calc_0")),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": scalar("Int")},
            func_param_types={
                "func_add_0": [
                    ("this", scalar("Calc")),
                    ("a", scalar("Int")),
                    ("b", scalar("Int")),
                ],
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        calc_type = scalar("Calc")
        assert calc_type in env.method_signatures
        sig = env.get_func_signature("add", class_name=calc_type)
        assert sig.return_type == "Int"
        assert len(sig.params) == 3
        assert sig.kind is FunctionKind.INSTANCE
        assert len(sig.callable_params) == 2  # a, b (this excluded)

    def test_overloaded_methods_accumulate(self):
        """Two methods with the same name should produce two signatures."""
        instructions = [
            _make_inst(Opcode.CONST, "%0", ["<class:Calc@class_Calc_0>"]),
            _make_inst(Opcode.STORE_VAR, operands=["Calc", "%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Calc_0")),
            # First overload: add(this, a, b) -> Int
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, "%1", ["param:this"]),
            _make_inst(Opcode.SYMBOLIC, "%2", ["param:a"]),
            _make_inst(Opcode.SYMBOLIC, "%3", ["param:b"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_add_0")),
            _make_inst(Opcode.CONST, "%4", ["func_add_0"]),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%4"]),
            # Second overload: add(this, a, b, c) -> Int
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_1")),
            _make_inst(Opcode.SYMBOLIC, "%5", ["param:this"]),
            _make_inst(Opcode.SYMBOLIC, "%6", ["param:a"]),
            _make_inst(Opcode.SYMBOLIC, "%7", ["param:b"]),
            _make_inst(Opcode.SYMBOLIC, "%8", ["param:c"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_add_1")),
            _make_inst(Opcode.CONST, "%9", ["func_add_1"]),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%9"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Calc_0")),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={
                "func_add_0": scalar("Int"),
                "func_add_1": scalar("Int"),
            },
            func_param_types={
                "func_add_0": [
                    ("this", scalar("Calc")),
                    ("a", scalar("Int")),
                    ("b", scalar("Int")),
                ],
                "func_add_1": [
                    ("this", scalar("Calc")),
                    ("a", scalar("Int")),
                    ("b", scalar("Int")),
                    ("c", scalar("Int")),
                ],
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        calc_type = scalar("Calc")
        sigs = env.method_signatures.get(calc_type, {}).get("add", [])
        assert len(sigs) == 2
        assert len(sigs[0].params) == 3  # this, a, b
        assert len(sigs[1].params) == 4  # this, a, b, c

    def test_different_classes_separate(self):
        """Methods from different classes should be in separate scopes."""
        instructions = [
            # Class Foo
            _make_inst(Opcode.CONST, "%0", ["<class:Foo@class_Foo_0>"]),
            _make_inst(Opcode.STORE_VAR, operands=["Foo", "%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Foo_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_greet_0")),
            _make_inst(Opcode.SYMBOLIC, "%1", ["param:this"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_greet_0")),
            _make_inst(Opcode.CONST, "%2", ["func_greet_0"]),
            _make_inst(Opcode.STORE_VAR, operands=["greet", "%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Foo_0")),
            # Class Bar
            _make_inst(Opcode.CONST, "%3", ["<class:Bar@class_Bar_0>"]),
            _make_inst(Opcode.STORE_VAR, operands=["Bar", "%3"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Bar_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_greet_1")),
            _make_inst(Opcode.SYMBOLIC, "%4", ["param:this"]),
            _make_inst(Opcode.SYMBOLIC, "%5", ["param:name"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_greet_1")),
            _make_inst(Opcode.CONST, "%6", ["func_greet_1"]),
            _make_inst(Opcode.STORE_VAR, operands=["greet", "%6"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Bar_0")),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={
                "func_greet_0": scalar("String"),
                "func_greet_1": scalar("String"),
            },
            func_param_types={
                "func_greet_0": [("this", scalar("Foo"))],
                "func_greet_1": [
                    ("this", scalar("Bar")),
                    ("name", scalar("String")),
                ],
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        foo_sig = env.get_func_signature("greet", class_name=scalar("Foo"))
        bar_sig = env.get_func_signature("greet", class_name=scalar("Bar"))
        assert len(foo_sig.params) == 1  # just this
        assert len(bar_sig.params) == 2  # this, name

    def test_get_func_signature_without_class_uses_flat(self):
        """get_func_signature without class_name still uses flat func_signatures."""
        instructions = [
            _make_inst(Opcode.LABEL, label=CodeLabel("func_f_0")),
            _make_inst(Opcode.SYMBOLIC, "%0", ["param:x"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_f_0")),
            _make_inst(Opcode.CONST, "%1", ["func_f_0"]),
            _make_inst(Opcode.STORE_VAR, operands=["f", "%1"]),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_f_0": scalar("Int")},
            func_param_types={"func_f_0": [("x", scalar("Int"))]},
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        sig = env.get_func_signature("f")
        assert sig.return_type == "Int"
        assert sig.kind is FunctionKind.UNBOUND


class TestFunctionKindInference:
    """Inference should set FunctionKind based on this param and class context."""

    def test_static_method_has_static_kind(self):
        """Class method without this param → STATIC."""
        instructions = [
            _make_inst(Opcode.CONST, "%0", ["<class:M@class_M_0>"]),
            _make_inst(Opcode.STORE_VAR, operands=["M", "%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_M_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_add_0")),
            _make_inst(Opcode.SYMBOLIC, "%1", ["param:a"]),
            _make_inst(Opcode.SYMBOLIC, "%2", ["param:b"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_add_0")),
            _make_inst(Opcode.CONST, "%3", ["func_add_0"]),
            _make_inst(Opcode.STORE_VAR, operands=["add", "%3"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_M_0")),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": scalar("Int")},
            func_param_types={
                "func_add_0": [("a", scalar("Int")), ("b", scalar("Int"))],
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        sig = env.get_func_signature("add", class_name=scalar("M"))
        assert sig.kind is FunctionKind.STATIC
        assert sig.callable_params == sig.params  # no this to exclude

    def test_instance_method_has_instance_kind(self):
        """Class method with this param → INSTANCE."""
        instructions = [
            _make_inst(Opcode.CONST, "%0", ["<class:Dog@class_Dog_0>"]),
            _make_inst(Opcode.STORE_VAR, operands=["Dog", "%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_Dog_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_bark_0")),
            _make_inst(Opcode.SYMBOLIC, "%1", ["param:this"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_bark_0")),
            _make_inst(Opcode.CONST, "%2", ["func_bark_0"]),
            _make_inst(Opcode.STORE_VAR, operands=["bark", "%2"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_Dog_0")),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_bark_0": scalar("String")},
            func_param_types={
                "func_bark_0": [("this", scalar("Dog"))],
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        sig = env.get_func_signature("bark", class_name=scalar("Dog"))
        assert sig.kind is FunctionKind.INSTANCE
        assert sig.callable_params == ()  # this excluded, no other params

    def test_php_dollar_this_is_instance(self):
        """PHP $this param → INSTANCE kind."""
        instructions = [
            _make_inst(Opcode.CONST, "%0", ["<class:User@class_User_0>"]),
            _make_inst(Opcode.STORE_VAR, operands=["User", "%0"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("class_User_0")),
            _make_inst(Opcode.LABEL, label=CodeLabel("func_greet_0")),
            _make_inst(Opcode.SYMBOLIC, "%1", ["param:$this"]),
            _make_inst(Opcode.SYMBOLIC, "%2", ["param:msg"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_func_greet_0")),
            _make_inst(Opcode.CONST, "%3", ["func_greet_0"]),
            _make_inst(Opcode.STORE_VAR, operands=["greet", "%3"]),
            _make_inst(Opcode.LABEL, label=CodeLabel("end_class_User_0")),
        ]
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_greet_0": scalar("String")},
            func_param_types={
                "func_greet_0": [
                    ("$this", scalar("User")),
                    ("msg", scalar("String")),
                ],
            },
        )
        env = infer_types(
            instructions,
            _default_resolver(),
            type_env_builder=builder,
            func_symbol_table=_build_func_symbol_table(instructions),
        )
        sig = env.get_func_signature("greet", class_name=scalar("User"))
        assert sig.kind is FunctionKind.INSTANCE
        assert sig.callable_params == (("msg", scalar("String")),)
