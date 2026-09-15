"""Exact COBOL fixed-point arithmetic end to end (red-dragon-4q25.1)."""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import first_region, run_cobol


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Fails loudly when PROLEAP_BRIDGE_JAR is unset."""


def _program(working_storage: list[str], procedure: list[str], max_steps: int = 5000):
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EXACT.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *working_storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *procedure,
            "    STOP RUN.",
        ],
        max_steps=max_steps,
    )


class TestEncodePaths:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_value_clause_fraction_into_integer_field_truncates(self):
        """red-dragon-bqds: VALUE 12.5 into PIC 999 stores 012, not 125."""
        vm = _program(["01 X PIC 999 VALUE 12.5."], ["    CONTINUE."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f1f2"


class TestNumericText:
    @covers(CobolFeature.CLASS_CONDITION)
    def test_tiny_implied_decimal_value_is_numeric(self):
        """str(float) rendered 1e-05, which IS NUMERIC rejected."""
        vm = _program(
            ["01 T PIC 9V9(5) VALUE 0.00001.", "01 FLAG PIC 9 VALUE 0."],
            ["    IF T IS NUMERIC", "        MOVE 1 TO FLAG", "    END-IF."],
        )
        assert first_region(vm)[6] == 0xF1


class TestIbmDivision:
    @covers(CobolFeature.COMPUTE)
    def test_receiver_decimals_keep_the_quotient_fraction(self):
        """IBM dmax = 1: 7 / 2 = 3.5, * 2 = 7.0 (stored 6.0 before)."""
        vm = _program(["01 X PIC 9V9."], ["    COMPUTE X = 7 / 2 * 2."])
        assert bytes(first_region(vm)[:2]).hex() == "f7f0"

    @covers(CobolFeature.COMPUTE)
    def test_integer_mod_idiom_still_truncates(self):
        """red-dragon-apoq regression guard: 2023 / 4 * 4 = 2020."""
        vm = _program(["01 X PIC 9(4)."], ["    COMPUTE X = 2023 / 4 * 4."])
        assert bytes(first_region(vm)[:4]).hex() == "f2f0f2f0"

    @covers(CobolFeature.COMPUTE)
    def test_one_third_into_nine_decimals(self):
        vm = _program(["01 X PIC 9V9(9)."], ["    COMPUTE X = 1 / 3."])
        assert bytes(first_region(vm)[:10]).hex() == "f0f3f3f3f3f3f3f3f3f3"

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounded_two_thirds(self):
        vm = _program(["01 X PIC 9V99."], ["    COMPUTE X ROUNDED = 2 / 3."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f6f7"


class TestExactOperators:
    @covers(CobolFeature.COMPUTE)
    def test_multiply_into_integer_receiver_is_exact(self):
        """4.35 * 100 stored 434 through float."""
        vm = _program(["01 X PIC 999."], ["    COMPUTE X = 4.35 * 100."])
        assert bytes(first_region(vm)[:3]).hex() == "f4f3f5"

    @covers(CobolFeature.COMPUTE)
    def test_point_one_plus_point_seven(self):
        vm = _program(["01 X PIC 9V99."], ["    COMPUTE X = 0.1 + 0.7."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f8f0"

    @covers(CobolFeature.USAGE_COMP_2, CobolFeature.COMPUTE)
    def test_comp2_expression_computes_in_floating_point(self):
        vm = _program(
            ["01 X PIC 9V9.", "01 D COMP-2 VALUE 1.5."],
            ["    COMPUTE X = D * 2."],
        )
        assert bytes(first_region(vm)[:2]).hex() == "f3f0"


class TestExactOperands:
    @covers(CobolFeature.ADD)
    def test_eighteen_digit_add_keeps_the_last_digit(self):
        vm = _program(
            ["01 Y PIC S9(9)V9(9) VALUE 123456789.123456788."],
            ["    ADD 0.000000001 TO Y."],
        )
        assert (
            bytes(first_region(vm)[:18]).hex() == "f1f2f3f4f5f6f7f8f9f1f2f3f4f5f6f7f8c9"
        )

    @covers(CobolFeature.USAGE_COMP)
    def test_comp_decimal_field_decodes_its_fraction(self):
        """red-dragon-0dvs (decode half)."""
        vm = _program(
            ["01 C PIC S9(5)V99 COMP VALUE 123.45.", "01 D PIC 9(5)V99."],
            ["    MOVE C TO D."],
        )
        assert bytes(first_region(vm)[:11]).hex() == "00003039f0f0f1f2f3f4f5"

    @covers(CobolFeature.USAGE_COMP)
    def test_comp_decimal_field_stores_its_fraction(self):
        """red-dragon-0dvs (store half): MOVE 123.45 stored 123."""
        vm = _program(
            ["01 C PIC S9(5)V99 COMP.", "01 D PIC 9(5)V99."],
            ["    MOVE 123.45 TO C.", "    MOVE C TO D."],
        )
        assert bytes(first_region(vm)[:11]).hex() == "00003039f0f0f1f2f3f4f5"

    @covers(CobolFeature.PIC_CLAUSE)
    def test_pic_p_field_round_trips(self):
        vm = _program(
            ["01 P PIC 999PP VALUE 12300.", "01 D PIC 9(5)."], ["    MOVE P TO D."]
        )
        assert bytes(first_region(vm)[:8]).hex() == "f1f2f3f1f2f3f0f0"

    @covers(CobolFeature.ARITHMETIC_EXPRESSION)
    def test_decimal_field_equals_decimal_literal(self):
        vm = _program(
            ["01 X PIC 9V9 VALUE 0.1.", "01 FLAG PIC 9 VALUE 0."],
            ["    IF X = 0.1", "        MOVE 1 TO FLAG", "    END-IF."],
        )
        assert first_region(vm)[2] == 0xF1


class TestBoundaryBuiltins:
    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounded_division_of_an_exact_field(self):
        vm = _program(
            ["01 X PIC 9V99.", "01 A PIC 9V99 VALUE 2.00."],
            ["    COMPUTE X ROUNDED = A / 3."],
        )
        assert bytes(first_region(vm)[:3]).hex() == "f0f6f7"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_numeric_edited_move_of_an_exact_field(self):
        vm = _program(
            ["01 E PIC ZZ9.99.", "01 A PIC 9(3)V99 VALUE 1.50."], ["    MOVE A TO E."]
        )
        assert bytes(first_region(vm)[:6]).hex() == "4040f14bf5f0"

    @covers(CobolFeature.USAGE_COMP_2)
    def test_exact_field_round_trips_through_comp2(self):
        vm = _program(
            ["01 X PIC 9V99.", "01 A PIC 9V99 VALUE 1.25.", "01 D COMP-2."],
            ["    MOVE A TO D.", "    MOVE D TO X."],
        )
        assert bytes(first_region(vm)[:3]).hex() == "f1f2f5"


class TestGuardRegression:
    """red-dragon-5b93: the 96651c84 guard rounded genuine nines up before
    truncating. With exact arithmetic the guard is gone and COBOL truncation
    is restored."""

    @covers(CobolFeature.COMPUTE)
    def test_compute_of_genuine_nines_truncates(self):
        vm = _program(["01 X PIC 9V99."], ["    COMPUTE X = 0.129999999."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f1f2"

    @covers(CobolFeature.ADD)
    def test_add_of_genuine_nines_truncates(self):
        vm = _program(
            ["01 X PIC 9V99.", "01 A PIC 9V9(9) VALUE 0.009999999."],
            ["    MOVE 0.12 TO X.", "    ADD A TO X."],
        )
        assert bytes(first_region(vm)[:3]).hex() == "f0f1f2"


class TestExactLowering:
    @covers(CobolFeature.COMPUTE, CobolFeature.ARITHMETIC_EXPRESSION)
    def test_fixed_point_operators_lower_to_exact_builtins(self):
        """Every fixed-point operator lowers to a cobol_numeric boundary
        builtin, never a Binop evaluated by the VM's operator table."""
        from interpreter.frontend import make_cobol_parser
        from interpreter.instructions import CallFunction
        from interpreter.project.cobol_compile import compile_cobol
        from tests.integration.cobol_helpers import to_fixed

        source = to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. LOWER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 A PIC 9V99 VALUE 1.25.",
                "01 X PIC 9(3)V99.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE X = A * 2 + A / 3 - 1.",
                "    STOP RUN.",
            ]
        )
        _, linked = compile_cobol(source.encode("utf-8"), parser=make_cobol_parser())
        called = {
            str(i.func_name) for i in linked.merged_ir if isinstance(i, CallFunction)
        }
        assert {
            "__cobol_multiply",
            "__cobol_add",
            "__cobol_divide",
            "__cobol_subtract",
        } <= called
