"""ADD/SUBTRACT/MULTIPLY/DIVIDE with several sending operands and receivers."""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    decode_zoned_unsigned,
    first_region,
    run_cobol,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Fails loudly when PROLEAP_BRIDGE_JAR is unset."""


def _two_digit_fields(working_storage: list[str], procedure: list[str]) -> list[int]:
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. MULTI.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *working_storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *procedure,
            "    STOP RUN.",
        ],
        max_steps=5000,
    )
    region = first_region(vm)
    return [
        decode_zoned_unsigned(region, 2 * index, 2)
        for index in range(len(working_storage))
    ]


class TestMultiOperandAdd:
    @covers(CobolFeature.ADD, CobolFeature.ROUNDED_CLAUSE)
    def test_every_addend_is_summed_into_every_receiver(self):
        fields = _two_digit_fields(
            [
                "01 A PIC 99 VALUE 2.",
                "01 B PIC 99 VALUE 3.",
                "01 C PIC 99 VALUE 10.",
                "01 D PIC 99 VALUE 20.",
                "01 X PIC 99 VALUE 0.",
                "01 Y PIC 99 VALUE 0.",
            ],
            ["    ADD A B 4 TO C D.", "    ADD A B .5 TO X Y ROUNDED."],
        )
        assert fields == [2, 3, 19, 29, 5, 6]

    @covers(CobolFeature.ADD, CobolFeature.GIVING_CLAUSE, CobolFeature.ROUNDED_CLAUSE)
    def test_giving_stores_the_sum_of_every_operand_in_every_receiver(self):
        fields = _two_digit_fields(
            [
                "01 A PIC 99 VALUE 2.",
                "01 B PIC 99 VALUE 3.",
                "01 G PIC 99 VALUE 0.",
                "01 H PIC 99 VALUE 0.",
                "01 M PIC 99 VALUE 0.",
            ],
            ["    ADD A B .5 GIVING G H ROUNDED.", "    ADD A 1 TO B GIVING M."],
        )
        assert fields == [2, 3, 5, 6, 6]

    @covers(CobolFeature.ADD, CobolFeature.GIVING_CLAUSE, CobolFeature.ROUNDED_CLAUSE)
    def test_a_numeric_literal_after_the_first_addend_is_an_operand(self):
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MULTI.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 A PIC 9V9(6) VALUE 1.",
                "01 B PIC 9V9(6) VALUE 0.333333.",
                "01 X PIC 9(6)V9(6) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD B 333333 A GIVING X ROUNDED.",
                "    STOP RUN.",
            ],
            max_steps=5000,
        )
        assert bytes(first_region(vm)[14:26]).decode("cp037") == "333334333333"


class TestMultiOperandSubtract:
    @covers(CobolFeature.SUBTRACT, CobolFeature.GIVING_CLAUSE)
    def test_every_subtrahend_is_taken_from_every_receiver(self):
        fields = _two_digit_fields(
            [
                "01 A PIC 99 VALUE 2.",
                "01 B PIC 99 VALUE 3.",
                "01 C PIC 99 VALUE 10.",
                "01 D PIC 99 VALUE 20.",
                "01 E PIC 99 VALUE 0.",
                "01 F PIC 99 VALUE 0.",
            ],
            ["    SUBTRACT A B 1 FROM C D.", "    SUBTRACT A B FROM 50 GIVING E F."],
        )
        assert fields == [2, 3, 4, 14, 45, 45]


class TestMultipleReceivers:
    @covers(CobolFeature.MULTIPLY, CobolFeature.DIVIDE, CobolFeature.ROUNDED_CLAUSE)
    def test_multiply_and_divide_update_every_receiver(self):
        fields = _two_digit_fields(
            [
                "01 M PIC 99 VALUE 3.",
                "01 R1 PIC 99 VALUE 2.",
                "01 R2 PIC 99 VALUE 5.",
                "01 D PIC 99 VALUE 4.",
                "01 Q1 PIC 99 VALUE 10.",
                "01 Q2 PIC 99 VALUE 10.",
                "01 Q3 PIC 99 VALUE 30.",
            ],
            ["    MULTIPLY M BY R1 R2.", "    DIVIDE D INTO Q1 Q2 ROUNDED Q3."],
        )
        assert fields == [3, 6, 15, 4, 2, 3, 7]

    @covers(CobolFeature.ADD, CobolFeature.ON_SIZE_ERROR)
    def test_a_size_error_leaves_only_its_own_receiver_unchanged(self):
        fields = _two_digit_fields(
            [
                "01 X PIC 99 VALUE 10.",
                "01 Y PIC 99 VALUE 60.",
                "01 F PIC 99 VALUE 0.",
                "01 N PIC 99 VALUE 0.",
            ],
            [
                "    ADD 30 20 TO X Y",
                "        ON SIZE ERROR MOVE 1 TO F",
                "        NOT ON SIZE ERROR MOVE 1 TO N",
                "    END-ADD.",
            ],
        )
        assert fields == [60, 60, 1, 0]
