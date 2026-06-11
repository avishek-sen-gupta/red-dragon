"""Unit tests for CICS text pre-pass."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.preprocessor import (
    inject_dfheiblk,
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
def test_apply_cics_prepass_injects_dfheiblk_and_preserves_dfhresp():
    """apply_cics_prepass injects DFHEIBLK but leaves DFHRESP literals intact.

    DFHRESP(X) is now lowered structurally by the ProLeap bridge (red-dragon-kieo);
    the pre-pass no longer performs text substitution.
    """
    source = (
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-X PIC X.\n"
        "       PROCEDURE DIVISION.\n"
        "           IF X = DFHRESP(NORMAL)\n"
        "               STOP RUN.\n"
    )
    result = apply_cics_prepass(source)
    assert "COPY DFHEIBLK." in result
    assert "DFHRESP(NORMAL)" in result


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
def test_dfhresp_table_values_are_unique():
    """No two conditions may share a code, else they'd compare-equal."""
    assert len(set(_DFHRESP_TABLE.values())) == len(_DFHRESP_TABLE)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dfhresp_unknown_sentinel_not_in_table():
    """The sentinel value must not collide with any real DFHRESP code."""
    assert _DFHRESP_UNKNOWN not in _DFHRESP_TABLE.values()
