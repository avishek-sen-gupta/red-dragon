"""Runs the NIST CCVS suite and writes a categorised report with pass percentages."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest

from interpreter.cli_output import emit
from tests.nist.nist_report_render import report_markdown, terminal_summary
from tests.nist.nist_result import NistResult

logger = logging.getLogger(__name__)

_NIST_RESULT_PROPERTY = "nist_result"
_DEFAULT_OUT_ROOT = Path("nist-reports")
_TECHNIQUE = "pytest"
_COMPLETED_RUNS = (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED)


def _carried(report: pytest.TestReport) -> tuple[NistResult, ...]:
    return tuple(
        NistResult.model_validate_json(str(value))
        for name, value in report.user_properties
        if name == _NIST_RESULT_PROPERTY
    )


class _ResultCollector:
    """Shell: holds the NIST results pytest pushes, one test report at a time."""

    def __init__(self) -> None:
        self.results: tuple[NistResult, ...] = ()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.results = (*self.results, *_carried(report))


def _arguments(argv: Sequence[str]) -> tuple[Path, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--out-root", type=Path, default=_DEFAULT_OUT_ROOT)
    known, pytest_args = parser.parse_known_args(argv)
    return known.out_root, pytest_args


def _write_report(out_dir: Path, results: Sequence[NistResult]) -> None:
    (out_dir / "report.md").write_text(report_markdown(results))
    emit(terminal_summary(results))
    emit(f"Report: {out_dir / 'report.md'}")


def main(argv: Sequence[str]) -> int:
    out_root, pytest_args = _arguments(argv)
    out_dir = out_root / f"{datetime.now():%Y%m%d-%H%M%S}-{_TECHNIQUE}"
    out_dir.mkdir(parents=True)
    collector = _ResultCollector()
    logger.info("Running the NIST suite; writing to %s", out_dir)
    exit_code = pytest.main(
        [
            "tests/nist",
            "-m",
            "nist",
            f"--junitxml={out_dir / 'junit.xml'}",
            *pytest_args,
        ],
        plugins=[collector],
    )
    if exit_code not in _COMPLETED_RUNS:
        return int(exit_code)
    _write_report(out_dir, collector.results)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main(sys.argv[1:]))
