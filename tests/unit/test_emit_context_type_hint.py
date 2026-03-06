"""Unit tests for type_hint routing in TreeSitterEmitContext.emit().

Verifies that emit() populates the TypeEnvironmentBuilder instead of
setting type_hint on IRInstruction.
"""

from interpreter.constants import Language
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.ir import Opcode


def _make_ctx() -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        source=b"",
        language=Language.JAVA,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


class TestEmitTypeHintRouting:
    def test_label_func_with_type_hint_seeds_func_return_types(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.LABEL, label="func_add_0", type_hint="Int")
        assert ctx.type_env_builder.func_return_types["func_add_0"] == "Int"

    def test_label_func_without_type_hint_does_not_seed_return_type(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.LABEL, label="func_add_0")
        assert "func_add_0" not in ctx.type_env_builder.func_return_types

    def test_label_func_initializes_param_types(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.LABEL, label="func_add_0", type_hint="Int")
        assert ctx.type_env_builder.func_param_types["func_add_0"] == []

    def test_symbolic_with_type_hint_seeds_register_types(self):
        ctx = _make_ctx()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg="%0",
            operands=["param:x"],
            type_hint="Int",
        )
        assert ctx.type_env_builder.register_types["%0"] == "Int"

    def test_symbolic_param_inside_function_seeds_func_param_types(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.LABEL, label="func_add_0", type_hint="Int")
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg="%0",
            operands=["param:x"],
            type_hint="Float",
        )
        assert ctx.type_env_builder.func_param_types["func_add_0"] == [("x", "Float")]

    def test_symbolic_param_outside_function_does_not_seed_func_param_types(self):
        ctx = _make_ctx()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg="%0",
            operands=["param:x"],
            type_hint="Int",
        )
        # No function context, so func_param_types should be empty
        assert len(ctx.type_env_builder.func_param_types) == 0

    def test_store_var_with_type_hint_seeds_var_types(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.STORE_VAR, operands=["x", "%0"], type_hint="Int")
        assert ctx.type_env_builder.var_types["x"] == "Int"

    def test_store_var_without_type_hint_does_not_seed_var_types(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.STORE_VAR, operands=["x", "%0"])
        assert "x" not in ctx.type_env_builder.var_types

    def test_call_function_with_type_hint_seeds_register_types(self):
        ctx = _make_ctx()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg="%0",
            operands=["Dog"],
            type_hint="Dog",
        )
        assert ctx.type_env_builder.register_types["%0"] == "Dog"

    def test_type_hint_not_set_on_instruction(self):
        """type_hint should NOT be set on the IRInstruction anymore."""
        ctx = _make_ctx()
        inst = ctx.emit(Opcode.CONST, result_reg="%0", operands=["42"], type_hint="Int")
        assert inst.type_hint == ""

    def test_class_label_resets_current_func(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.LABEL, label="func_add_0", type_hint="Int")
        ctx.emit(Opcode.LABEL, label="class_Dog_0")
        # Symbolic after class label should not append to function params
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg="%0",
            operands=["param:self"],
            type_hint="Dog",
        )
        assert ctx.type_env_builder.func_param_types["func_add_0"] == []
