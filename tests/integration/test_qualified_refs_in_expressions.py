"""An OF/IN qualifier survives every expression position, not just statement operands.

``red-dragon-2afo``. The ASG-side ``serializeRef`` emits ``qualifiers``; its
grammar-context twins -- ``serializeBasisCtx``, ``serializeSubscriptCtx``,
``serializeRefModIdentifier`` and ``serializeFromValue``'s bare-field fallback --
emitted the leaf name alone. A FUNCTION argument, an arithmetic basis, a
subscript, a slice bound or a PERFORM VARYING FROM value written as
``FLD OF GA`` arrived as the bare ``FLD``, which resolves a different group's
bytes when the name is duplicated (and the fallback glued it to the
unresolvable ``FLDOFGA``).

``FLD`` is declared under two groups on purpose: only the qualifier the
programmer wrote picks the right one.
"""

from __future__ import annotations

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    first_region,
    run_cobol,
    to_fixed,
)

_PREAMBLE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. T.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 GA.",
    "   05 FLD PIC 9(4) VALUE 3.",
    "01 GB.",
    "   05 FLD PIC 9(4) VALUE 7.",
    "01 TXT PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 TBL.",
    "   05 TU PIC X(3) OCCURS 3 TIMES.",
    "01 I PIC 9(2) VALUE 1.",
    "01 D PIC 9(4) VALUE 0.",
    "01 S PIC X(10) VALUE SPACES.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]

_D = 29
_S = 33
_FLD_OF_GA = {"kind": "ref", "name": "FLD", "qualifiers": ["GA"]}

_FILL = [
    "MOVE 'AAA' TO TU(1).",
    "MOVE 'BBB' TO TU(2).",
    "MOVE 'CCC' TO TU(3).",
]


def _program(*statement_lines: str) -> list[str]:
    return [
        *_PREAMBLE,
        *(f"    {line}" for line in statement_lines),
        "    STOP RUN.",
    ]


def _statement(bridge_jar: str, *statement_lines: str) -> dict:
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar], to_fixed(_program(*statement_lines))
    )
    return json.loads(raw)["paragraphs"][0]["statements"][0]


def _region(*statement_lines: str) -> bytearray:
    return first_region(run_cobol(_program(*statement_lines)))


def _number(region: bytearray, offset: int = _D) -> int:
    return decode_zoned_unsigned(region, offset, 4)


def _text(region: bytearray) -> str:
    return bytes(region[_S : _S + 10]).decode("cp037")


# -- The bridge JSON shape ---------------------------------------------------


@covers(CobolFeature.GROUP_ITEM, CobolFeature.INTRINSIC_FUNCTION)
def test_a_function_argument_keeps_its_qualifier(bridge_jar):
    stmt = _statement(bridge_jar, "COMPUTE D = FUNCTION MAX(FLD OF GA 1).")
    assert stmt["expression"]["args"][0] == _FLD_OF_GA


@covers(CobolFeature.GROUP_ITEM, CobolFeature.COMPUTE)
def test_an_arithmetic_basis_keeps_its_qualifier(bridge_jar):
    stmt = _statement(bridge_jar, "COMPUTE D = FLD OF GB + 1.")
    assert stmt["expression"]["left"] == {
        "kind": "ref",
        "name": "FLD",
        "qualifiers": ["GB"],
    }


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_slice_bound_keeps_its_own_qualifier(bridge_jar):
    stmt = _statement(bridge_jar, "MOVE TXT(1:FLD OF GA) TO S.")
    operand = stmt["operands"][0]
    assert operand["ref_mod_length"] == _FLD_OF_GA
    assert "qualifiers" not in operand


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
def test_a_subscript_keeps_its_qualifier(bridge_jar):
    stmt = _statement(bridge_jar, "MOVE TU(FLD OF GA) TO S.")
    assert stmt["operands"][0]["subscripts"][0] == _FLD_OF_GA


@covers(CobolFeature.GROUP_ITEM, CobolFeature.PERFORM_VARYING)
def test_a_perform_varying_from_value_keeps_its_qualifier(bridge_jar):
    stmt = _statement(
        bridge_jar,
        "PERFORM VARYING I FROM FLD OF GA BY 1 UNTIL I > 3",
        "   ADD 1 TO D",
        "END-PERFORM.",
    )
    assert stmt["varying_from"] == _FLD_OF_GA


@covers(CobolFeature.COMPUTE)
def test_an_unqualified_expression_ref_emits_no_qualifiers_key(bridge_jar):
    stmt = _statement(bridge_jar, "COMPUTE D = FUNCTION MAX(I 1).")
    assert stmt["expression"]["args"][0] == {"kind": "ref", "name": "I"}


@covers(CobolFeature.GROUP_ITEM, CobolFeature.INTRINSIC_FUNCTION)
def test_a_length_of_register_still_carries_the_leaf_name_alone(bridge_jar):
    """red-dragon-twfl's shape: a LENGTH OF register is not a field ref node."""
    stmt = _statement(bridge_jar, "COMPUTE D = FUNCTION MAX(LENGTH OF FLD OF GA 1).")
    assert stmt["expression"]["args"][0] == {"kind": "length_of", "name": "FLD"}


# -- The bytes the program actually reads ------------------------------------


@covers(CobolFeature.GROUP_ITEM, CobolFeature.INTRINSIC_FUNCTION)
def test_a_function_argument_reads_its_own_groups_bytes():
    assert _number(_region("COMPUTE D = FUNCTION MAX(FLD OF GA 1).")) == 3
    assert _number(_region("COMPUTE D = FUNCTION MAX(FLD OF GB 1).")) == 7


@covers(CobolFeature.GROUP_ITEM, CobolFeature.COMPUTE)
def test_an_arithmetic_basis_reads_its_own_groups_bytes():
    assert _number(_region("COMPUTE D = FLD OF GA + 1.")) == 4
    assert _number(_region("COMPUTE D = FLD OF GB + 1.")) == 8


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_slice_bound_reads_its_own_groups_bytes():
    assert _text(_region("MOVE TXT(1:FLD OF GA) TO S.")) == "ABC       "
    assert _text(_region("MOVE TXT(1:FLD OF GB) TO S.")) == "ABCDEFG   "


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
def test_a_subscript_reads_its_own_groups_bytes():
    assert _text(_region(*_FILL, "MOVE TU(FLD OF GA) TO S.")) == "CCC       "


@covers(CobolFeature.GROUP_ITEM, CobolFeature.PERFORM_VARYING)
def test_a_perform_varying_from_value_reads_its_own_groups_bytes():
    region = _region(
        "PERFORM VARYING I FROM FLD OF GA BY 1 UNTIL I > 3",
        "   ADD 1 TO D",
        "END-PERFORM.",
    )
    assert _number(region) == 1
