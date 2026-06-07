"""Integration: REDEFINES with an anonymous FILLER sibling parses via the bridge.

Regression test for an NPE in the ProLeap bridge's ``findRedefinesOffset``:
when a REDEFINES group has an anonymous ``FILLER`` sibling group, the bridge
called ``getName().equalsIgnoreCase(...)`` on the FILLER (whose name is null),
NPE'd, exited 1, and failed the entire parse. This is the universal BMS
symbolic-map idiom (``01 outputMap REDEFINES inputMap`` with FILLER siblings),
so the crash blocked parsing every BMS symbolic-map copybook.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    JAR_AVAILABLE,
    JAR_PATH,
    to_fixed,
)

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


# A REDEFINES whose sibling list (within the enclosing group OUTER) contains an
# anonymous FILLER group that is visited BEFORE the redefines target. The bridge
# walks the sibling list looking for the target (GRP-IN); on the way it
# dereferences the FILLER sibling's name, which ProLeap reports as null -> NPE.
# The FILLER must precede GRP-IN so the walk reaches it before matching.
REDEF_FILLER = to_fixed(
    [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. REDEFFIL.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 OUTER.",
        "   05 FILLER       PIC X(2).",
        "   05 GRP-IN.",
        "      10 FLD-A     PIC X(4).",
        "      10 FLD-X     PIC X(2).",
        "   05 GRP-OUT REDEFINES GRP-IN.",
        "      10 FLD-B     PIC X(6).",
        "PROCEDURE DIVISION.",
        "    STOP RUN.",
    ]
)


def _find(fields, name):
    for f in fields:
        if f.name == name:
            return f
        hit = _find(f.children, name)
        if hit is not None:
            return hit
    return None


@covers(CobolFeature.REDEFINES_CLAUSE)
@covers(CobolFeature.FILLER_FIELD)
def test_redefines_with_filler_sibling_parses_and_resolves():
    """A REDEFINES group with an anonymous FILLER sibling parses; redefines resolves."""
    runner = RealSubprocessRunner()
    parser = ProLeapCobolParser(runner, JAR_PATH)

    asg = parser.parse(REDEF_FILLER.encode("utf-8"))

    grp_in = _find(asg.data_fields, "GRP-IN")
    grp_out = _find(asg.data_fields, "GRP-OUT")
    fld_b = _find(asg.data_fields, "FLD-B")

    assert grp_in is not None, "GRP-IN missing from parsed fields"
    assert grp_out is not None, "GRP-OUT (redefining group) missing from parsed fields"
    assert fld_b is not None, "FLD-B (under redefining group) missing"
    assert (
        grp_out.redefines.upper() == "GRP-IN"
    ), f"GRP-OUT should redefine GRP-IN, got {grp_out.redefines!r}"
    assert (
        grp_out.offset == grp_in.offset
    ), f"GRP-OUT offset {grp_out.offset} should equal GRP-IN offset {grp_in.offset}"
