"""DELETE removes the record its key names in random or dynamic access, and the
current record in sequential access (ANSI X3.23-1985 Relative and Indexed I-O
modules, DELETE statement)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cobol_asg.file_enums import AccessMode, FileOrganization
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers

_INDEXED = FileOrganization.INDEXED.value
_RELATIVE = FileOrganization.RELATIVE.value
_DYNAMIC = AccessMode.DYNAMIC.value
_SEQUENTIAL = AccessMode.SEQUENTIAL.value


def _loaded(
    prov: RealFileIOProvider,
    name: str,
    organization: str,
    access: str,
    records: Sequence[str],
) -> None:
    prov._open_file(name, "OUTPUT", 4, organization, 0, 2, access, 0, "P")
    [prov._write_record(name, record, "", "P") for record in records]
    prov._close_file(name, "P")
    prov._open_file(name, "I-O", 4, organization, 0, 2, access, 0, "P")


@covers(CobolFeature.DELETE_RECORD)
def test_a_keyed_delete_needs_no_current_record(
    tmp_path: Path,
) -> None:
    prov = RealFileIOProvider(base_dir=tmp_path)
    _loaded(prov, "IX", _INDEXED, _DYNAMIC, ["01AA", "02BB", "03CC"])
    _loaded(prov, "IS", _INDEXED, _SEQUENTIAL, ["01AA", "02BB", "03CC"])
    _loaded(prov, "RL", _RELATIVE, _DYNAMIC, ["AAAA", "BBBB"])
    statuses = [
        prov._delete_record("IX", "02", "P").status,
        prov._delete_record("IX", "09", "P").status,
        prov._delete_record("IS", "", "P").status,
        prov._read_record("IS", "", "P").status,
        prov._delete_record("IS", "", "P").status,
        prov._delete_record("RL", "2", "P").status,
    ]
    [prov._close_file(name, "P") for name in ("IX", "IS", "RL")]
    assert (
        statuses,
        (tmp_path / "ix.dat").read_bytes(),
        (tmp_path / "is.dat").read_bytes(),
        (tmp_path / "rl.dat").read_bytes(),
    ) == (
        ["00", "23", "43", "00", "00", "00"],
        b"01AA03CC",
        b"02BB03CC",
        b"\xffAAAA\x00BBBB",
    )
