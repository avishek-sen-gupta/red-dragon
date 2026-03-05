"""Unit tests for type_hint parameter in TreeSitterEmitContext.emit()."""

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


class TestEmitTypeHint:
    def test_emit_with_type_hint_sets_field(self):
        ctx = _make_ctx()
        inst = ctx.emit(Opcode.CONST, result_reg="%0", operands=["42"], type_hint="Int")
        assert inst.type_hint == "Int"

    def test_emit_without_type_hint_defaults_to_empty(self):
        ctx = _make_ctx()
        inst = ctx.emit(Opcode.CONST, result_reg="%0", operands=["42"])
        assert inst.type_hint == ""

    def test_emit_with_empty_type_hint(self):
        ctx = _make_ctx()
        inst = ctx.emit(Opcode.CONST, result_reg="%0", operands=["42"], type_hint="")
        assert inst.type_hint == ""

    def test_type_hint_propagates_to_instructions_list(self):
        ctx = _make_ctx()
        ctx.emit(Opcode.CONST, result_reg="%0", operands=["42"], type_hint="Float")
        assert ctx.instructions[0].type_hint == "Float"

    def test_type_hint_with_custom_class(self):
        ctx = _make_ctx()
        inst = ctx.emit(
            Opcode.SYMBOLIC,
            result_reg="%0",
            operands=["param:x"],
            type_hint="MyClass",
        )
        assert inst.type_hint == "MyClass"
