"""INITIALIZE is a series of MOVEs into the elementary items of its operands:
REPLACING sends each named category its own value and leaves the rest alone, and
FILLER and REDEFINES items are skipped while every occurrence of a table is set."""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region


def _record(name: str) -> list[str]:
    return [
        f"01 {name}.",
        f"   03 {name}-NUM PIC 9(4).",
        f"   03 {name}-ALPHA PIC A(3).",
        f"   03 {name}-ALNUM PIC X(3).",
        f"   03 {name}-EDIT PIC $(3)9.99.",
        f"   03 {name}-AEDIT PIC XXBXX.",
    ]


def _program(program_id: str, data: list[str], statements: list[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        f"PROGRAM-ID. {program_id}.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        *data,
        "PROCEDURE DIVISION.",
        *statements,
        "    STOP RUN.",
    ]


@covers(CobolFeature.INITIALIZE)
def test_replacing_moves_each_named_category_its_value_and_leaves_the_rest() -> None:
    program = _program(
        "INIREP",
        [*_record("R1"), *_record("R2"), "01 WS-SRC PIC 9(4) VALUE 1234."],
        [
            "    MOVE ALL '#' TO R1 R2.",
            "    INITIALIZE R1 REPLACING ALPHABETIC DATA BY 'ABC'",
            "        NUMERIC-EDITED DATA BY WS-SRC.",
            "    INITIALIZE R2 REPLACING NUMERIC DATA BY 7",
            "        ALPHANUMERIC BY 'Q' ALPHANUMERIC-EDITED BY 'DDDD'.",
        ],
    )

    ws = bytes(ws_region(run_cobol_programs(program, {}), "INIREP"))

    assert (ws[:22].decode("cp037"), ws[22:44].decode("cp037")) == (
        "####ABC###$234.00#####",
        "0007###Q  #######DD DD",
    )


@covers(CobolFeature.INITIALIZE, CobolFeature.OCCURS_FIXED)
def test_initialize_skips_filler_and_redefines_and_sets_every_occurrence() -> None:
    table = [
        "   03 FILLER PIC XX VALUE 'FF'.",
        "   03 {0}-CELL PIC X OCCURS 3.",
        "   03 {0}-NUMS PIC 9 OCCURS 2.",
        "   03 {0}-OVER REDEFINES {0}-NUMS PIC XX.",
        "   03 {0}-ROW OCCURS 2.",
        "      05 {0}-R1 PIC X.",
        "      05 {0}-R2 PIC 9.",
    ]
    program = _program(
        "INIOCC",
        [
            "01 T1.",
            *(line.format("T1") for line in table),
            "01 T2.",
            *(line.format("T2") for line in table),
        ],
        [
            "    MOVE ALL '#' TO T1 T2.",
            "    INITIALIZE T1.",
            "    INITIALIZE T2-ROW(2) T2-CELL(3).",
        ],
    )

    ws = bytes(ws_region(run_cobol_programs(program, {}), "INIOCC"))

    assert (ws[:11].decode("cp037"), ws[11:22].decode("cp037")) == (
        "##   00 0 0",
        "#### #### 0",
    )
