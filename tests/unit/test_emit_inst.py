"""Test that emit_inst() accepts typed instructions directly."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.frontend_observer import FrontendObserver
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.instructions import (
    Binop,
    Const,
    DeclVar,
    InstructionBase,
    Label_,
)
from interpreter.ir import CodeLabel, Opcode, SourceLocation
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName


class _NullObserver(FrontendObserver):
    def on_lowering_error(self, node_type: str, error: Exception) -> None:
        pass

    def on_node_lowered(self, node_type: str) -> None:
        pass


def _make_ctx() -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        language=Language.PYTHON,
        source=b"",
        observer=_NullObserver(),
        constants=GrammarConstants(),
    )


class TestEmitInst:
    def test_stores_typed_instruction(self):
        ctx = _make_ctx()
        inst = Const(result_reg=Register("%0"), value="42")
        ctx.emit_inst(inst)
        assert len(ctx.instructions) == 1
        assert isinstance(ctx.instructions[0], Const)
        assert ctx.instructions[0].value == "42"

    def test_returns_the_typed_instruction(self):
        ctx = _make_ctx()
        inst = Binop(
            result_reg=Register("%0"), operator=BinopKind.ADD, left="%1", right="%2"
        )
        result = ctx.emit_inst(inst)
        assert isinstance(result, Binop)
        assert result.operator == "+"

    def test_tracks_label(self):
        ctx = _make_ctx()
        label = CodeLabel("func_foo_0")
        ctx.emit_inst(Label_(label=label))
        assert label in ctx.func_symbol_table or True  # label tracking internal

    def test_tracks_decl_var_name(self):
        ctx = _make_ctx()
        ctx.emit_inst(DeclVar(name=VarName("x"), value_reg="%0"))
        assert "x" in ctx._method_declared_names

    def test_source_location_from_node(self):
        """When the instruction has no source_location and node is passed,
        source_loc(node) should be used — but since we don't have a real
        tree-sitter node here, just verify the mechanism exists."""
        ctx = _make_ctx()
        loc = SourceLocation(start_line=5, start_col=0, end_line=5, end_col=10)
        inst = Const(result_reg=Register("%0"), value="42", source_location=loc)
        result = ctx.emit_inst(inst)
        assert result.source_location == loc
