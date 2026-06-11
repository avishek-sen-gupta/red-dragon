"""Unit tests for CICS verb/options text parser."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.cics_parser import parse_exec_cics_text, CicsOperand
from interpreter.cobol.ref_mod import RefModLiteral, RefModReference
from interpreter.cobol.cobol_expression import FieldRefNode


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_return():
    verb, opts = parse_exec_cics_text("EXEC CICS RETURN END-EXEC")
    assert verb == "RETURN"
    assert opts == {}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_ignores_inline_comment_inside_exec_block():
    """A commented-out option line inside an EXEC CICS block (ProLeap surfaces
    the column-7 '*' comment as a free-format '*>' inline comment) must be
    ignored by the grammar. CardDemo COTRN02C SEND-TRNADD-SCREEN has a
    commented-out LENGTH(...) line inside its EXEC CICS RETURN. ProLeap joins
    continuation lines with newlines, so END-EXEC is on its own line after the
    comment line."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS RETURN TRANSID (WS-TRANID) COMMAREA (CARDDEMO-COMMAREA)\n"
        "*>               LENGTH(LENGTH OF CARDDEMO-COMMAREA)\n"
        "               END-EXEC"
    )
    assert verb == "RETURN"
    assert opts["TRANSID"] == CicsOperand("WS-TRANID", False)
    assert opts["COMMAREA"] == CicsOperand("CARDDEMO-COMMAREA", False)
    # The commented-out LENGTH option must NOT appear.
    assert "LENGTH" not in opts


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
    # Subscripted operand is structural: bare base + structured subscripts.
    assert opts["PROGRAM"] == CicsOperand(
        "CDEMO-MENU-OPT-PGMNAME", False, subscripts=(FieldRefNode("WS-OPTION"),)
    )
    assert "NOHANDLE" in opts and opts["NOHANDLE"] is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_reference_modified_option_value():
    """Option value with reference modification (start:length byte-slice).

    A nested group containing a ``:`` is reference modification, NOT a
    subscript: ``WS-MSG(1:8)`` is ``start=1, length=8``. It parses
    structurally into ref_mod_start/ref_mod_length (RefModLiteral) with an
    EMPTY subscripts tuple (red-dragon-6ddr ref-mod)."""
    verb, opts = parse_exec_cics_text("EXEC CICS SEND TEXT FROM(WS-MSG(1:8)) END-EXEC")
    assert verb == "SEND TEXT"
    assert opts["FROM"] == CicsOperand(
        "WS-MSG",
        False,
        ref_mod_start=RefModLiteral("1"),
        ref_mod_length=RefModLiteral("8"),
    )
    assert opts["FROM"].subscripts == ()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_reference_modified_with_data_names():
    """Ref-mod start/length may themselves be data-names (NAME → RefModReference)."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND TEXT FROM(WS-MSG(WS-A:WS-B)) END-EXEC"
    )
    assert verb == "SEND TEXT"
    assert opts["FROM"] == CicsOperand(
        "WS-MSG",
        False,
        ref_mod_start=RefModReference("WS-A"),
        ref_mod_length=RefModReference("WS-B"),
    )
    assert opts["FROM"].subscripts == ()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_numeric_length_operand_is_not_literal():
    """A numeric operand like LENGTH(8) is a bare (non-literal) operand."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND TEXT FROM(WS-MSG) LENGTH(8) END-EXEC"
    )
    assert opts["LENGTH"] == CicsOperand("8", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_send_map_with_value_keeps_map_in_opts():
    """SEND MAP where MAP carries a value: verb is 'SEND MAP', MAP stays in opts."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS SEND MAP(WS-MAPNM) MAPSET('COSGN0A') FROM(X) END-EXEC"
    )
    assert verb == "SEND MAP"
    assert opts["MAP"] == CicsOperand("WS-MAPNM", False)
    assert opts["MAPSET"] == CicsOperand("COSGN0A", True)
    assert opts["FROM"] == CicsOperand("X", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_bare_send_from_is_not_compound():
    """SEND followed by a non-second-word option stays verb 'SEND', not 'SEND MAP'."""
    verb, opts = parse_exec_cics_text("EXEC CICS SEND FROM(WS-MSG) LENGTH(8) END-EXEC")
    assert verb == "SEND"
    assert opts["FROM"] == CicsOperand("WS-MSG", False)
    assert opts["LENGTH"] == CicsOperand("8", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_case_insensitive_lowercase():
    """Lowercase envelope and verb parse identically to uppercase."""
    verb, opts = parse_exec_cics_text("exec cics read dataset('x') end-exec")
    assert verb == "READ"
    assert opts["DATASET"] == CicsOperand("x", True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_case_insensitive_mixed():
    """Mixed-case envelope parses identically; verb upper-folded to 'READ'."""
    verb, opts = parse_exec_cics_text("Exec Cics ReAd Dataset('x') End-Exec")
    assert verb == "READ"
    assert opts["DATASET"] == CicsOperand("x", True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_read_dataset_single_word_verb():
    """Canonical single-word verb with DATASET and RIDFLD."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS READ DATASET('ACCTDAT') RIDFLD(WS-KEY) END-EXEC"
    )
    assert verb == "READ"
    assert opts["DATASET"] == CicsOperand("ACCTDAT", True)
    assert opts["RIDFLD"] == CicsOperand("WS-KEY", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_leading_trailing_whitespace_envelope():
    """Whitespace around the envelope is consumed by the grammar."""
    verb, opts = parse_exec_cics_text("   EXEC CICS RETURN TRANSID(CC00) END-EXEC   ")
    assert verb == "RETURN"
    assert opts["TRANSID"] == CicsOperand("CC00", False)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_xctl_subscripted_program():
    """XCTL with subscripted PROGRAM operand preserves nested parens verbatim."""
    verb, opts = parse_exec_cics_text(
        "EXEC CICS XCTL PROGRAM(CDEMO-MENU-OPT-PGMNAME(WS-OPTION)) END-EXEC"
    )
    assert verb == "XCTL"
    assert opts["PROGRAM"] == CicsOperand(
        "CDEMO-MENU-OPT-PGMNAME", False, subscripts=(FieldRefNode("WS-OPTION"),)
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_send_map_literal_collision_guard():
    """g5gx guard: a quoted MAP literal stays is_literal=True."""
    _, opts = parse_exec_cics_text("EXEC CICS SEND MAP('SGNMAP') END-EXEC")
    assert opts["MAP"] == CicsOperand("SGNMAP", True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_empty_command_envelope_only():
    """Envelope with no verb yields empty verb and no opts (historical contract)."""
    assert parse_exec_cics_text("EXEC CICS END-EXEC") == ("", {})
    assert parse_exec_cics_text("") == ("", {})


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_two_concatenated_blocks_peels_outer_envelope_only():
    """Two EXEC CICS blocks captured as one block: only the FIRST EXEC CICS and
    the LAST END-EXEC are the envelope; inner envelope words become bare flags.

    This pins the historical first-envelope/last-envelope peeling so the real
    CardDemo (two adjacent ASSIGN blocks) keeps parsing identically.
    """
    verb, opts = parse_exec_cics_text(
        "EXEC CICS ASSIGN APPLID(APPLIDO OF COSGN0AO) END-EXEC "
        "EXEC CICS ASSIGN SYSID(SYSIDO OF COSGN0AO) END-EXEC"
    )
    assert verb == "ASSIGN"
    assert opts["APPLID"] == CicsOperand("APPLIDO OF COSGN0AO", False)
    assert opts["SYSID"] == CicsOperand("SYSIDO OF COSGN0AO", False)
    # Inner envelope words and the second verb survive as bare flags.
    assert opts["END-EXEC"] is None
    assert opts["EXEC"] is None
    assert opts["CICS"] is None
    assert opts["ASSIGN"] is None
