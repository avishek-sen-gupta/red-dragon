"""Unit tests for CICS text pre-pass."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.preprocessor import (
    inject_dfheiblk,
    substitute_dfhresp,
    apply_cics_prepass,
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
