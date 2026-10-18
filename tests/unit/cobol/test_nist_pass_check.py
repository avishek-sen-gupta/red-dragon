"""The NIST pass check reads the CCVS summary from an EBCDIC print file."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from interpreter.cobol.ebcdic_table import EbcdicTable
from tests.nist.conftest import assert_nist_pass
from tests.nist.nist_failure import NistFailure
from tests.nist.nist_outcome import NistOutcome
from tests.nist.nist_skip import NistSkip


def _print_file(path: Path, lines: Sequence[str]) -> Path:
    path.write_bytes(
        b"".join(
            EbcdicTable.ascii_to_ebcdic(line.ljust(120).encode()) for line in lines
        )
    )
    return path


def test_pass_check_reads_the_ebcdic_summary(tmp_path: Path) -> None:
    clean = _print_file(
        tmp_path / "clean.dat",
        ["END OF TEST-  NC999A", "NO  TEST(S) FAILED"],
    )
    failing = _print_file(
        tmp_path / "failing.dat",
        ["END OF TEST-  NC999A", "003 TEST(S) FAILED"],
    )

    assert_nist_pass(clean, "NC999A")
    with pytest.raises(
        NistFailure, match="NC999A: CCVS summary reports 3 failed"
    ) as summary:
        assert_nist_pass(failing, "NC999A")
    with pytest.raises(NistSkip, match="NC999A: PRINT-FILE not written") as absent:
        assert_nist_pass(tmp_path / "absent.dat", "NC999A")
    assert (summary.value.outcome, absent.value.outcome) == (
        NistOutcome.SUMMARY_FAILURES,
        NistOutcome.NO_PRINT_FILE,
    )


def test_visual_inspection_summary_passes_only_when_complete_and_clean(
    tmp_path: Path,
) -> None:
    clean = _print_file(
        tmp_path / "clean.dat",
        ["END OF TEST-  NC999M", "15 TESTS REQUIRE VISUAL INSPECTION"],
    )
    failing = _print_file(
        tmp_path / "failing.dat",
        [
            "FAIL*  AREA-A-TEST",
            "END OF TEST-  NC999M",
            "15 TESTS REQUIRE VISUAL INSPECTION",
        ],
    )

    assert_nist_pass(clean, "NC999M")
    with pytest.raises(NistFailure, match="NC999M: inline FAIL\\* records") as inline:
        assert_nist_pass(failing, "NC999M")
    with pytest.raises(
        NistFailure, match="NC999M: did not run to completion"
    ) as halted:
        assert_nist_pass(
            _print_file(
                tmp_path / "halted.dat", ["15 TESTS REQUIRE VISUAL INSPECTION"]
            ),
            "NC999M",
        )
    with pytest.raises(
        NistFailure, match="NC999A: completion banner present"
    ) as silent:
        assert_nist_pass(
            _print_file(tmp_path / "silent.dat", ["END OF TEST-  NC999A"]), "NC999A"
        )
    assert [(e.value.outcome, e.value.detail) for e in (inline, halted, silent)] == [
        (NistOutcome.INLINE_FAILURES, "FAIL*  AREA-A-TEST"),
        (
            NistOutcome.INCOMPLETE,
            "NC999M: did not run to completion — 'END OF TEST' banner absent "
            "(1 record(s) written). Program halted before its summary.",
        ),
        (
            NistOutcome.NO_SUMMARY,
            "NC999A: completion banner present but no 'TEST(S) FAILED' summary line "
            "found — cannot confirm a clean run.",
        ),
    ]
