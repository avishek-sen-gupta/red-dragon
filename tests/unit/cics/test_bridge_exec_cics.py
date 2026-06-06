"""Verify the ProLeap bridge emits exec_cics_text for EXEC CICS statements."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.covers import covers, NotLanguageFeature

REPO_ROOT = Path(__file__).parents[3]
BRIDGE_JAR = "proleap-bridge.jar"
JAR_AVAILABLE = os.path.isfile(REPO_ROOT / BRIDGE_JAR)

COBOL_WITH_EXEC_CICS = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTCICS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DUMMY PIC X.
       PROCEDURE DIVISION.
           EXEC CICS RETURN END-EXEC.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.skipif(not JAR_AVAILABLE, reason="bridge JAR not available")
def test_bridge_emits_exec_cics_text():
    result = subprocess.run(
        ["java", "-jar", BRIDGE_JAR],
        input=COBOL_WITH_EXEC_CICS,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    asg = json.loads(result.stdout)
    stmts = asg.get("statements", [])
    exec_cics = next((s for s in stmts if s.get("type") == "EXEC_CICS"), None)
    assert exec_cics is not None, f"No EXEC_CICS in statements: {stmts}"
    assert "exec_cics_text" in exec_cics, f"Missing exec_cics_text: {exec_cics}"
    assert "RETURN" in exec_cics["exec_cics_text"]
