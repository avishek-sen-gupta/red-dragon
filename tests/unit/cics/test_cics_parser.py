"""Unit tests for CICS verb/options text parser."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.cics_parser import parse_exec_cics_text, CicsOperand


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_return():
    verb, opts = parse_exec_cics_text("EXEC CICS RETURN END-EXEC")
    assert verb == "RETURN"
    assert opts == {}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_return_transid():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS RETURN TRANSID(CC00) COMMAREA(WS-CA) LENGTH(16) END-EXEC"
    )
    assert verb == "RETURN"
    assert opts["TRANSID"] == CicsOperand("CC00", False)
    assert opts["COMMAREA"] == CicsOperand("WS-CA", False)
    assert opts["LENGTH"] == CicsOperand("16", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_send_map():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND MAP('COSGN0A') MAPSET('COSGN00') FROM(COSGN0AO) ERASE END-EXEC"
    )
    assert verb == "SEND MAP"
    assert opts["MAP"] == CicsOperand("COSGN0A", True)
    assert opts["MAPSET"] == CicsOperand("COSGN00", True)
    assert opts["FROM"] == CicsOperand("COSGN0AO", False)
    assert opts["ERASE"] is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_send_map_literal_vs_data_name():
    """A quoted MAP literal and a bare MAP data-name are structurally distinct."""
    _, opts_lit = parse_exec_cics_text("EXEC CICS SEND MAP('SGNMAP') END-EXEC")
    assert opts_lit["MAP"] == CicsOperand("SGNMAP", True)

    _, opts_name = parse_exec_cics_text("EXEC CICS SEND MAP(WS-X) END-EXEC")
    assert opts_name["MAP"] == CicsOperand("WS-X", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_receive_map():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS RECEIVE MAP('COSGN0A') MAPSET('COSGN00') INTO(COSGN0AI) END-EXEC"
    )
    assert verb == "RECEIVE MAP"
    assert opts["MAP"] == CicsOperand("COSGN0A", True)
    assert opts["INTO"] == CicsOperand("COSGN0AI", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_send_text():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND TEXT FROM(WS-MSG) LENGTH(80) END-EXEC"
    )
    assert verb == "SEND TEXT"
    assert opts["FROM"] == CicsOperand("WS-MSG", False)
    assert opts["LENGTH"] == CicsOperand("80", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_read_file():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS READ FILE('ACCTDAT') INTO(WS-REC) RIDFLD(WS-KEY) "
        "KEYLENGTH(16) RESP(WS-RESP) END-EXEC"
    )
    assert verb == "READ"
    assert opts["FILE"] == CicsOperand("ACCTDAT", True)
    assert opts["INTO"] == CicsOperand("WS-REC", False)
    assert opts["RIDFLD"] == CicsOperand("WS-KEY", False)
    assert opts["RESP"] == CicsOperand("WS-RESP", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_xctl():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS XCTL PROGRAM(CDEMO-TO-PGM) COMMAREA(WS-CA) END-EXEC"
    )
    assert verb == "XCTL"
    assert opts["PROGRAM"] == CicsOperand("CDEMO-TO-PGM", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_startbr():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS STARTBR FILE('CARDDAT') RIDFLD(WS-KEY) KEYLENGTH(16) RESP(WS-RESP) END-EXEC"
    )
    assert verb == "STARTBR"
    assert opts["FILE"] == CicsOperand("CARDDAT", True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_abend():
    verb, opts = parse_exec_cics_text("EXEC CICS ABEND ABCODE('CICS') END-EXEC")
    assert verb == "ABEND"
    assert opts["ABCODE"] == CicsOperand("CICS", True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_handle_abend():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS HANDLE ABEND LABEL(ABEND-HANDLER) END-EXEC"
    )
    assert verb == "HANDLE ABEND"
    assert opts["LABEL"] == CicsOperand("ABEND-HANDLER", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_assign():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS ASSIGN APPLID(WS-APPL) SYSID(WS-SYS) END-EXEC"
    )
    assert verb == "ASSIGN"
    assert opts["APPLID"] == CicsOperand("WS-APPL", False)
    assert opts["SYSID"] == CicsOperand("WS-SYS", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_handle_condition():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS HANDLE CONDITION NOTFND(NOT-FOUND-RTN) ERROR(ERROR-RTN) END-EXEC"
    )
    assert verb == "HANDLE CONDITION"
    assert opts["NOTFND"] == CicsOperand("NOT-FOUND-RTN", False)
    assert opts["ERROR"] == CicsOperand("ERROR-RTN", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_handle_aid():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS HANDLE AID PF3(PF3-HANDLER) CLEAR(CLEAR-HANDLER) END-EXEC"
    )
    assert verb == "HANDLE AID"
    assert opts["PF3"] == CicsOperand("PF3-HANDLER", False)
    assert opts["CLEAR"] == CicsOperand("CLEAR-HANDLER", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_multiline():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS\n    READ FILE('ACCTDAT')\n    INTO(WS-REC)\n    RESP(WS-RESP) END-EXEC"
    )
    assert verb == "READ"
    assert opts["FILE"] == CicsOperand("ACCTDAT", True)
    assert opts["RESP"] == CicsOperand("WS-RESP", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_subscripted_option_value_and_nohandle():
    """Option value may be a subscripted data-name (nested parens); NOHANDLE flag."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS INQUIRE PROGRAM(CDEMO-MENU-OPT-PGMNAME(WS-OPTION)) "
        "NOHANDLE END-EXEC"
    )
    assert verb == "INQUIRE"
    # Full subscripted operand text preserved (balanced nested parens).
    assert opts["PROGRAM"] == CicsOperand("CDEMO-MENU-OPT-PGMNAME(WS-OPTION)", False)
    assert "NOHANDLE" in opts and opts["NOHANDLE"] is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_reference_modified_option_value():
    """Option value with reference modification (subscript-style nested parens)."""
    verb, opts = parse_exec_cics_text("EXEC CICS SEND TEXT FROM(WS-MSG(1:8)) END-EXEC")
    assert verb == "SEND TEXT"
    assert opts["FROM"] == CicsOperand("WS-MSG(1:8)", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_numeric_length_operand_is_not_literal():
    """A numeric operand like LENGTH(8) is a bare (non-literal) operand."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND TEXT FROM(WS-MSG) LENGTH(8) END-EXEC"
    )
    assert opts["LENGTH"] == CicsOperand("8", False)
