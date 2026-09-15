"""Only cobol_numeric may touch ``decimal`` (red-dragon-4q25.1).

The silent failure mode this guards: a module that quietly builds a Decimal or
imports the module spreads representation-specific handling outside the
boundary, so a future change of representation misses it.
"""

import re
from pathlib import Path

from tests.covers import NotLanguageFeature, covers

REPO_ROOT = Path(__file__).resolve().parents[3]

# A deliberate regex rather than ast-grep, for the same reason as
# test_region_funnel_invariant.py: the tokens are single-line and unambiguous,
# and over-matching only names an extra file for a human to clear.
DECIMAL_USE = re.compile(
    r"^\s*(from\s+decimal\s+import|import\s+decimal)\b|\bDecimal\(", re.MULTILINE
)
SCANNED_ROOTS = ("interpreter", "cobol_asg", "cobol_memory", "mcp_server")


def _decimal_users() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for root in SCANNED_ROOTS
        for path in (REPO_ROOT / root).rglob("*.py")
        if DECIMAL_USE.search(path.read_text())
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decimal_is_used_only_inside_cobol_numeric():
    offenders = sorted(_decimal_users())
    assert offenders == [], (
        f"decimal used outside cobol_numeric: {offenders}. Route the calculation "
        "through a cobol_numeric function so the representation stays swappable."
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_boundary_itself_still_uses_decimal():
    """Guards against the invariant passing vacuously."""
    assert DECIMAL_USE.search((REPO_ROOT / "cobol_numeric/number.py").read_text())
