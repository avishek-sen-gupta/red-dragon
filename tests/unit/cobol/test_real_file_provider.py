# pyright: standard
"""Tests for RealFileIOProvider."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

import pytest

from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import AccessMode, FileOrganization, OpenMode
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_drivers import FileOrganizationDriver, open_driver
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.vm.vm import Operators
from tests.covers import NotLanguageFeature, covers
from tests.unit.cobol.declared_files import opened


def _provider(
    tmp_path: Path,
    entries: Sequence[Mapping[str, str]] = (),
    overrides: Mapping[str, Path] = MappingProxyType({}),
) -> RealFileIOProvider:
    fce = [FileControlEntry.from_dict(dict(e)) for e in entries]
    return RealFileIOProvider(
        base_dir=tmp_path, file_control=fce, path_overrides=overrides
    )


class TestRealFileIOProvider:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_sequential_write_and_read(self, tmp_path: Path) -> None:
        prov = _provider(tmp_path, [{"file_name": "SEQ-FILE", "assign_to": "seq.dat"}])
        opened(
            prov,
            "OUTPUT",
            FileFrame(
                "SEQ-FILE",
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                10,
            ),
        )
        prov._write_record("SEQ-FILE", "HELLO     ", "", "PGM")
        prov._close_file("SEQ-FILE", "PGM")

        prov2 = _provider(tmp_path, [{"file_name": "SEQ-FILE", "assign_to": "seq.dat"}])
        opened(
            prov2,
            "INPUT",
            FileFrame(
                "SEQ-FILE",
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                10,
            ),
        )
        r = prov2._read_record("SEQ-FILE", "", "PGM")
        prov2._close_file("SEQ-FILE", "PGM")
        assert r.status == "00"
        assert r.data == "HELLO     "

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
        opened(
            prov,
            "OUTPUT",
            FileFrame(
                "F1",
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                5,
            ),
        )
        prov._write_record("F1", "HELLO", "", "PGM")
        prov._close_file("F1", "PGM")
        assert custom.exists()

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_env_var_path_resolution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dat = tmp_path / "envfile.dat"
        monkeypatch.setenv("MYFILE", str(dat))
        prov = _provider(tmp_path, [{"file_name": "ENV-FILE", "assign_to": "MYFILE"}])
        opened(
            prov,
            "OUTPUT",
            FileFrame(
                "ENV-FILE",
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                5,
            ),
        )
        prov._write_record("ENV-FILE", "HELLO", "", "PGM")
        prov._close_file("ENV-FILE", "PGM")
        assert dat.exists()

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_file_not_found_returns_35(self, tmp_path: Path) -> None:
        prov = _provider(
            tmp_path, [{"file_name": "MISSING", "assign_to": "nonexistent.dat"}]
        )
        statuses = [
            opened(
                prov,
                mode,
                FileFrame(
                    "MISSING",
                    FileOrganization("SEQUENTIAL"),
                    AccessMode("SEQUENTIAL"),
                    PrimeKey(0, 0),
                    False,
                    10,
                ),
            ).status
            for mode in ("INPUT", "I-O", "EXTEND")
        ]
        assert statuses == ["35", "35", "35"]
        assert not (tmp_path / "nonexistent.dat").exists()

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
        opened(
            prov,
            "OUTPUT",
            FileFrame(
                "IDX-FILE",
                FileOrganization("INDEXED"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 3),
                False,
                10,
            ),
        )
        _ = [
            prov._write_record("IDX-FILE", record, "", "PGM")
            for record in ("AAAFILLER ", "BBBFILLER ")
        ]
        prov._close_file("IDX-FILE", "PGM")

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
        opened(
            prov2,
            "INPUT",
            FileFrame(
                "IDX-FILE",
                FileOrganization("INDEXED"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 3),
                False,
                10,
            ),
        )
        r = prov2._read_record("IDX-FILE", "BBB", "PGM")
        prov2._close_file("IDX-FILE", "PGM")
        assert r.status == "00"
        assert r.data == "BBBFILLER "

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_sequential_eof_returns_10(self, tmp_path: Path) -> None:
        prov = _provider(tmp_path, [{"file_name": "SEQ", "assign_to": "s.dat"}])
        opened(
            prov,
            "OUTPUT",
            FileFrame(
                "SEQ",
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                5,
            ),
        )
        prov._write_record("SEQ", "HELLO", "", "PGM")
        prov._close_file("SEQ", "PGM")

        prov2 = _provider(tmp_path, [{"file_name": "SEQ", "assign_to": "s.dat"}])
        opened(
            prov2,
            "INPUT",
            FileFrame(
                "SEQ",
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                5,
            ),
        )
        prov2._read_record("SEQ", "", "PGM")  # read the one record
        r = prov2._read_record("SEQ", "", "PGM")  # now EOF
        prov2._close_file("SEQ", "PGM")
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
        r = opened(
            prov,
            "INPUT",
            FileFrame(
                "IN-FILE",
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                5,
            ),
        )
        assert r.status == "00"


class _WideRecords(RealFileIOProvider):
    def _driver(
        self, frame: FileFrame, path: Path, mode: OpenMode
    ) -> FileOrganizationDriver:
        return open_driver(
            frame.organization,
            path,
            mode,
            frame.record_length * (2 if frame.file_name == "F1" else 1),
            frame.prime_key.offset,
            frame.prime_key.length,
        )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_subclass_chooses_the_driver_each_open_of_each_file_uses(
    tmp_path: Path,
) -> None:
    fce = [
        FileControlEntry.from_dict({"file_name": name, "assign_to": f"{name}.dat"})
        for name in ("F1", "F2")
    ]
    prov = _WideRecords(base_dir=tmp_path, file_control=fce)
    opens = [
        opened(
            prov,
            "OUTPUT",
            FileFrame(
                n,
                FileOrganization("SEQUENTIAL"),
                AccessMode("SEQUENTIAL"),
                PrimeKey(0, 0),
                False,
                5,
            ),
        )
        for n in ("F1", "F2")
    ]
    prov._write_record("F1", "HELLO", "", "PGM")
    prov._write_record("F2", "WORLD", "", "PGM")
    prov._close_file("F1", "PGM")
    prov._close_file("F2", "PGM")
    assert (
        [o.status for o in opens],
        (tmp_path / "F1.dat").read_bytes(),
        (tmp_path / "F2.dat").read_bytes(),
    ) == (["00", "00"], b"HELLO     ", b"WORLD")


@covers(CobolFeature.ACCEPT)
def test_accept_fills_the_receiving_area_from_successive_system_input_records(
    tmp_path: Path,
) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path, system_input=["ABCD", "EFGH", "IJKL"])
    filled = [prov._accept_area("SYSIN", length) for length in (6, 2, 3)]
    assert filled == ["ABCDEF", "IJ", Operators.UNCOMPUTABLE]
