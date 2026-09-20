"""A FUNCTION used as a reference-modifier bound must not replace the operand.

``MOVE M(1:FUNCTION LENGTH(M)) TO D`` moves a slice of ``M``; the function only
computes the slice's length. The operand serializer returned the call in place
of the ref-modified identifier, so the MOVE stored the *number* the function
returned instead of the text — silently, with no error (red-dragon-pe45).

These are the end-to-end counterparts of ``test_bridge_refmod_function_bounds``:
the bytes a COBOL program actually stores.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import first_region, run_cobol

_M = 0
_N = 10
_D = 14
_T = 24


def _program(body: list[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. REFMODFN.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 M PIC X(10) VALUE 'ABCDEFGHIJ'.",
        "01 N PIC 9(4) VALUE 4.",
        "01 D PIC X(10) VALUE SPACES.",
        "01 P PIC X(3) VALUE 'XYZ'.",
        "01 H.",
        "   05 T PIC X(5) OCCURS 3 TIMES.",
        "01 I PIC 9(2) VALUE 2.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        *body,
        "    STOP RUN.",
    ]


def _d(body: list[str]) -> str:
    vm = run_cobol(_program(body), max_steps=6000)
    return bytes(first_region(vm)[_D : _D + 10]).decode("cp037")


@covers(CobolFeature.MOVE, CobolFeature.REFERENCE_MODIFICATION)
def test_plain_ref_modified_move_is_the_baseline():
    """The shape that always worked — the FUNCTION bound is what breaks it."""
    assert _d(["    MOVE M(1:N) TO D."]) == "ABCD      "


@covers(CobolFeature.MOVE, CobolFeature.REFERENCE_MODIFICATION)
@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_function_as_the_length_bound_moves_the_slice():
    """The defect moved LENGTH(M)'s value; D held no text at all."""
    assert _d(["    MOVE M(1:FUNCTION LENGTH(M)) TO D."]) == "ABCDEFGHIJ"


@covers(CobolFeature.MOVE, CobolFeature.REFERENCE_MODIFICATION)
@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_parenthesised_function_bound_moves_the_slice():
    assert _d(["    MOVE M(1:(FUNCTION LENGTH(M) - 1)) TO D."]) == "ABCDEFGHI "


@covers(CobolFeature.MOVE, CobolFeature.REFERENCE_MODIFICATION)
@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_function_in_the_start_position_moves_the_slice():
    """P is PIC X(3), so FUNCTION LENGTH(P) is 3 and the slice is M(3:2)."""
    assert _d(["    MOVE M(FUNCTION LENGTH(P):2) TO D."]) == "CD        "


@covers(CobolFeature.STRING_VERB, CobolFeature.STRING_REF_MOD)
@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_string_sending_item_sends_the_slice():
    assert (
        _d(["    STRING M(1:FUNCTION LENGTH(M)) DELIMITED BY SIZE INTO D."])
        == "ABCDEFGHIJ"
    )


@covers(CobolFeature.MOVE, CobolFeature.REFERENCE_MODIFICATION)
@covers(CobolFeature.SUBSCRIPT_ACCESS, CobolFeature.INTRINSIC_FUNCTION)
def test_subscripted_element_that_is_also_ref_modified():
    """A subscript and a reference modifier are different constructs; keep both."""
    body = [
        "    MOVE 'VWXYZ' TO T(2)",
        "    MOVE T(I)(1:FUNCTION LENGTH(P)) TO D.",
    ]
    assert _d(body) == "VWX       "


@covers(CobolFeature.MOVE, CobolFeature.SUBSCRIPT_ACCESS)
@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_subscripted_and_ref_modified_without_a_function_is_the_baseline():
    body = [
        "    MOVE 'VWXYZ' TO T(2)",
        "    MOVE T(I)(1:N) TO D.",
    ]
    assert _d(body) == "VWXY      "


@covers(CobolFeature.MOVE, CobolFeature.INTRINSIC_FUNCTION)
def test_a_function_over_a_ref_modified_argument_still_calls_the_function():
    """Guard-rail: here the ref modifier is the ARGUMENT's, not the operand's."""
    assert _d(["    MOVE FUNCTION LOWER-CASE(M(1:4)) TO D."]) == "abcd      "
