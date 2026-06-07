"""Unit tests for CICS text pre-pass."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.preprocessor import (
    inject_dfheiblk,
    substitute_dfhresp,
    apply_cics_prepass,
    _DFHRESP_TABLE,
    _DFHRESP_UNKNOWN,
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inject_dfheiblk_inserts_after_ws_section():
    source = "       WORKING-STORAGE SECTION.\n" "       01 WS-DUMMY PIC X.\n"
    result = inject_dfheiblk(source)
    lines = result.splitlines()
    assert lines[0] == "       WORKING-STORAGE SECTION."
    assert "COPY DFHEIBLK." in lines[1]
    assert "WS-DUMMY" in lines[2]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inject_dfheiblk_no_change_if_no_ws_section():
    source = "       PROCEDURE DIVISION.\n       STOP RUN.\n"
    assert inject_dfheiblk(source) == source


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inject_dfheiblk_case_insensitive():
    source = "       working-storage section.\n       01 X PIC X.\n"
    result = inject_dfheiblk(source)
    assert "COPY DFHEIBLK." in result


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_normal():
    line = "           IF WS-RESP = DFHRESP(NORMAL)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 0"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_notfnd():
    line = "           IF WS-RESP = DFHRESP(NOTFND)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 13"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_endfile():
    line = "           IF WS-RESP = DFHRESP(ENDFILE)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 20"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_multiple_on_same_line():
    line = "           MOVE DFHRESP(NORMAL) TO A DFHRESP(NOTFND) TO B"
    result = substitute_dfhresp(line)
    assert "DFHRESP" not in result
    assert "0" in result
    assert "13" in result


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_apply_cics_prepass_combines_both():
    source = (
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-X PIC X.\n"
        "       PROCEDURE DIVISION.\n"
        "           IF X = DFHRESP(NORMAL)\n"
        "               STOP RUN.\n"
    )
    result = apply_cics_prepass(source)
    assert "COPY DFHEIBLK." in result
    assert "DFHRESP" not in result
    assert "0" in result


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inject_dfheiblk_injects_only_once():
    """Malformed source with two WS sections gets exactly one injection."""
    source = (
        "       WORKING-STORAGE SECTION.\n"
        "       01 X PIC X.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 Y PIC X.\n"
    )
    result = inject_dfheiblk(source)
    assert result.count("COPY DFHEIBLK.") == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_unknown_logs_warning(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="interpreter.cics.preprocessor"):
        result = substitute_dfhresp("IF X = DFHRESP(UNKNOWNCODE)")
    assert "UNKNOWNCODE" in caplog.text
    assert "DFHRESP" not in result  # still substituted, not left as-is


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_dupkey():
    line = "           IF WS-RESP = DFHRESP(DUPKEY)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 15"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_duprec():
    line = "           IF WS-RESP = DFHRESP(DUPREC)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 14"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_case_insensitive_dupkey():
    line = "           IF WS-RESP = DFHRESP(dupkey)"
    assert substitute_dfhresp(line) == "           IF WS-RESP = 15"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_substitute_dfhresp_unknown_uses_sentinel_not_normal(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="interpreter.cics.preprocessor"):
        result = substitute_dfhresp("IF X = DFHRESP(BOGUS)")
    # Unknown must NOT alias NORMAL (0) — it gets the sentinel.
    assert result == "IF X = 9999"
    assert _DFHRESP_UNKNOWN == 9999
    assert "BOGUS" in caplog.text


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfhresp_table_values_are_unique():
    """No two conditions may share a code, else they'd compare-equal."""
    assert len(set(_DFHRESP_TABLE.values())) == len(_DFHRESP_TABLE)
