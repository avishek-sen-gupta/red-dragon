"""python -m interpreter: a COBOL main program, its callees and copybooks found
through --search-dir."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import to_fixed

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CLIMAIN.",
    "PROCEDURE DIVISION.",
    "    CALL 'CLISUB'.",
    "    GOBACK.",
]
_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CLISUB.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "COPY CLIBOOK.",
    "PROCEDURE DIVISION.",
    "    DISPLAY WS-GREETING.",
    "    GOBACK.",
]


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "interpreter", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "TMPDIR": tempfile.gettempdir()},
        check=False,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cli_runs_a_main_program_with_callees_and_copybooks_from_search_dirs(
    tmp_path: Path, bridge_jar
):
    lib = tmp_path / "lib"
    lib.mkdir()
    (tmp_path / "CLIMAIN.cbl").write_text(to_fixed(_MAIN))
    (lib / "CLISUB.cbl").write_text(to_fixed(_SUB))
    (lib / "CLIBOOK.cpy").write_text(
        to_fixed(["01 WS-GREETING PIC X(5) VALUE 'HELLO'."])
    )

    ran = _cli(str(tmp_path / "CLIMAIN.cbl"), "--search-dir", str(lib))
    rejected = _cli(str(tmp_path))

    assert (ran.returncode, ran.stdout.strip()) == (0, "HELLO")
    assert rejected.returncode == 2
    assert rejected.stderr.strip().endswith(
        f"{tmp_path.resolve()} is a directory; give the main program's source file"
    )
