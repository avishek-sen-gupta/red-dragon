"""A CCVS program whose deck comments out a statement's period is recognised by the IF it leaves nested."""

from __future__ import annotations

from tests.covers import NotLanguageFeature, covers
from tests.nist.conftest import exit_nested_under

_REEL = "XRECORD-NUMBER (1) EQUAL TO 325"
_EXIT = "XRECORD-NUMBER (1) EQUAL TO 750"


def _deck(*lines: str) -> str:
    return "\n".join(f"{n:06d}{line}" for n, line in enumerate(lines, start=1))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_exit_if_is_nested_only_when_comment_lines_took_the_period_before_it() -> (
    None
):
    nested = _deck(
        "     IF      XRECORD-NUMBER (1) EQUAL TO 325",
        "*             CLOSE SQ-FS1 REEL.",
        "     IF XRECORD-NUMBER (1) EQUAL TO 750",
        "         GO TO SEQ-WRITE-001.",
    )
    ended = _deck(
        "     IF      XRECORD-NUMBER (1) EQUAL TO 325",
        "              CLOSE SQ-FS1 REEL.",
        "     IF XRECORD-NUMBER (1) EQUAL TO 750",
        "         GO TO SEQ-WRITE-001.",
    )
    closed = _deck(
        "     IF      XRECORD-NUMBER (1) EQUAL TO 325.",
        "     IF XRECORD-NUMBER (1) EQUAL TO 750",
        "         GO TO SEQ-WRITE-001.",
    )

    assert [
        exit_nested_under(src, _REEL, _EXIT) for src in (nested, ended, closed)
    ] == [
        True,
        False,
        False,
    ]
