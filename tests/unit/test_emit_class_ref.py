"""Unit tests for TreeSitterEmitContext.emit_class_ref() and class_symbol_table."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.constants import Language
from interpreter.class_ref import ClassRef
from interpreter.ir import Opcode


def _make_ctx(lang: Language = Language.PYTHON) -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        source=b"",
        language=lang,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


class TestEmitClassRef:
    def test_registers_in_symbol_table_no_parents(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", [], result_reg="%0")
        assert "class_Dog_0" in ctx.class_symbol_table
        ref = ctx.class_symbol_table["class_Dog_0"]
        assert ref == ClassRef(name="Dog", label="class_Dog_0", parents=())

    def test_registers_in_symbol_table_with_parents(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", ["Animal"], result_reg="%0")
        ref = ctx.class_symbol_table["class_Dog_0"]
        assert ref.parents == ("Animal",)

    def test_emits_const_with_plain_label(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", [], result_reg="%0")
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        assert len(const_insts) == 1
        assert const_insts[0].operands == ["class_Dog_0"]
        assert const_insts[0].result_reg == "%0"

    def test_no_angle_brackets_in_operand(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", ["Animal"], result_reg="%1")
        const_inst = [i for i in ctx.instructions if i.opcode == Opcode.CONST][0]
        operand = str(const_inst.operands[0])
        assert "<" not in operand
        assert ">" not in operand

    def test_multiple_registrations(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", ["Animal"], result_reg="%0")
        ctx.emit_class_ref("Cat", "class_Cat_0", [], result_reg="%1")
        assert len(ctx.class_symbol_table) == 2
        assert ctx.class_symbol_table["class_Dog_0"].name == "Dog"
        assert ctx.class_symbol_table["class_Cat_0"].name == "Cat"

    def test_parents_converted_to_tuple(self):
        """Parents are passed as a list but stored as a tuple."""
        ctx = _make_ctx()
        ctx.emit_class_ref("C", "class_C_0", ["A", "B"], result_reg="%0")
        ref = ctx.class_symbol_table["class_C_0"]
        assert isinstance(ref.parents, tuple)
        assert ref.parents == ("A", "B")
