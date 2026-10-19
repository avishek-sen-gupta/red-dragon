"""The NIST report groups program results by module and by outcome."""

from __future__ import annotations

from tests.covers import NotLanguageFeature, covers
from tests.nist.nist_outcome import NistOutcome
from tests.nist.nist_report_render import report_markdown, terminal_summary
from tests.nist.nist_result import NistResult

_RESULTS = (
    NistResult(program="SQ102A", outcome=NistOutcome.PASS, detail=""),
    NistResult(
        program="NC103A",
        outcome=NistOutcome.INCOMPLETE,
        detail="NC103A: did not run to completion",
    ),
    NistResult(program="NC101A", outcome=NistOutcome.PASS, detail=""),
    NistResult(program="NC302M", outcome=NistOutcome.FIPS_FLAGGER, detail="flags"),
    NistResult(
        program="SQ101A",
        outcome=NistOutcome.ERROR,
        detail="KeyError: 'X'",
    ),
    NistResult(program="NC102A", outcome=NistOutcome.PASS, detail=""),
    NistResult(program="CM101M", outcome=NistOutcome.UNSUPPORTED, detail="no MCS"),
    NistResult(
        program="ST102A",
        outcome=NistOutcome.VERIFIED_BY_CHECKER,
        detail="verified by ST103A",
    ),
)

_TABLE = (
    "| Module | Pass | Fail | Skip | Total | Pass % |\n"
    "|---|---:|---:|---:|---:|---:|\n"
    "| CM | 0 | 0 | 1 | 1 | 0.0 |\n"
    "| NC | 2 | 1 | 1 | 4 | 50.0 |\n"
    "| SQ | 1 | 1 | 0 | 2 | 50.0 |\n"
    "| ST | 1 | 0 | 0 | 1 | 100.0 |\n"
    "| Overall | 4 | 2 | 2 | 8 | 50.0 |"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_report_lists_modules_then_categories_then_first_failure_lines() -> None:
    assert report_markdown(_RESULTS) == (
        "# NIST CCVS conformance report\n"
        "\n"
        f"{_TABLE}\n"
        "\n"
        "## Categories\n"
        "\n"
        "### pass (3)\n"
        "\n"
        "NC101A, NC102A, SQ102A\n"
        "\n"
        "### verified-by-checker (1)\n"
        "\n"
        "ST102A (verified by ST103A)\n"
        "\n"
        "### incomplete (1)\n"
        "\n"
        "NC103A\n"
        "\n"
        "### error (1)\n"
        "\n"
        "SQ101A\n"
        "\n"
        "### fips-flagger (1)\n"
        "\n"
        "NC302M\n"
        "\n"
        "### unsupported (1)\n"
        "\n"
        "CM101M\n"
        "\n"
        "## First failure line per program\n"
        "\n"
        "- NC103A (incomplete): NC103A: did not run to completion\n"
        "- SQ101A (error): KeyError: 'X'\n"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_terminal_summary_is_the_module_table_and_category_counts() -> None:
    assert terminal_summary(_RESULTS) == (
        f"{_TABLE}\n"
        "\n"
        "pass: 3\n"
        "verified-by-checker: 1\n"
        "incomplete: 1\n"
        "error: 1\n"
        "fips-flagger: 1\n"
        "unsupported: 1"
    )
