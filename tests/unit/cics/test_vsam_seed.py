"""Tests for seed_vsam and load_vsam_seed."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from interpreter.cics.vsam.format import read_flat_file
from interpreter.cics.vsam.seed import load_vsam_seed, seed_vsam
from tests.covers import NotLanguageFeature, covers


def _write_fct(path: Path, datasets: dict) -> None:
    path.write_text(yaml.dump({"datasets": datasets}))


def _write_flat(path: Path, records: list[bytes]) -> None:
    path.write_bytes(b"".join(records))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_vsam_seed_returns_records(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_flat(data_dir / "acct.dat", [b"AAAA", b"BBBB"])
    _write_fct(
        tmp_path / "fct.yaml",
        {"ACCTFILE": {"file": "acct.dat", "record_length": 4}},
    )

    seed = load_vsam_seed(tmp_path / "fct.yaml", data_dir)

    assert seed == {"ACCTFILE": [b"AAAA", b"BBBB"]}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_vsam_seed_multiple_datasets(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_flat(data_dir / "acct.dat", [b"AAAA"])
    _write_flat(data_dir / "card.dat", [b"CCCCCCCC", b"DDDDDDDD"])
    _write_fct(
        tmp_path / "fct.yaml",
        {
            "ACCTFILE": {"file": "acct.dat", "record_length": 4},
            "CARDFILE": {"file": "card.dat", "record_length": 8},
        },
    )

    seed = load_vsam_seed(tmp_path / "fct.yaml", data_dir)

    assert seed["ACCTFILE"] == [b"AAAA"]
    assert seed["CARDFILE"] == [b"CCCCCCCC", b"DDDDDDDD"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_seed_vsam_writes_dat_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vsam_dir = tmp_path / "vsam"
    _write_flat(data_dir / "acct.dat", [b"AAAA", b"BBBB"])
    _write_fct(
        tmp_path / "fct.yaml",
        {"ACCTFILE": {"file": "acct.dat", "record_length": 4}},
    )

    seed_vsam(tmp_path / "fct.yaml", data_dir, vsam_dir)

    dat = vsam_dir / "ACCTFILE.dat"
    assert dat.exists()
    assert read_flat_file(dat, 4) == [b"AAAA", b"BBBB"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_seed_vsam_creates_vsam_dir_if_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vsam_dir = tmp_path / "vsam" / "nested"
    _write_flat(data_dir / "acct.dat", [b"AAAA"])
    _write_fct(
        tmp_path / "fct.yaml",
        {"ACCTFILE": {"file": "acct.dat", "record_length": 4}},
    )

    seed_vsam(tmp_path / "fct.yaml", data_dir, vsam_dir)

    assert (vsam_dir / "ACCTFILE.dat").exists()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_seed_vsam_source_files_untouched(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vsam_dir = tmp_path / "vsam"
    original = b"AAAA"
    (data_dir / "acct.dat").write_bytes(original)
    _write_fct(
        tmp_path / "fct.yaml",
        {"ACCTFILE": {"file": "acct.dat", "record_length": 4}},
    )

    seed_vsam(tmp_path / "fct.yaml", data_dir, vsam_dir)

    assert (data_dir / "acct.dat").read_bytes() == original
