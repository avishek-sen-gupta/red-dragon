"""An ALSO subject is a reference and can be TRUE, exactly as the first subject is.

``red-dragon-ba1`` and ``red-dragon-c7p``. ``red-dragon-sfih`` made the FIRST
EVALUATE subject travel as ``subject_ref`` -- the structured ref node the operands
already get -- so a qualifier or a slice on it survives the bridge. The ALSO
subjects were left on the path it replaced: the serializer took the leaf data name
alone, so ``EVALUATE X ALSO FA OF GA(1:2)`` arrived as the bare name ``"FA"`` and
compared the WHOLE field rather than the slice. The same defect, one subject
position over, and just as silent.

The lowering has the matching gap: the first-subject path skips the
``EVALUATE TRUE`` form, so a WHEN under it lowers as a CONDITION, but the ALSO
loop has no such guard. ``EVALUATE TRUE ALSO TRUE / WHEN a ALSO b`` therefore
lowered ``b`` as a comparison against a field literally named TRUE -- which no
program has, so the branch could not be taken.

Both are guards on a branch, so both fail the same way: the branch reads weaker
than the source states, and nothing says so.
"""

from __future__ import annotations

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
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
    "   05 FA PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 GB.",
    "   05 FA PIC X(10) VALUE 'ZZZZZZZZZZ'.",
    "01 WS-A PIC X(2) VALUE 'AB'.",
    "01 WS-FLAG PIC X VALUE 'Y'.",
    "   88 FLAG-ON VALUE 'Y'.",
    "01 WS-MODE PIC X VALUE 'A'.",
    "   88 MODE-A VALUE 'A'.",
    "   88 MODE-B VALUE 'B'.",
    "01 D PIC 9(4) VALUE 0.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]

_D = 24
_D_LEN = 4


def _program(*statement_lines: str) -> list[str]:
    return [
        *_PREAMBLE,
        *(f"    {line}" for line in statement_lines),
        "    STOP RUN.",
    ]


def _statement(bridge_jar: str, *statement_lines: str) -> dict:  # noqa: F811
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar], to_fixed(_program(*statement_lines))
    )
    return json.loads(raw)["paragraphs"][0]["statements"][0]


def _ran(*statement_lines: str) -> int:
    """The value of D after the statements run: which WHEN branch was taken."""
    return decode_zoned_unsigned(
        first_region(run_cobol(_program(*statement_lines))), _D, _D_LEN
    )


_SLICED_ALSO = (
    "EVALUATE WS-A ALSO FA OF GA(1:2)",
    "   WHEN 'AB' ALSO 'AB' MOVE 1 TO D",
    "   WHEN OTHER MOVE 9 TO D",
    "END-EVALUATE.",
)


# -- red-dragon-ba1: the ALSO subject keeps its structure ---------------------


@covers(CobolFeature.EVALUATE, CobolFeature.REFERENCE_MODIFICATION)
def test_a_sliced_also_subject_travels_as_a_structured_ref(bridge_jar):  # noqa: F811
    """The bridge shape: what the first subject gets, every ALSO subject gets."""
    stmt = _statement(bridge_jar, *_SLICED_ALSO)

    assert stmt["also_subject_refs"] == [
        {
            "kind": "ref",
            "name": "FA",
            "ref_mod_start": {"kind": "lit", "value": "1"},
            "ref_mod_length": {"kind": "lit", "value": "2"},
            "qualifiers": ["GA"],
        }
    ]


@covers(CobolFeature.EVALUATE, CobolFeature.REFERENCE_MODIFICATION)
def test_a_sliced_also_subject_compares_the_slice_not_the_whole_field():
    """FA OF GA is 'ABCDEFGHIJ' and its first two bytes are 'AB'.

    Comparing the whole field against 'AB' does not match, so the branch that
    the source says fires is skipped and WHEN OTHER answers instead.
    """
    assert _ran(*_SLICED_ALSO) == 1


@covers(CobolFeature.EVALUATE, CobolFeature.GROUP_ITEM)
def test_a_qualified_also_subject_resolves_through_its_qualifier():
    """Two fields are named FA; the qualifier is the only thing telling them apart."""
    assert (
        _ran(
            "EVALUATE WS-A ALSO FA OF GB(1:2)",
            "   WHEN 'AB' ALSO 'AB' MOVE 1 TO D",
            "   WHEN OTHER MOVE 9 TO D",
            "END-EVALUATE.",
        )
        == 9
    )


@covers(CobolFeature.EVALUATE)
def test_a_plain_also_subject_needs_no_ref(bridge_jar):  # noqa: F811
    """A name that is only a name keeps the string alone, so nothing else moves."""
    stmt = _statement(
        bridge_jar,
        "EVALUATE WS-A ALSO WS-FLAG",
        "   WHEN 'AB' ALSO 'Y' MOVE 1 TO D",
        "END-EVALUATE.",
    )

    assert stmt["also_subjects"] == ["WS-FLAG"]
    assert "also_subject_refs" not in stmt


# -- red-dragon-c7p: TRUE in ALSO position is the condition form --------------


@covers(CobolFeature.EVALUATE, CobolFeature.LEVEL_88_CONDITION)
def test_evaluate_true_also_true_reads_both_branches_as_conditions():
    """Both level-88s hold, so the first WHEN is the one the source says fires."""
    assert (
        _ran(
            "EVALUATE TRUE ALSO TRUE",
            "   WHEN FLAG-ON ALSO MODE-A MOVE 1 TO D",
            "   WHEN OTHER MOVE 9 TO D",
            "END-EVALUATE.",
        )
        == 1
    )


@covers(CobolFeature.EVALUATE, CobolFeature.LEVEL_88_CONDITION)
def test_a_false_also_condition_under_true_does_not_take_the_branch():
    """WS-MODE is 'A', so MODE-B does not hold and the pair must not match.

    Without this the fix could be "treat every ALSO condition as true", which
    passes the test above and is wrong.
    """
    assert (
        _ran(
            "EVALUATE TRUE ALSO TRUE",
            "   WHEN FLAG-ON ALSO MODE-B MOVE 1 TO D",
            "   WHEN OTHER MOVE 9 TO D",
            "END-EVALUATE.",
        )
        == 9
    )
