"""External tests for demo scripts — require LLM API access.

Run with: poetry run python -m pytest -m external
These are excluded from default test runs and CI.
"""

import subprocess
import sys

import pytest
from interpreter.var_name import VarName

SCRIPTS_DIR = "scripts"
TIMEOUT_SECONDS = 120


def _run_script(script_name: str) -> subprocess.CompletedProcess:
    """Run a demo script as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, f"{SCRIPTS_DIR}/{script_name}"],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )


@pytest.mark.external
class TestDemoUnresolvedCall:
    def test_runs_without_error(self):
        result = _run_script("demo_unresolved_call.py")
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_output_contains_both_modes(self):
        result = _run_script("demo_unresolved_call.py")
        assert VarName("MODE 1: symbolic") in result.stdout
        assert VarName("MODE 2: llm") in result.stdout

    def test_no_typedvalue_in_output(self):
        result = _run_script("demo_unresolved_call.py")
        assert VarName("TypedValue(") not in result.stdout


@pytest.mark.external
class TestDemoLlmE2e:
    def test_runs_without_error(self):
        result = _run_script("demo_llm_e2e.py")
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_output_contains_phases(self):
        result = _run_script("demo_llm_e2e.py")
        assert VarName("Phase 1") in result.stdout
        assert VarName("Phase 2") in result.stdout
        assert VarName("Summary") in result.stdout

    def test_no_typedvalue_in_output(self):
        result = _run_script("demo_llm_e2e.py")
        assert VarName("TypedValue(") not in result.stdout


@pytest.mark.external
class TestDemoHlasm:
    def test_runs_without_error(self):
        result = _run_script("demo_hlasm.py")
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_output_contains_verification(self):
        result = _run_script("demo_hlasm.py")
        assert VarName("Verification") in result.stdout

    def test_no_typedvalue_in_output(self):
        result = _run_script("demo_hlasm.py")
        assert VarName("TypedValue(") not in result.stdout


@pytest.mark.external
class TestDemoHlasmBubblesort:
    def test_runs_without_error(self):
        result = _run_script("demo_hlasm_bubblesort.py")
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_output_contains_verification(self):
        result = _run_script("demo_hlasm_bubblesort.py")
        assert VarName("Verification") in result.stdout

    def test_no_typedvalue_in_output(self):
        result = _run_script("demo_hlasm_bubblesort.py")
        assert VarName("TypedValue(") not in result.stdout


@pytest.mark.external
class TestDemoUnsupportedLanguageHaskell:
    def test_runs_without_error(self):
        result = _run_script("demo_unsupported_language_haskell.py")
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_output_contains_phases(self):
        result = _run_script("demo_unsupported_language_haskell.py")
        assert VarName("Phase 1") in result.stdout
        assert VarName("Phase 3") in result.stdout
        assert VarName("Summary") in result.stdout

    def test_no_typedvalue_in_output(self):
        result = _run_script("demo_unsupported_language_haskell.py")
        assert VarName("TypedValue(") not in result.stdout
