"""Unit tests for VSAM file engine."""

import tempfile
from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.vsam.engine import (
    VsamEngine,
    RESP_NORMAL,
    RESP_NOTFND,
    RESP_DUPREC,
    RESP_ENDFILE,
)
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fct_config_from_yaml():
    import yaml

    data = yaml.safe_load(
        "datasets:\n"
        "  ACCTDAT:\n"
        "    path: data/acctdata.txt\n"
        "    record_length: 300\n"
        "  CARDDAT:\n"
        "    path: data/carddata.txt\n"
        "    record_length: 150\n"
    )
    config = FctConfig.from_dict(data)
    assert "ACCTDAT" in config.datasets
    assert config.datasets["ACCTDAT"].record_length == 300
    assert config.datasets["CARDDAT"].path == Path("data/carddata.txt")


def _write_fixed_records(path: Path, records: list[bytes]) -> None:
    with path.open("wb") as f:
        for r in records:
            f.write(r)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vsam_engine_loads_dataset():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "acctdata.txt"
        _write_fixed_records(p, [b"A" * 20 + b"B" * 10])
        config = FctConfig(
            datasets={"ACCTDAT": DatasetConfig(path=p, record_length=30)}
        )
        engine = VsamEngine(config)
        engine.load_all()
        assert engine.dataset_count() == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vsam_engine_empty_file_is_ok():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "empty.txt"
        p.write_bytes(b"")
        config = FctConfig(datasets={"EMPTY": DatasetConfig(path=p, record_length=10)})
        engine = VsamEngine(config)
        engine.load_all()
        assert engine.dataset_count() == 1


REC_LEN = 10
KEY_LEN = 4


def _rec(key: str, rest: str = "") -> bytes:
    body = rest.ljust(REC_LEN - KEY_LEN)[: REC_LEN - KEY_LEN]
    return (key.ljust(KEY_LEN)[:KEY_LEN] + body).encode()


def _engine_with_records(records: list[bytes], rec_len: int) -> VsamEngine:
    td = tempfile.mkdtemp()
    p = Path(td) / "data.txt"
    _write_fixed_records(p, records)
    config = FctConfig(
        datasets={"TESTDS": DatasetConfig(path=p, record_length=rec_len)}
    )
    engine = VsamEngine(config)
    engine.load_all()
    return engine


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_existing_record():
    engine = _engine_with_records([_rec("AA01", "DATA")], REC_LEN)
    record, resp = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert resp == RESP_NORMAL
    assert record is not None and record[:KEY_LEN] == b"AA01"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_not_found():
    engine = _engine_with_records([_rec("AA01", "DATA")], REC_LEN)
    _, resp = engine.read("TESTDS", b"ZZ99", KEY_LEN)
    assert resp == RESP_NOTFND


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_new_record():
    engine = _engine_with_records([], REC_LEN)
    assert engine.write("TESTDS", b"AA01", KEY_LEN, _rec("AA01", "NEW")) == RESP_NORMAL
    _, resp2 = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert resp2 == RESP_NORMAL


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_duplicate_returns_duprec():
    engine = _engine_with_records([_rec("AA01", "OLD")], REC_LEN)
    assert engine.write("TESTDS", b"AA01", KEY_LEN, _rec("AA01", "NEW")) == RESP_DUPREC


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_rewrite_updates_record():
    engine = _engine_with_records([_rec("AA01", "OLD")], REC_LEN)
    assert (
        engine.rewrite("TESTDS", b"AA01", KEY_LEN, _rec("AA01", "UPD")) == RESP_NORMAL
    )
    record, _ = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert b"UPD" in record


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_rewrite_without_key_extracts_key_from_record():
    """EXEC CICS REWRITE supplies FROM but no RIDFLD — the key must be taken
    from the FROM record itself (its key field), not from the passed key arg
    (which the lowering leaves empty). (CardDemo COACTUPC 9600-WRITE-PROCESSING.)"""
    engine = _engine_with_records([_rec("AA01", "OLD")], REC_LEN)
    # Empty key arg, as the REWRITE lowering passes when there is no RIDFLD.
    assert engine.rewrite("TESTDS", b"", KEY_LEN, _rec("AA01", "UPD")) == RESP_NORMAL
    record, _ = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert b"UPD" in record


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_delete_removes_record():
    engine = _engine_with_records([_rec("AA01", "DATA")], REC_LEN)
    assert engine.delete("TESTDS", b"AA01", KEY_LEN) == RESP_NORMAL
    _, resp2 = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert resp2 == RESP_NOTFND


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_browse_forward():
    engine = _engine_with_records([_rec("AA01"), _rec("BB02"), _rec("CC03")], REC_LEN)
    cursor = ("task0", "TESTDS", "cur0")
    engine.startbr("TESTDS", b"AA01", KEY_LEN, cursor)
    rec1, r1 = engine.readnext("TESTDS", cursor)
    rec2, r2 = engine.readnext("TESTDS", cursor)
    _, r3 = engine.readnext("TESTDS", cursor)
    _, r4 = engine.readnext("TESTDS", cursor)
    assert r1 == RESP_NORMAL and rec1[:4] == b"AA01"
    assert r2 == RESP_NORMAL and rec2[:4] == b"BB02"
    assert r3 == RESP_NORMAL
    assert r4 == RESP_ENDFILE
    engine.endbr("TESTDS", cursor)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_browse_reverse():
    engine = _engine_with_records([_rec("AA01"), _rec("BB02")], REC_LEN)
    cursor = ("task0", "TESTDS", "cur0")
    engine.startbr("TESTDS", b"BB02", KEY_LEN, cursor)
    engine.readnext("TESTDS", cursor)
    rec, resp = engine.readprev("TESTDS", cursor)
    assert resp == RESP_NORMAL and rec[:4] == b"AA01"


# ── Key-offset (red-dragon-7kgb) ─────────────────────────────────────


def _engine_offset(records: list[bytes], rec_len: int, key_offset: int) -> VsamEngine:
    """Engine over a single dataset whose key sits at ``key_offset``."""
    td = tempfile.mkdtemp()
    p = Path(td) / "data.txt"
    _write_fixed_records(p, records)
    config = FctConfig(
        datasets={
            "OFFDS": DatasetConfig(path=p, record_length=rec_len, key_offset=key_offset)
        }
    )
    engine = VsamEngine(config)
    engine.load_all()
    return engine


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_matches_key_at_nonzero_offset():
    # Mirror the CARD-XREF layout: card-num(16) cust-id(9) acct-id(11) = 36 here.
    rec = b"C" * 16 + b"000000001" + b"00000000011" + b"\x00" * 4
    engine = _engine_offset([rec], len(rec), key_offset=25)
    record, resp = engine.read("OFFDS", b"00000000011", 11)
    assert resp == RESP_NORMAL
    assert record is not None
    assert record[25:36] == b"00000000011"
    # The yielded record carries the cust-id at offset 16 (the read-through value).
    assert record[16:25] == b"000000001"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_offset_nonmatching_key_notfnd():
    rec = b"C" * 16 + b"000000001" + b"00000000011" + b"\x00" * 4
    engine = _engine_offset([rec], len(rec), key_offset=25)
    _, resp = engine.read("OFFDS", b"99999999999", 11)
    assert resp == RESP_NOTFND


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_default_offset_zero_unchanged():
    # key_offset defaulting to 0 must preserve offset-0 matching.
    engine = _engine_with_records([_rec("AA01", "DATA")], REC_LEN)
    record, resp = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert resp == RESP_NORMAL
    assert record is not None and record[:KEY_LEN] == b"AA01"
