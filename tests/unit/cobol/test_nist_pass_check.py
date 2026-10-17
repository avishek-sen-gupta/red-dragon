"""The NIST pass check reads the CCVS summary from an EBCDIC print file."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from interpreter.cobol.ebcdic_table import EbcdicTable
from tests.nist.conftest import assert_nist_pass


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
    with pytest.raises(AssertionError, match="NC999A: CCVS summary reports 3 failed"):
        assert_nist_pass(failing, "NC999A")


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
    with pytest.raises(AssertionError, match="NC999M: inline FAIL\\* records"):
        assert_nist_pass(failing, "NC999M")
    with pytest.raises(AssertionError, match="NC999M: did not run to completion"):
        assert_nist_pass(
            _print_file(
                tmp_path / "halted.dat", ["15 TESTS REQUIRE VISUAL INSPECTION"]
            ),
            "NC999M",
        )
    with pytest.raises(AssertionError, match="NC999A: completion banner present"):
        assert_nist_pass(
            _print_file(tmp_path / "silent.dat", ["END OF TEST-  NC999A"]), "NC999A"
        )
