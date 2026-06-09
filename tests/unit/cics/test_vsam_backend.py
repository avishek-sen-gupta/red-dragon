"""VSAM persistence backends: InMemoryBackend (default) and FileBackend."""

from __future__ import annotations

from pathlib import Path

from interpreter.cics.vsam.backend import InMemoryBackend, FileBackend
from interpreter.cics.vsam.fct import DatasetConfig
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inmemory_loads_seed_and_persist_is_noop(tmp_path: Path) -> None:
    seed = tmp_path / "seed.dat"
    seed.write_bytes(b"AAAABBBB")  # two 4-byte records
    cfg = DatasetConfig(path=seed, record_length=4)
    be = InMemoryBackend()
    assert be.load("DS", cfg) == [b"AAAA", b"BBBB"]
    be.persist("DS", cfg, [b"CCCC"])  # no-op
    assert seed.read_bytes() == b"AAAABBBB"  # seed untouched


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_backend_first_run_seeds_then_persists_to_backing_dir(
    tmp_path: Path,
) -> None:
    seed = tmp_path / "seed.dat"
    seed.write_bytes(b"AAAA")
    backing = tmp_path / "store"
    cfg = DatasetConfig(path=seed, record_length=4)
    be = FileBackend(backing)
    # first run: no backing file yet -> seed from cfg.path
    assert be.load("DS", cfg) == [b"AAAA"]
    # persist writes the backing file, NOT the seed
    be.persist("DS", cfg, [b"AAAA", b"ZZZZ"])
    assert (backing / "DS.dat").read_bytes() == b"AAAAZZZZ"
    assert seed.read_bytes() == b"AAAA"  # seed untouched
    # subsequent load reads the backing file, not the seed
    assert be.load("DS", cfg) == [b"AAAA", b"ZZZZ"]
