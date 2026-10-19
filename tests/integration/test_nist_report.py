"""The NIST report command runs real CCVS programs and categorises each one."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.nist.conftest import run_within_budget
from tests.nist.nist_failure import NistFailure
from tests.nist.nist_outcome import NistOutcome

_REPO = Path(__file__).resolve().parents[2]
_PROGRAMS = ("SQ130A", "SG103A", "RW101A", "NC302M", "SQ302M", "CM101M")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_report_command_categorises_a_pass_a_fail_an_error_and_skips(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.nist_report",
            "--out-root",
            str(tmp_path),
            "-n",
            "0",
            "-k",
            " or ".join(_PROGRAMS),
        ],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    [out_dir] = list(tmp_path.iterdir())
    report = (out_dir / "report.md").read_text()

    assert (completed.returncode, out_dir.name.endswith("-pytest")) == (0, True)
    assert (out_dir / "junit.xml").exists()
    assert report.split("## First failure line per program")[0] == (
        "# NIST CCVS conformance report\n"
        "\n"
        "| Module | Pass | Fail | Skip | Total | Pass % |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        "| CM | 0 | 0 | 1 | 1 | 0.0 |\n"
        "| NC | 0 | 0 | 1 | 1 | 0.0 |\n"
        "| RW | 0 | 1 | 0 | 1 | 0.0 |\n"
        "| SG | 0 | 1 | 0 | 1 | 0.0 |\n"
        "| SQ | 1 | 0 | 1 | 2 | 50.0 |\n"
        "| Overall | 1 | 2 | 3 | 6 | 16.7 |\n"
        "\n"
        "## Categories\n"
        "\n"
        "### pass (1)\n"
        "\n"
        "SQ130A\n"
        "\n"
        "### summary-failures (1)\n"
        "\n"
        "SG103A\n"
        "\n"
        "### error (1)\n"
        "\n"
        "RW101A\n"
        "\n"
        "### fips-flagger (2)\n"
        "\n"
        "NC302M, SQ302M\n"
        "\n"
        "### unsupported (1)\n"
        "\n"
        "CM101M\n"
        "\n"
    )
    assert report.split("## First failure line per program\n\n")[1] == (
        "- RW101A (error): ValueError: Unknown COBOL statement type: 'INITIATE'\n"
        "- SG103A (summary-failures): SG103A: CCVS summary reports 3 failed test(s).\n"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_run_that_exhausts_its_step_budget_fails_as_such(tmp_path: Path) -> None:
    with pytest.raises(NistFailure) as exhausted:
        run_within_budget("SQ130A", tmp_path, 1000)

    assert (exhausted.value.outcome, exhausted.value.detail) == (
        NistOutcome.STEP_BUDGET_EXHAUSTED,
        "SQ130A: step budget of 1000 exhausted before the program ended.",
    )
