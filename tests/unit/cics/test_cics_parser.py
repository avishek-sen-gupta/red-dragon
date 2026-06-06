"""Unit tests for CICS verb/options text parser."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.cics_parser import parse_exec_cics_text


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
    assert opts["TRANSID"] == "CC00"
    assert opts["COMMAREA"] == "WS-CA"
    assert opts["LENGTH"] == "16"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_send_map():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND MAP('COSGN0A') MAPSET('COSGN00') FROM(COSGN0AO) ERASE END-EXEC"
    )
    assert verb == "SEND MAP"
    assert opts["MAP"] == "COSGN0A"
    assert opts["MAPSET"] == "COSGN00"
    assert opts["FROM"] == "COSGN0AO"
    assert opts["ERASE"] is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_receive_map():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS RECEIVE MAP('COSGN0A') MAPSET('COSGN00') INTO(COSGN0AI) END-EXEC"
    )
    assert verb == "RECEIVE MAP"
    assert opts["MAP"] == "COSGN0A"
    assert opts["INTO"] == "COSGN0AI"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_send_text():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND TEXT FROM(WS-MSG) LENGTH(80) END-EXEC"
    )
    assert verb == "SEND TEXT"
    assert opts["FROM"] == "WS-MSG"
    assert opts["LENGTH"] == "80"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_read_file():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS READ FILE('ACCTDAT') INTO(WS-REC) RIDFLD(WS-KEY) "
        "KEYLENGTH(16) RESP(WS-RESP) END-EXEC"
    )
    assert verb == "READ"
    assert opts["FILE"] == "ACCTDAT"
    assert opts["INTO"] == "WS-REC"
    assert opts["RIDFLD"] == "WS-KEY"
    assert opts["RESP"] == "WS-RESP"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_xctl():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS XCTL PROGRAM(CDEMO-TO-PGM) COMMAREA(WS-CA) END-EXEC"
    )
    assert verb == "XCTL"
    assert opts["PROGRAM"] == "CDEMO-TO-PGM"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_startbr():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS STARTBR FILE('CARDDAT') RIDFLD(WS-KEY) KEYLENGTH(16) RESP(WS-RESP) END-EXEC"
    )
    assert verb == "STARTBR"
    assert opts["FILE"] == "CARDDAT"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_abend():
    verb, opts = parse_exec_cics_text("EXEC CICS ABEND ABCODE('CICS') END-EXEC")
    assert verb == "ABEND"
    assert opts["ABCODE"] == "CICS"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_handle_abend():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS HANDLE ABEND LABEL(ABEND-HANDLER) END-EXEC"
    )
    assert verb == "HANDLE ABEND"
    assert opts["LABEL"] == "ABEND-HANDLER"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_assign():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS ASSIGN APPLID(WS-APPL) SYSID(WS-SYS) END-EXEC"
    )
    assert verb == "ASSIGN"
    assert opts["APPLID"] == "WS-APPL"
    assert opts["SYSID"] == "WS-SYS"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_handle_condition():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS HANDLE CONDITION NOTFND(NOT-FOUND-RTN) ERROR(ERROR-RTN) END-EXEC"
    )
    assert verb == "HANDLE CONDITION"
    assert opts["NOTFND"] == "NOT-FOUND-RTN"
    assert opts["ERROR"] == "ERROR-RTN"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_multiline():
    verb, opts = parse_exec_cics_text(
        "EXEC CICS\n    READ FILE('ACCTDAT')\n    INTO(WS-REC)\n    RESP(WS-RESP) END-EXEC"
    )
    assert verb == "READ"
    assert opts["FILE"] == "ACCTDAT"
    assert opts["RESP"] == "WS-RESP"
