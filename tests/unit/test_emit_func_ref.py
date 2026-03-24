"""Unit tests for TreeSitterEmitContext.emit_func_ref() and func_symbol_table."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.constants import Language
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import Opcode, CodeLabel
from interpreter.register import Register


def _make_ctx(lang: Language = Language.PYTHON) -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        source=b"",
        language=lang,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


class TestEmitFuncRef:
    def test_registers_in_symbol_table(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("add", "func_add_0", result_reg="%0")
        assert "func_add_0" in ctx.func_symbol_table
        ref = ctx.func_symbol_table["func_add_0"]
        assert ref == FuncRef(name="add", label=CodeLabel("func_add_0"))

    def test_emits_const_with_plain_label(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("add", "func_add_0", result_reg="%0")
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        assert len(const_insts) == 1
        assert const_insts[0].operands == ["func_add_0"]
        assert str(const_insts[0].result_reg) == "%0"

    def test_plain_label_format(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("my_func", "func_my_func_0", result_reg="%1")
        const_inst = [i for i in ctx.instructions if i.opcode == Opcode.CONST][0]
        operand = str(const_inst.operands[0])
        assert operand == "func_my_func_0"

    def test_multiple_registrations(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("foo", "func_foo_0", result_reg="%0")
        ctx.emit_func_ref("bar", "func_bar_0", result_reg="%1")
        assert len(ctx.func_symbol_table) == 2
        assert ctx.func_symbol_table["func_foo_0"].name == "foo"
        assert ctx.func_symbol_table["func_bar_0"].name == "bar"

    def test_dotted_name_works(self):
        """The original regex couldn't handle dots. Symbol table can."""
        ctx = _make_ctx()
        ctx.emit_func_ref("Counter.new", "func_new_0", result_reg="%0")
        assert ctx.func_symbol_table["func_new_0"].name == "Counter.new"
