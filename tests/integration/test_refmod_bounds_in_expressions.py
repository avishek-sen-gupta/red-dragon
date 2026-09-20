"""A ref-mod bound must not replace its operand in an EXPRESSION either.

The end-to-end counterparts of ``test_bridge_refmod_bounds_in_expressions``:
the values a COBOL program actually computes when a reference modifier's bound
is an intrinsic FUNCTION (red-dragon-35do) or a ``LENGTH OF`` special register
(red-dragon-twfl). Both defects were silent — a length arrived where the sliced
value belonged, with no error.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import first_region, run_cobol

_D = 0
_O = 10


def _run(body: list[str]) -> bytearray:
    program = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. REFMODEX.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 D PIC X(10) VALUE SPACES.",
        "01 O PIC 9(4) VALUE 0.",
        "01 M PIC X(10) VALUE 'ABCDEFGHIJ'.",
        "01 N PIC 9(4) VALUE 4.",
        "01 NUMF PIC 9(6) VALUE 123456.",
        "01 I PIC 9(4) VALUE 0.",
        "01 K PIC 9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        *body,
        "    STOP RUN.",
    ]
    return first_region(run_cobol(program, max_steps=8000))


def _o(body: list[str]) -> int:
    region = _run(body)
    return int(bytes(region[_O : _O + 4]).decode("cp037"))


def _d(body: list[str]) -> str:
    return bytes(_run(body)[_D : _D + 10]).decode("cp037")


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_function_bound_inside_a_function_argument_measures_the_slice():
    """LENGTH of the 10-byte slice, not LENGTH of the bound's own result."""
    assert _o(["    COMPUTE O = FUNCTION LENGTH(M(1:FUNCTION LENGTH(M)))."]) == 10


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_function_bound_in_a_relation_compares_the_slice():
    """The defect compared the NUMBER 10 against the text, and never matched."""
    body = [
        "    IF M(1:FUNCTION LENGTH(M)) = 'ABCDEFGHIJ'",
        "        MOVE 'MATCHED' TO D",
        "    END-IF.",
    ]
    assert _d(body) == "MATCHED   "


@covers(CobolFeature.PERFORM_VARYING, CobolFeature.REFERENCE_MODIFICATION)
def test_length_of_bound_in_a_perform_varying_from_starts_at_the_slice():
    """NUMF(1:LENGTH OF N) is '1234' = 1234, not LENGTH OF N = 4."""
    body = [
        "    PERFORM VARYING I FROM NUMF(1:LENGTH OF N)",
        "            BY 1 UNTIL I > 1235",
        "        MOVE I TO K",
        "    END-PERFORM.",
        "    MOVE K TO O.",
    ]
    assert _o(body) == 1235


@covers(CobolFeature.PERFORM_VARYING, CobolFeature.REFERENCE_MODIFICATION)
def test_a_plain_bound_in_a_perform_varying_from_starts_at_the_slice():
    """A sliced FROM is a number, whatever computes its bounds."""
    body = [
        "    PERFORM VARYING I FROM NUMF(1:N) BY 1 UNTIL I > 1235",
        "        MOVE I TO K",
        "    END-PERFORM.",
        "    MOVE K TO O.",
    ]
    assert _o(body) == 1235


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_length_of_bound_in_a_function_argument_reads_the_slice():
    assert _o(["    COMPUTE O = FUNCTION MAX(NUMF(1:LENGTH OF N) 1)."]) == 1234


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_a_plain_bound_is_the_baseline():
    assert _o(["    COMPUTE O = FUNCTION MAX(NUMF(1:N) 1)."]) == 1234


@covers(CobolFeature.PERFORM_VARYING)
def test_a_plain_length_of_perform_from_still_starts_at_the_length():
    body = [
        "    PERFORM VARYING I FROM LENGTH OF N BY 1 UNTIL I > 6",
        "        MOVE I TO K",
        "    END-PERFORM.",
        "    MOVE K TO O.",
    ]
    assert _o(body) == 6


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_a_function_over_a_ref_modified_argument_still_calls_the_function():
    """Guard-rail: here the ref modifier is the ARGUMENT's, not the operand's."""
    assert _o(["    COMPUTE O = FUNCTION LENGTH(M(1:3))."]) == 3
