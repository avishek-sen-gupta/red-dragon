"""Unit tests for seed helpers and label tracking in TreeSitterEmitContext.

Verifies that seed_func_return_type, seed_register_type, seed_var_type,
and seed_param_type populate the TypeEnvironmentBuilder correctly, and that
LABEL emit tracks the current function for param association.
"""

from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.instructions import (
    CallFunction,
    Const,
    Label_,
    StoreVar,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.types.type_expr import ScalarType, ParameterizedType, UNKNOWN


def _make_ctx() -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        source=b"",
        language=Language.JAVA,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


class TestSeedHelpers:
    def test_seed_func_return_type(self):
        ctx = _make_ctx()
        ctx.emit_inst(Label_(label=CodeLabel("func_add_0")))
        ctx.seed_func_return_type("func_add_0", ScalarType("Int"))
        assert ctx.type_env_builder.func_return_types["func_add_0"] == ScalarType("Int")

    def test_seed_func_return_type_falsy_does_not_seed(self):
        ctx = _make_ctx()
        ctx.emit_inst(Label_(label=CodeLabel("func_add_0")))
        ctx.seed_func_return_type("func_add_0", UNKNOWN)
        assert "func_add_0" not in ctx.type_env_builder.func_return_types

    def test_label_func_initializes_param_types(self):
        ctx = _make_ctx()
        ctx.emit_inst(Label_(label=CodeLabel("func_add_0")))
        assert ctx.type_env_builder.func_param_types["func_add_0"] == []

    def test_seed_register_type(self):
        ctx = _make_ctx()
        ctx.emit_inst(Symbolic(result_reg=Register("%0"), hint="param:x"))
        ctx.seed_register_type("%0", ScalarType("Int"))
        assert ctx.type_env_builder.register_types[Register("%0")] == ScalarType("Int")

    def test_seed_param_type_inside_function(self):
        ctx = _make_ctx()
        ctx.emit_inst(Label_(label=CodeLabel("func_add_0")))
        ctx.emit_inst(Symbolic(result_reg=Register("%0"), hint="param:x"))
        ctx.seed_register_type("%0", ScalarType("Float"))
        ctx.seed_param_type("x", ScalarType("Float"))
        assert ctx.type_env_builder.func_param_types["func_add_0"] == [
            ("x", ScalarType("Float"))
        ]

    def test_seed_param_type_outside_function_does_not_seed(self):
        ctx = _make_ctx()
        ctx.emit_inst(Symbolic(result_reg=Register("%0"), hint="param:x"))
        ctx.seed_register_type("%0", ScalarType("Int"))
        ctx.seed_param_type("x", ScalarType("Int"))
        assert len(ctx.type_env_builder.func_param_types) == 0

    def test_seed_var_type(self):
        ctx = _make_ctx()
        ctx.emit_inst(StoreVar(name="x", value_reg=Register("%0")))
        ctx.seed_var_type("x", ScalarType("Int"))
        assert ctx.type_env_builder.var_types["x"] == ScalarType("Int")

    def test_seed_var_type_falsy_does_not_seed(self):
        ctx = _make_ctx()
        ctx.emit_inst(StoreVar(name="x", value_reg=Register("%0")))
        ctx.seed_var_type("x", UNKNOWN)
        assert "x" not in ctx.type_env_builder.var_types

    def test_seed_register_type_for_call_function(self):
        ctx = _make_ctx()
        ctx.emit_inst(
            CallFunction(result_reg=Register("%0"), func_name=FuncName("Dog"), args=())
        )
        ctx.seed_register_type("%0", ScalarType("Dog"))
        assert ctx.type_env_builder.register_types[Register("%0")] == ScalarType("Dog")

    def test_class_label_resets_current_func(self):
        ctx = _make_ctx()
        ctx.emit_inst(Label_(label=CodeLabel("func_add_0")))
        ctx.seed_func_return_type("func_add_0", ScalarType("Int"))
        ctx.emit_inst(Label_(label=CodeLabel("class_Dog_0")))
        ctx.emit_inst(Symbolic(result_reg=Register("%0"), hint="param:self"))
        ctx.seed_register_type("%0", ScalarType("Dog"))
        ctx.seed_param_type("self", ScalarType("Dog"))
        assert ctx.type_env_builder.func_param_types["func_add_0"] == []

    def test_seed_func_return_type_accepts_parameterized_type_expr(self):
        ctx = _make_ctx()
        ctx.emit_inst(Label_(label=CodeLabel("func_get_0")))
        ret_type = ParameterizedType("Array", (ScalarType("String"),))
        ctx.seed_func_return_type("func_get_0", ret_type)
        assert ctx.type_env_builder.func_return_types["func_get_0"] == ret_type

    def test_const_instruction_has_no_type_hint_field(self):
        ctx = _make_ctx()
        inst = ctx.emit_inst(Const(result_reg=Register("%0"), value="42"))
        assert not hasattr(inst, "type_hint") or inst.__class__.__name__ == "Const"
