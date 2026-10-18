"""USAGE spellings reach the layout as one canonical USAGE each."""

import pytest

from cobol_asg.asg_types import CobolASG
from interpreter.frontend import make_cobol_parser
from tests.integration.cobol_helpers import bridge_jar, to_fixed  # noqa: F401

pytestmark = pytest.mark.usefixtures("bridge_jar")

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. USAGES.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 G.",
    "   05 P1 PIC 9(3) COMPUTATIONAL-3.",
    "   05 P2 PIC 9(3) PACKED-DECIMAL.",
    "   05 B1 PIC 9(3) BINARY.",
    "   05 B2 PIC 9(3) COMPUTATIONAL-4.",
    "   05 B3 PIC 9(3) COMP.",
    "   05 B5 PIC 9(3) COMPUTATIONAL-5.",
    "   05 F1 COMPUTATIONAL-1.",
    "   05 F2 COMP-2.",
    "   05 D1 PIC X DISPLAY.",
    "   05 X1 USAGE INDEX.",
    "   05 PT USAGE POINTER.",
    "PROCEDURE DIVISION.",
    "    STOP RUN.",
]


def test_each_usage_spelling_reads_as_its_canonical_usage():
    asg = make_cobol_parser().parse(to_fixed(_PROGRAM).encode()).first_program
    expected = [
        ("P1", "COMP-3"),
        ("P2", "COMP-3"),
        ("B1", "COMP"),
        ("B2", "COMP"),
        ("B3", "COMP"),
        ("B5", "COMP-5"),
        ("F1", "COMP-1"),
        ("F2", "COMP-2"),
        ("D1", "DISPLAY"),
        ("X1", "INDEX"),
        ("PT", "POINTER"),
    ]

    assert [(c.name, c.usage) for c in asg.data_fields[0].children] == expected
    revived = CobolASG.from_dict(asg.to_dict())
    assert [(c.name, c.usage) for c in revived.data_fields[0].children] == expected
