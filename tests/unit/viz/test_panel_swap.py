"""Tests for source/AST panel content swapping."""

from viz.panels.ast_panel import ASTPanel
from viz.panels.source_panel import SourcePanel
from viz.pipeline import ASTNode


class TestSourcePanelSwap:
    def test_set_source_updates_lines(self) -> None:
        panel = SourcePanel("line1\nline2")
        assert len(panel._lines) == 2
        panel.set_source("a\nb\nc")
        assert len(panel._lines) == 3


class TestASTPanelSwap:
    def test_set_ast_stores_new_ast(self) -> None:
        ast1 = ASTNode("module", "mod1", 1, 0, 1, 3, [])
        ast2 = ASTNode("module", "mod2", 1, 0, 2, 5, [])
        panel = ASTPanel(ast1)
        assert panel._ast is ast1
        panel.set_ast(ast2)
        assert panel._ast is ast2
