"""A subscripted operand of an intrinsic FUNCTION must read the element the
subscript names, not occurrence 1 (red-dragon).

``lower_function_operand`` is the single entry point for MOVE, conditions
(IF/EVALUATE/PERFORM UNTIL and COMPUTE, via ``_lower_expr_dict``) and STRING, so
every one of those paths is exercised here. The tables are laid out so that the
defect's signature — every element collapsing to the first — is impossible to
mistake for a passing run.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    first_region,
    run_cobol,
)


def decode_alpha(region, offset: int, length: int) -> str:
    """Decode EBCDIC alphanumeric bytes from a memory region (code page 037)."""
    return bytes(region[offset : offset + length]).decode("cp037")


_ROWS = "AAA  BBB  CCC  DDD  EEE  FFF  GGG  "


def _program(data: list[str], body: list[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. FNSUB.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        *data,
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        *body,
        "    STOP RUN.",
    ]


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_move_of_function_of_variable_subscript_reads_each_element():
    """MOVE FUNCTION TRIM(SRC-TXT(I)) TO DST-TXT(I) copies the table elementwise.

    The defect made every destination element read occurrence 1, so the whole
    destination table came back 'AAA'.
    """
    vm = run_cobol(
        _program(
            [
                "01 SRC-TAB.",
                "   05 SRC-TXT PIC X(5) OCCURS 7 TIMES.",
                "01 DST-TAB.",
                "   05 DST-TXT PIC X(5) OCCURS 7 TIMES.",
                "01 WS-I PIC 9(2) VALUE 0.",
            ],
            [
                f"    MOVE '{_ROWS}' TO SRC-TAB",
                "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 7",
                "        MOVE FUNCTION TRIM(SRC-TXT(WS-I)) TO DST-TXT(WS-I)",
                "    END-PERFORM.",
            ],
        ),
        max_steps=6000,
    )
    assert decode_alpha(first_region(vm), 35, 35) == _ROWS


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_move_of_function_of_literal_subscript_reads_that_element():
    vm = run_cobol(
        _program(
            [
                "01 SRC-TAB.",
                "   05 SRC-TXT PIC X(5) OCCURS 7 TIMES.",
                "01 WS-OUT PIC X(5) VALUE SPACES.",
            ],
            [
                f"    MOVE '{_ROWS}' TO SRC-TAB",
                "    MOVE FUNCTION TRIM(SRC-TXT(5)) TO WS-OUT.",
            ],
        )
    )
    assert decode_alpha(first_region(vm), 35, 5) == "EEE  "


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_move_of_function_of_computed_subscript_reads_that_element():
    vm = run_cobol(
        _program(
            [
                "01 SRC-TAB.",
                "   05 SRC-TXT PIC X(5) OCCURS 7 TIMES.",
                "01 WS-OUT PIC X(5) VALUE SPACES.",
                "01 WS-I PIC 9(2) VALUE 4.",
            ],
            [
                f"    MOVE '{_ROWS}' TO SRC-TAB",
                "    MOVE FUNCTION TRIM(SRC-TXT(WS-I + 1)) TO WS-OUT.",
            ],
        )
    )
    assert decode_alpha(first_region(vm), 35, 5) == "EEE  "


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_nested_functions_keep_the_subscript_of_the_inner_operand():
    """IF FUNCTION UPPER-CASE(FUNCTION TRIM(a(I))) = ...(b(I)) finds the one
    element that differs. The defect compared occurrence 1 with occurrence 1,
    so every row reported 'same'."""
    vm = run_cobol(
        _program(
            [
                "01 A-TAB.",
                "   05 A-TXT PIC X(5) OCCURS 7 TIMES.",
                "01 B-TAB.",
                "   05 B-TXT PIC X(5) OCCURS 7 TIMES.",
                "01 R-TAB.",
                "   05 R-TXT PIC X(1) OCCURS 7 TIMES.",
                "01 WS-I PIC 9(2) VALUE 0.",
            ],
            [
                f"    MOVE '{_ROWS}' TO A-TAB",
                "    MOVE 'AAA  BBB  CCC  DDD  XXX  FFF  GGG  ' TO B-TAB",
                "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 7",
                "        IF FUNCTION UPPER-CASE(FUNCTION TRIM(A-TXT(WS-I))) =",
                "           FUNCTION UPPER-CASE(FUNCTION TRIM(B-TXT(WS-I)))",
                "            MOVE 'S' TO R-TXT(WS-I)",
                "        ELSE",
                "            MOVE 'D' TO R-TXT(WS-I)",
                "        END-IF",
                "    END-PERFORM.",
            ],
        ),
        max_steps=8000,
    )
    assert decode_alpha(first_region(vm), 70, 7) == "SSSSDSS"


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.STRING_VERB)
def test_string_sending_function_keeps_its_subscript():
    vm = run_cobol(
        _program(
            [
                "01 SRC-TAB.",
                "   05 SRC-TXT PIC X(5) OCCURS 7 TIMES.",
                "01 WS-M PIC X(8) VALUE SPACES.",
            ],
            [
                f"    MOVE '{_ROWS}' TO SRC-TAB",
                "    STRING FUNCTION TRIM(SRC-TXT(5)) ' OK'",
                "      DELIMITED BY SIZE INTO WS-M",
                "    END-STRING.",
            ],
        )
    )
    assert decode_alpha(first_region(vm), 35, 8) == "EEE OK  "


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.COMPUTE)
def test_compute_of_function_keeps_its_subscript():
    vm = run_cobol(
        _program(
            [
                "01 N-TAB.",
                "   05 N-E PIC 9(3) OCCURS 4 TIMES.",
                "01 WS-R PIC 9(4) VALUE 0.",
            ],
            [
                "    MOVE '001002003004' TO N-TAB",
                "    COMPUTE WS-R = FUNCTION NUMVAL(N-E(3)).",
            ],
        )
    )
    assert decode_zoned_unsigned(first_region(vm), 12, 4) == 3


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_two_dimensional_subscripts_in_a_function_argument():
    vm = run_cobol(
        _program(
            [
                "01 M-TAB.",
                "   05 M-ROW OCCURS 2 TIMES.",
                "      10 M-CELL PIC X(3) OCCURS 3 TIMES.",
                "01 WS-OUT PIC X(3) VALUE SPACES.",
            ],
            [
                "    MOVE 'AAABBBCCCDDDEEEFFF' TO M-TAB",
                "    MOVE FUNCTION TRIM(M-CELL(2, 2)) TO WS-OUT.",
            ],
        )
    )
    assert decode_alpha(first_region(vm), 18, 3) == "EEE"


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_genuine_two_argument_function_still_evaluates_both_arguments():
    """`FUNCTION MAX(A B)` and `FUNCTION MAX(A, (B))` are two-argument calls; the
    subscript re-join must not fuse either into a subscripted read of A."""
    vm = run_cobol(
        _program(
            [
                "01 WS-A PIC 9(4) VALUE 3.",
                "01 WS-B PIC 9(4) VALUE 7.",
                "01 WS-R PIC 9(4) VALUE 0.",
                "01 WS-S PIC 9(4) VALUE 0.",
            ],
            [
                "    COMPUTE WS-R = FUNCTION MAX(WS-A WS-B)",
                "    COMPUTE WS-S = FUNCTION MAX(WS-A, (WS-B)).",
            ],
        )
    )
    region = first_region(vm)
    assert decode_zoned_unsigned(region, 8, 4) == 7
    assert decode_zoned_unsigned(region, 12, 4) == 7
