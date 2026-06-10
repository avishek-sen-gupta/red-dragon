from __future__ import annotations

from interpreter.cics.cics_parser import parse_exec_cics_text
from interpreter.cobol.cobol_expression import FieldRefNode, LiteralNode
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_subscripted_operand_is_structural_expr_node():
    """A data-name subscript becomes a FieldRefNode ExprNode (red-dragon-l445)."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS XCTL PROGRAM(PGM-TABLE(WS-OPTION)) END-EXEC"
    )
    op = opts["PROGRAM"]
    assert op.is_literal is False
    assert op.text == "PGM-TABLE"  # bare base, no parens
    assert op.subscripts == (FieldRefNode("WS-OPTION"),)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_numeric_subscript_is_literal_node():
    verb, opts = parse_exec_cics_text("EXEC CICS XCTL PROGRAM(PGM-TABLE(3)) END-EXEC")
    op = opts["PROGRAM"]
    assert op.text == "PGM-TABLE"
    assert op.subscripts == (LiteralNode("3"),)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_plain_name_has_no_subscripts():
    verb, opts = parse_exec_cics_text("EXEC CICS READ FILE(ACCTDAT) END-EXEC")
    assert opts["FILE"].text == "ACCTDAT"
    assert opts["FILE"].subscripts == ()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_two_subscript_operand_carries_all_subscripts():
    # The parser carries ALL subscripts structurally as ExprNodes; the
    # multi-dimensional NotImplementedError is raised later at resolve time.
    verb, opts = parse_exec_cics_text("EXEC CICS XCTL PROGRAM(TBL(I)(J)) END-EXEC")
    op = opts["PROGRAM"]
    assert op.is_literal is False
    assert op.text == "TBL"
    assert op.subscripts == (FieldRefNode("I"), FieldRefNode("J"))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_literal_unaffected():
    verb, opts = parse_exec_cics_text("EXEC CICS SEND MAP('SGNMAP') END-EXEC")
    assert opts["MAP"].is_literal is True
    assert opts["MAP"].text == "SGNMAP"
    assert opts["MAP"].subscripts == ()
