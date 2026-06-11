"""VSAM persistence backends: InMemoryBackend (default) and FileBackend."""

from __future__ import annotations

from pathlib import Path

from interpreter.cics.vsam.backend import InMemoryBackend, FileBackend
from interpreter.cics.vsam.fct import DatasetConfig
from tests.covers import covers, NotLanguageFeature


def _cfg(record_length: int = 4) -> DatasetConfig:
    return DatasetConfig(record_length=record_length)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inmemory_empty_by_default() -> None:
    be = InMemoryBackend()
    assert be.load("DS", _cfg()) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inmemory_loads_from_seed_dict() -> None:
    be = InMemoryBackend(seed={"DS": [b"AAAA", b"BBBB"]})
    assert be.load("DS", _cfg()) == [b"AAAA", b"BBBB"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inmemory_seed_lookup_is_case_insensitive() -> None:
    be = InMemoryBackend(seed={"ACCTFILE": [b"AAAA"]})
    assert be.load("acctfile", _cfg()) == [b"AAAA"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inmemory_persist_is_noop() -> None:
    be = InMemoryBackend(seed={"DS": [b"AAAA"]})
    be.persist("DS", _cfg(), [b"ZZZZ"])
    assert be.load("DS", _cfg()) == [b"AAAA"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_backend_empty_when_no_dat_file(tmp_path: Path) -> None:
    be = FileBackend(tmp_path / "store")
    assert be.load("DS", _cfg()) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_backend_persists_and_reloads(tmp_path: Path) -> None:
    backing = tmp_path / "store"
    be = FileBackend(backing)
    be.persist("DS", _cfg(), [b"AAAA", b"ZZZZ"])
    assert (backing / "DS.dat").read_bytes() == b"AAAAZZZZ"
    assert be.load("DS", _cfg()) == [b"AAAA", b"ZZZZ"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_backend_load_uses_dat_file_not_seed(tmp_path: Path) -> None:
    backing = tmp_path / "store"
    be = FileBackend(backing)
    be.persist("DS", _cfg(), [b"AAAA"])
    be.persist("DS", _cfg(), [b"AAAA", b"ZZZZ"])
    assert be.load("DS", _cfg()) == [b"AAAA", b"ZZZZ"]
