"""A parenthesised group containing an intrinsic FUNCTION must evaluate whole.

The bridge's ``serializeBasis`` probed the whole basis subtree for a
``functionCall`` rule, so a parenthesised basis collapsed to whichever FUNCTION
sat inside it and every other operand and operator in the group was discarded:
``(FUNCTION LENGTH(M) - N)`` computed ``LENGTH(M)``.

These are the end-to-end counterparts of
``test_bridge_parenthesised_function_groups`` — the values a COBOL program
actually stores, with a 40-byte field and a length of 34 so that the defect's
signature (40) and the correct answer (6) can never be confused.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import first_region, run_cobol


def decode_zoned_signed(region: bytearray, offset: int, length: int) -> int:
    """Decode a signed zoned-decimal field; the sign rides the last byte's zone."""
    digits = [region[offset + i] & 0x0F for i in range(length)]
    magnitude = sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))
    negative = (region[offset + length - 1] >> 4) == 0xD
    return -magnitude if negative else magnitude


def _program(body: list[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. PARENFN.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-MSG PIC X(40) VALUE 'HELLO'.",
        "01 WS-LEN PIC 9(4) VALUE 34.",
        "01 WS-OUT PIC S9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        *body,
        "    STOP RUN.",
    ]


def _ws_out(body: list[str]) -> int:
    vm = run_cobol(_program(body), max_steps=6000)
    return decode_zoned_signed(first_region(vm), 44, 4)


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_unparenthesised_function_subtraction_is_the_baseline():
    """The shape that always worked — the group is what breaks, not the FUNCTION."""
    assert _ws_out(["    COMPUTE WS-OUT = FUNCTION LENGTH(WS-MSG) - WS-LEN."]) == 6


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_parenthesised_function_subtraction_keeps_the_subtrahend():
    """The defect returned 40 — FUNCTION LENGTH alone, the rest discarded."""
    assert _ws_out(["    COMPUTE WS-OUT = (FUNCTION LENGTH(WS-MSG) - WS-LEN)."]) == 6


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_function_as_the_right_operand_of_a_group():
    """Parenthesising is fatal wherever the FUNCTION sits. The defect returned 40."""
    assert _ws_out(["    COMPUTE WS-OUT = (WS-LEN - FUNCTION LENGTH(WS-MSG))."]) == -6


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_used_as_an_operand_of_a_larger_expression():
    """CardDemo's centring idiom. The defect returned 21 (40 / 2 + 1)."""
    assert (
        _ws_out(["    COMPUTE WS-OUT = (FUNCTION LENGTH(WS-MSG) - WS-LEN) / 2 + 1."])
        == 4
    )


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_nested_groups():
    assert _ws_out(["    COMPUTE WS-OUT = ((FUNCTION LENGTH(WS-MSG) - WS-LEN))."]) == 6


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_in_an_if_condition():
    """The defect compared 40 > 20 and took the wrong branch."""
    assert (
        _ws_out(
            [
                "    IF (FUNCTION LENGTH(WS-MSG) - WS-LEN) > 20",
                "        MOVE 1 TO WS-OUT",
                "    ELSE",
                "        MOVE 2 TO WS-OUT",
                "    END-IF.",
            ]
        )
        == 2
    )


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_in_a_perform_until_condition():
    """Loops until WS-OUT passes LENGTH(WS-MSG) - WS-LEN, i.e. 6 — not 40."""
    assert (
        _ws_out(
            [
                "    PERFORM UNTIL WS-OUT > (FUNCTION LENGTH(WS-MSG) - WS-LEN)",
                "        ADD 1 TO WS-OUT",
                "    END-PERFORM.",
            ]
        )
        == 7
    )


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_multi_argument_function_still_evaluates_both_arguments():
    """Guard-rail: a parenthesised second argument is an argument, not a subscript."""
    assert _ws_out(["    COMPUTE WS-OUT = FUNCTION MAX(3, (7))."]) == 7
