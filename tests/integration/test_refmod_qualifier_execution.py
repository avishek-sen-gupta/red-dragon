"""A ref-modified qualified operand must read its OWN group's bytes.

The end-to-end counterpart of ``test_bridge_refmod_qualifiers``
(``red-dragon-64s4``). ``FLD`` is declared under two groups on purpose: an
operand that loses its qualifier is ambiguous, and one that inherits the
BOUND's qualifier names a field that does not exist under it. Only the
qualifier the programmer wrote reads the right bytes.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import first_region, run_cobol

_PREAMBLE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. T.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 GA.",
    "   05 FLD PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 GB.",
    "   05 FLD PIC X(10) VALUE 'ZZZZZZZZZZ'.",
    "01 NB.",
    "   05 NL PIC 9(4) VALUE 3.",
    "01 D PIC X(10) VALUE SPACES.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]

_GA_FLD = 0
_GB_FLD = 10
_D = 24
_WIDTH = 10


def _region(*statement_lines: str) -> bytearray:
    return first_region(
        run_cobol(
            [
                *_PREAMBLE,
                *(f"    {line}" for line in statement_lines),
                "    STOP RUN.",
            ]
        )
    )


def _text(region: bytearray, offset: int) -> str:
    return bytes(region[offset : offset + _WIDTH]).decode("cp037")


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_literal_slice_reads_the_written_groups_bytes():
    assert _text(_region("MOVE FLD OF GA(1:3) TO D."), _D) == "ABC       "
    assert _text(_region("MOVE FLD OF GB(1:3) TO D."), _D) == "ZZZ       "


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_qualified_bound_does_not_redirect_the_slice_to_its_own_group():
    assert _text(_region("MOVE FLD OF GA(1:NL OF NB) TO D."), _D) == "ABC       "


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_the_unsliced_groups_keep_their_bytes():
    region = _region("MOVE FLD OF GA(1:3) TO D.")
    assert _text(region, _GA_FLD) == "ABCDEFGHIJ"
    assert _text(region, _GB_FLD) == "ZZZZZZZZZZ"


@covers(CobolFeature.GROUP_ITEM)
def test_a_qualified_operand_without_a_slice_is_the_baseline():
    assert _text(_region("MOVE FLD OF GB TO D."), _D) == "ZZZZZZZZZZ"
