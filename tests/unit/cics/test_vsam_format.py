"""Raw fixed-length-record flat-file codec for VSAM dataset images."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cics.vsam.format import read_flat_file, write_flat_file
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_round_trip(tmp_path: Path) -> None:
    recs = [b"AAAA", b"BBBB", b"CCCC"]
    p = tmp_path / "ds.dat"
    write_flat_file(p, recs, 4)
    assert read_flat_file(p, 4) == recs


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_missing_file_reads_empty(tmp_path: Path) -> None:
    assert read_flat_file(tmp_path / "nope.dat", 4) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_size_not_multiple_of_record_length_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.dat"
    p.write_bytes(b"AAAAB")  # 5 bytes, record_length 4
    with pytest.raises(ValueError):
        read_flat_file(p, 4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_wrong_length_record_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_flat_file(tmp_path / "x.dat", [b"AAAA", b"BB"], 4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_is_atomic_no_temp_left(tmp_path: Path) -> None:
    p = tmp_path / "ds.dat"
    write_flat_file(p, [b"AAAA"], 4)
    assert [f.name for f in tmp_path.iterdir()] == ["ds.dat"]
