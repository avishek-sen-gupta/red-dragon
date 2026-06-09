from __future__ import annotations

from interpreter.cics.cics_parser import parse_exec_cics_text
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_subscripted_operand_is_structural():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS XCTL PROGRAM(PGM-TABLE(WS-OPTION)) END-EXEC"
    )
    op = opts["PROGRAM"]
    assert op.is_literal is False
    assert op.text == "PGM-TABLE"  # bare base, no parens
    assert op.subscripts == ("WS-OPTION",)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_plain_name_has_no_subscripts():
    verb, opts = parse_exec_cics_text("EXEC CICS READ FILE(ACCTDAT) END-EXEC")
    assert opts["FILE"].text == "ACCTDAT"
    assert opts["FILE"].subscripts == ()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_two_subscript_operand_carries_all_subscripts():
    # The parser carries ALL subscripts structurally; the multi-dimensional
    # NotImplementedError is raised later at resolve time (resolve_field_ref's
    # concern), so assert the PARSER output here, not any raise.
    verb, opts = parse_exec_cics_text("EXEC CICS XCTL PROGRAM(TBL(I)(J)) END-EXEC")
    op = opts["PROGRAM"]
    assert op.is_literal is False
    assert op.text == "TBL"
    assert op.subscripts == ("I", "J")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_literal_unaffected():
    verb, opts = parse_exec_cics_text("EXEC CICS SEND MAP('SGNMAP') END-EXEC")
    assert opts["MAP"].is_literal is True
    assert opts["MAP"].text == "SGNMAP"
    assert opts["MAP"].subscripts == ()
