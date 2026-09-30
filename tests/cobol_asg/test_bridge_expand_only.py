"""The bridge writes expanded source, not an ASG, under -expand-only."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.cobol_parser import ProLeapCobolParser
from cobol_asg.subprocess_runner import RealSubprocessRunner
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import to_fixed

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. EXPTEST.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "COPY MYBOOK.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    "    STOP RUN.",
]


def _parser(jar: str, copybook_dir: Path) -> ProLeapCobolParser:
    return ProLeapCobolParser(
        RealSubprocessRunner(),
        jar,
        copybook_dirs=[copybook_dir],
        copybook_exts=["cpy"],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_expand_inlines_the_copybook_in_place_of_the_copy(
    bridge_jar: str, tmp_path: Path
) -> None:
    """The COPY line is replaced by the copybook's own lines, and the rest of the
    member is untouched. Equality rather than containment: the whole point of
    reading an expansion is that it is what the lexer got, so a test that only
    checks the copybook appeared would pass on an expansion that lost the
    PROCEDURE DIVISION."""
    (tmp_path / "MYBOOK.cpy").write_text(to_fixed(["01 WS-FROM-COPYBOOK PIC X(10)."]))

    expanded = _parser(bridge_jar, tmp_path).expand(
        to_fixed(_PROGRAM).encode("latin-1")
    )

    assert expanded == (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. EXPTEST.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-FROM-COPYBOOK PIC X(10).\n"
        "\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
