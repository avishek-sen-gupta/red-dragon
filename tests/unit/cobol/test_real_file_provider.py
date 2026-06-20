# pyright: standard
"""Tests for RealFileIOProvider."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interpreter.cobol.cobol_statements import FileControlEntry
from interpreter.cobol.file_enums import FileOrganization
from interpreter.cobol.io_provider import IOResult
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers, NotLanguageFeature


def _provider(
    tmp_path: Path,
    entries: list[dict] | None = None,
    overrides: dict[str, Path] | None = None,
) -> RealFileIOProvider:
    fce = [FileControlEntry.from_dict(e) for e in (entries or [])]
    return RealFileIOProvider(
        base_dir=tmp_path, file_control=fce, path_overrides=overrides
    )


class TestRealFileIOProvider:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_sequential_write_and_read(self, tmp_path: Path) -> None:
        prov = _provider(tmp_path, [{"file_name": "SEQ-FILE", "assign_to": "seq.dat"}])
        prov._open_file("SEQ-FILE", "OUTPUT", 10, "SEQUENTIAL", 0, 0)
        prov._write_record("SEQ-FILE", "HELLO     ")
        prov._close_file("SEQ-FILE")

        prov2 = _provider(tmp_path, [{"file_name": "SEQ-FILE", "assign_to": "seq.dat"}])
        prov2._open_file("SEQ-FILE", "INPUT", 10, "SEQUENTIAL", 0, 0)
        r = prov2._read_record("SEQ-FILE", "")
        prov2._close_file("SEQ-FILE")
        assert r.status == "00"
        assert r.data is not None and "HELLO" in r.data

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_path_override_takes_precedence(self, tmp_path: Path) -> None:
        custom = tmp_path / "custom.dat"
        fce = FileControlEntry.from_dict(
            {
                "file_name": "F1",
                "assign_to": "ignored.dat",
            }
        )
        prov = RealFileIOProvider(
            base_dir=tmp_path,
            file_control=[fce],
            path_overrides={"F1": custom},
        )
        prov._open_file("F1", "OUTPUT", 5, "SEQUENTIAL", 0, 0)
        prov._write_record("F1", "HELLO")
        prov._close_file("F1")
        assert custom.exists()

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_env_var_path_resolution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dat = tmp_path / "envfile.dat"
        monkeypatch.setenv("MYFILE", str(dat))
        prov = _provider(tmp_path, [{"file_name": "ENV-FILE", "assign_to": "MYFILE"}])
        prov._open_file("ENV-FILE", "OUTPUT", 5, "SEQUENTIAL", 0, 0)
        prov._write_record("ENV-FILE", "HELLO")
        prov._close_file("ENV-FILE")
        assert dat.exists()

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_file_not_found_returns_35(self, tmp_path: Path) -> None:
        prov = _provider(
            tmp_path, [{"file_name": "MISSING", "assign_to": "nonexistent.dat"}]
        )
        r = prov._open_file("MISSING", "INPUT", 10, "SEQUENTIAL", 0, 0)
        assert r.status == "35"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_read_without_open_returns_47(self, tmp_path: Path) -> None:
        prov = _provider(tmp_path)
        r = prov._read_record("UNOPENED", "")
        assert r.status == "47"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_indexed_write_and_keyed_read(self, tmp_path: Path) -> None:
        prov = _provider(
            tmp_path,
            [
                {
                    "file_name": "IDX-FILE",
                    "assign_to": "idx.dat",
                    "organization": "INDEXED",
                    "record_key": "KEY-FIELD",
                }
            ],
        )
        prov._open_file("IDX-FILE", "OUTPUT", 10, "INDEXED", 0, 3)
        prov._write_record("IDX-FILE", "AAAFILLER ")
        prov._write_record("IDX-FILE", "BBBFILLER ")
        prov._close_file("IDX-FILE")

        prov2 = _provider(
            tmp_path,
            [
                {
                    "file_name": "IDX-FILE",
                    "assign_to": "idx.dat",
                    "organization": "INDEXED",
                    "record_key": "KEY-FIELD",
                }
            ],
        )
        prov2._open_file("IDX-FILE", "INPUT", 10, "INDEXED", 0, 3)
        r = prov2._read_record("IDX-FILE", "BBB")
        prov2._close_file("IDX-FILE")
        assert r.status == "00"
        assert r.data is not None and r.data[:3] == "BBB"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_sequential_eof_returns_10(self, tmp_path: Path) -> None:
        prov = _provider(tmp_path, [{"file_name": "SEQ", "assign_to": "s.dat"}])
        prov._open_file("SEQ", "OUTPUT", 5, "SEQUENTIAL", 0, 0)
        prov._write_record("SEQ", "HELLO")
        prov._close_file("SEQ")

        prov2 = _provider(tmp_path, [{"file_name": "SEQ", "assign_to": "s.dat"}])
        prov2._open_file("SEQ", "INPUT", 5, "SEQUENTIAL", 0, 0)
        prov2._read_record("SEQ", "")  # read the one record
        r = prov2._read_record("SEQ", "")  # now EOF
        prov2._close_file("SEQ")
        assert r.status == "10"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_override_resolves_by_assign_name(self, tmp_path: Path) -> None:
        # SELECT IN-FILE ASSIGN TO INDD: the override is keyed by the ASSIGN
        # name (the JCL DDname), not the SELECT name. The provider must resolve
        # IN-FILE -> assign_to "INDD" -> the override path (red-dragon-3mmk).
        data = tmp_path / "in.dat"
        data.write_bytes(b"HELLO")
        prov = RealFileIOProvider(
            base_dir=tmp_path,
            file_control=[
                FileControlEntry.from_dict(
                    {"file_name": "IN-FILE", "assign_to": "INDD"}
                )
            ],
            path_overrides={"INDD": data},
        )
        r = prov._open_file("IN-FILE", "INPUT", 5, "SEQUENTIAL", 0, 0)
        assert r.status == "00"
