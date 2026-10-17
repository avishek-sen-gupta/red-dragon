"""RealFileIOProvider reports the ANSI X3.23-1985 logic-error I-O statuses (4x)."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import covers

_SEQ = "SEQUENTIAL"


def _provider(tmp_path: Path) -> RealFileIOProvider:
    return RealFileIOProvider(base_dir=tmp_path)


def _one_record_file(prov: RealFileIOProvider) -> None:
    prov._open_file("F", "OUTPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P")
    prov._write_record("F", "AAAA", "", "P")
    prov._close_file("F", "P")


@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
def test_open_of_an_open_file_and_close_of_a_closed_file(tmp_path: Path) -> None:
    prov = _provider(tmp_path)
    _one_record_file(prov)
    statuses = [
        prov._close_file("F", "P").status,
        prov._open_file(
            "F", "INPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P"
        ).status,
        prov._open_file(
            "F", "I-O", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P"
        ).status,
        prov._open_mode("F", "P"),
        prov._close_file("F", "P").status,
        prov._close_file("F", "P").status,
    ]
    assert statuses == ["42", "00", "41", "INPUT", "00", "42"]


@covers(CobolFeature.READ)
def test_read_needs_an_input_mode_and_a_next_record(tmp_path: Path) -> None:
    prov = _provider(tmp_path)
    _one_record_file(prov)
    unopened = prov._read_record("F", "", "P").status
    prov._open_file("F", "EXTEND", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P")
    extend = prov._read_record("F", "", "P").status
    prov._close_file("F", "P")
    prov._open_file("F", "INPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P")
    reads = [prov._read_record("F", "", "P").status for _ in range(3)]
    assert [unopened, extend, *reads] == ["47", "47", "00", "10", "46"]


@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
def test_write_and_rewrite_need_their_open_modes_and_a_current_record(
    tmp_path: Path,
) -> None:
    prov = _provider(tmp_path)
    _one_record_file(prov)
    statuses = [
        prov._write_record("F", "BBBB", "", "P").status,
        prov._rewrite_record("F", "BBBB", "", "P").status,
        prov._delete_record("F", "", "P").status,
        prov._open_file(
            "F", "INPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P"
        ).status,
        prov._rewrite_record("F", "BBBB", "", "P").status,
        prov._close_file("F", "P").status,
        prov._open_file(
            "F", "I-O", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P"
        ).status,
        prov._write_record("F", "BBBB", "", "P").status,
        prov._rewrite_record("F", "BBBB", "", "P").status,
        prov._read_record("F", "", "P").status,
        prov._rewrite_record("F", "CCCC", "", "P").status,
        prov._rewrite_record("F", "DDDD", "", "P").status,
        prov._read_record("F", "", "P").status,
        prov._rewrite_record("F", "EEEE", "", "P").status,
    ]
    assert statuses == [
        "48",
        "49",
        "49",
        "00",
        "49",
        "00",
        "00",
        "48",
        "43",
        "00",
        "00",
        "43",
        "10",
        "43",
    ]
    assert (tmp_path / "f.dat").read_bytes() == b"CCCC"


@covers(CobolFeature.CLOSE)
def test_a_file_closed_with_lock_cannot_be_opened_again(tmp_path: Path) -> None:
    prov = _provider(tmp_path)
    _one_record_file(prov)
    prov._open_file("F", "INPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P")
    prov._open_file("G", "OUTPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P")
    statuses = [
        prov._close_file_with_lock("F", "P").status,
        prov._open_file(
            "F", "INPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P"
        ).status,
        prov._open_file(
            "F", "EXTEND", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P"
        ).status,
        prov._close_file_with_lock("F", "P").status,
        prov._close_file("G", "P").status,
        prov._open_file(
            "G", "INPUT", 4, _SEQ, 0, 0, "SEQUENTIAL", 0, False, False, "P"
        ).status,
    ]
    assert statuses == ["00", "38", "38", "42", "00", "00"]
