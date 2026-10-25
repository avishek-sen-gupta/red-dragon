# pyright: standard
"""Tests for COBOL file organization drivers."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import OpenMode
from infrastructure.zos.access_methods.access_result import AccessCondition
from infrastructure.zos.access_methods.file_drivers import (
    IndexedDriver,
    RelativeDriver,
    SequentialDriver,
)
from infrastructure.zos.access_methods.prime_key import PrimeKey
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

RL = 10  # record length for all tests


def _b(s: str) -> bytes:
    return s.encode().ljust(RL)[:RL]


class TestSequentialDriver:
    @covers(CobolFeature.WRITE)
    def test_write_and_read_three(self, tmp_path: Path) -> None:
        path = tmp_path / "seq.dat"
        drv = SequentialDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("AAAA"))
        drv.write(_b("BBBB"))
        drv.write(_b("CCCC"))
        drv.close()

        drv2 = SequentialDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        assert drv2.read_seq().data is not None and drv2.read_seq().data  # type: ignore[union-attr]

    @covers(CobolFeature.READ)
    def test_read_all_three_in_order(self, tmp_path: Path) -> None:
        path = tmp_path / "seq.dat"
        drv = SequentialDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("AAAA"))
        drv.write(_b("BBBB"))
        drv.write(_b("CCCC"))
        drv.close()

        drv2 = SequentialDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        r1 = drv2.read_seq()
        r2 = drv2.read_seq()
        r3 = drv2.read_seq()
        eof = drv2.read_seq()
        drv2.close()
        assert (
            r1.condition is AccessCondition.OK
            and r1.data is not None
            and b"AAAA" in r1.data
        )
        assert (
            r2.condition is AccessCondition.OK
            and r2.data is not None
            and b"BBBB" in r2.data
        )
        assert (
            r3.condition is AccessCondition.OK
            and r3.data is not None
            and b"CCCC" in r3.data
        )
        assert eof.condition is AccessCondition.END_OF_FILE

    @covers(CobolFeature.REWRITE)
    def test_rewrite_updates_last_read(self, tmp_path: Path) -> None:
        path = tmp_path / "seq.dat"
        drv = SequentialDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("AAAA"))
        drv.write(_b("BBBB"))
        drv.close()

        drv2 = SequentialDriver()
        drv2.open(path, OpenMode.IO, RL, PrimeKey(0, 0))
        drv2.read_seq()
        drv2.rewrite(_b("XXXX"))
        drv2.close()

        drv3 = SequentialDriver()
        drv3.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        first = drv3.read_seq()
        drv3.close()
        assert first.data is not None and b"XXXX" in first.data

    @covers(CobolFeature.WRITE)
    def test_write_in_input_mode_returns_48(self, tmp_path: Path) -> None:
        path = tmp_path / "seq.dat"
        drv = SequentialDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("AAAA"))
        drv.close()

        drv2 = SequentialDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        result = drv2.write(_b("BBBB"))
        drv2.close()
        assert result.condition is AccessCondition.WRITE_NOT_PERMITTED


class TestIndexedDriver:
    KO = 0
    KL = 3

    @covers(CobolFeature.WRITE)
    def test_write_sorted_by_key(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        drv.write(_b("CCC"))
        drv.write(_b("AAA"))
        drv.write(_b("BBB"))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(self.KO, self.KL))
        r = drv2.read_key(b"AAA")
        drv2.close()
        assert r.condition is AccessCondition.OK
        assert r.data is not None and r.data[:3] == b"AAA"

    @covers(CobolFeature.WRITE)
    def test_duplicate_key_returns_22(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        drv.write(_b("AAA"))
        result = drv.write(_b("AAA"))
        drv.close()
        assert result.condition is AccessCondition.DUPLICATE_KEY

    @covers(CobolFeature.READ)
    def test_missing_key_returns_23(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        drv.write(_b("AAA"))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(self.KO, self.KL))
        r = drv2.read_key(b"ZZZ")
        drv2.close()
        assert r.condition is AccessCondition.NOT_FOUND

    @covers(CobolFeature.DELETE_RECORD)
    def test_delete_compacts_file(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        drv.write(_b("AAA"))
        drv.write(_b("BBB"))
        drv.write(_b("CCC"))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.IO, RL, PrimeKey(self.KO, self.KL))
        drv2.read_key(b"BBB")
        drv2.delete()
        drv2.close()

        drv3 = IndexedDriver()
        drv3.open(path, OpenMode.INPUT, RL, PrimeKey(self.KO, self.KL))
        r = drv3.read_key(b"BBB")
        drv3.close()
        assert r.condition is AccessCondition.NOT_FOUND

    @covers(CobolFeature.DELETE_RECORD)
    @covers(CobolFeature.WRITE)
    def test_a_scan_continues_past_records_deleted_or_inserted_behind_it(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        [drv.write(_b(k)) for k in ("BBB", "DDD", "FFF", "HHH")]
        drv.close()
        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.IO, RL, PrimeKey(self.KO, self.KL))
        first = drv2.read_seq().data
        drv2.delete()
        after_delete = drv2.read_seq().data
        drv2.write(_b("AAA"))
        after_insert = drv2.read_seq().data
        drv2.close()
        assert (first, after_delete, after_insert) == (_b("BBB"), _b("DDD"), _b("FFF"))

    @covers(CobolFeature.WRITE)
    def test_write_in_input_mode_returns_48(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        drv.write(_b("AAA"))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(self.KO, self.KL))
        result = drv2.write(_b("BBB"))
        drv2.close()
        assert result.condition is AccessCondition.WRITE_NOT_PERMITTED

    @covers(CobolFeature.START)
    def test_start_positions_for_seq_scan(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        for c in ["AAA", "BBB", "CCC", "DDD"]:
            drv.write(_b(c))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(self.KO, self.KL))
        drv2.start(b"BBB", ">=")
        r1 = drv2.read_seq()
        r2 = drv2.read_seq()
        drv2.close()
        assert r1.data is not None and r1.data[:3] == b"BBB"
        assert r2.data is not None and r2.data[:3] == b"CCC"

    @covers(CobolFeature.START)
    def test_start_compares_a_shorter_key_with_the_keys_leading_bytes(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(self.KO, self.KL))
        [drv.write(_b(k)) for k in ("AAX", "BBA", "BBB", "CCA")]
        drv.close()
        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(self.KO, self.KL))
        starts = [
            (relop, prefix, drv2.start(prefix, relop).condition, drv2.read_seq().data)
            for relop, prefix in (("=", b"BB"), (">", b"BB"), (">=", b"AB"))
        ]
        missing = drv2.start(b"BC", "=").condition
        drv2.close()
        assert (starts, missing) == (
            [
                ("=", b"BB", AccessCondition.OK, _b("BBA")),
                (">", b"BB", AccessCondition.OK, _b("CCA")),
                (">=", b"AB", AccessCondition.OK, _b("BBA")),
            ],
            AccessCondition.NOT_FOUND,
        )


class TestRelativeDriver:
    @covers(CobolFeature.WRITE)
    def test_write_slot_3_and_read(self, tmp_path: Path) -> None:
        path = tmp_path / "rel.dat"
        k3 = (3).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("SLOT3"), key=k3)
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        r = drv2.read_key(k3)
        drv2.close()
        assert r.condition is AccessCondition.OK
        assert r.data is not None and b"SLOT3" in r.data

    @covers(CobolFeature.READ)
    def test_empty_slot_returns_23(self, tmp_path: Path) -> None:
        path = tmp_path / "rel.dat"
        k1 = (1).to_bytes(4, "big")
        k3 = (3).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("SLOT3"), key=k3)
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        r = drv2.read_key(k1)
        drv2.close()
        assert r.condition is AccessCondition.NOT_FOUND

    @covers(CobolFeature.DELETE_RECORD)
    def test_delete_clears_flag(self, tmp_path: Path) -> None:
        path = tmp_path / "rel.dat"
        k2 = (2).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("SLOT2"), key=k2)
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.IO, RL, PrimeKey(0, 0))
        drv2.read_key(k2)
        drv2.delete()
        drv2.close()

        drv3 = RelativeDriver()
        drv3.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        r = drv3.read_key(k2)
        drv3.close()
        assert r.condition is AccessCondition.NOT_FOUND

    @covers(CobolFeature.WRITE)
    def test_write_in_input_mode_returns_48(self, tmp_path: Path) -> None:
        path = tmp_path / "rel.dat"
        k1 = (1).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("SLOT1"), key=k1)
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        result = drv2.write(_b("SLOT2"), key=(2).to_bytes(4, "big"))
        drv2.close()
        assert result.condition is AccessCondition.WRITE_NOT_PERMITTED

    @covers(CobolFeature.READ)
    def test_seq_read_skips_empty_slots(self, tmp_path: Path) -> None:
        path = tmp_path / "rel.dat"
        k1 = (1).to_bytes(4, "big")
        k3 = (3).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        drv.write(_b("SLOT1"), key=k1)
        drv.write(_b("SLOT3"), key=k3)
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        r1 = drv2.read_seq()
        r2 = drv2.read_seq()
        eof = drv2.read_seq()
        drv2.close()
        assert r1.data is not None and b"SLOT1" in r1.data
        assert r2.data is not None and b"SLOT3" in r2.data
        assert eof.condition is AccessCondition.END_OF_FILE

    @covers(CobolFeature.START)
    def test_start_positions_by_its_relation_to_the_record_number(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "rel.dat"
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RL, PrimeKey(0, 0))
        [drv.write(_b(f"SLOT{n}"), key=n.to_bytes(4, "big")) for n in (2, 5, 7)]
        drv.close()
        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RL, PrimeKey(0, 0))
        starts = [
            (relop, n, drv2.start(n.to_bytes(4, "big"), relop).condition)
            for relop, n in (("=", 3), (">", 7))
        ]
        found = [
            (relop, n, drv2.start(n.to_bytes(4, "big"), relop).condition)
            + (drv2.read_seq().record_number,)
            for relop, n in (("=", 5), (">=", 3), (">", 5), (">", 0))
        ]
        drv2.close()
        assert (starts, found) == (
            [("=", 3, AccessCondition.NOT_FOUND), (">", 7, AccessCondition.NOT_FOUND)],
            [
                ("=", 5, AccessCondition.OK, 5),
                (">=", 3, AccessCondition.OK, 5),
                (">", 5, AccessCondition.OK, 7),
                (">", 0, AccessCondition.OK, 2),
            ],
        )
