"""VSAM persistence backends.

The engine keeps records in memory (SortedDict); a backend owns the durable copy
and is selected at engine instantiation. InMemoryBackend (default) seeds from the
read-only DatasetConfig.path and never persists. FileBackend keeps a durable
write-through copy in a backing directory, separate from the seeds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from interpreter.cics.vsam.fct import DatasetConfig
from interpreter.cics.vsam.format import read_flat_file, write_flat_file


@runtime_checkable
class VsamBackend(Protocol):
    """Persistence boundary for the VSAM engine. Records are full record bytes
    in key order. The default impl preserves legacy in-memory behavior.
    """

    def load(self, name: str, cfg: DatasetConfig) -> list[bytes]:
        """Return the dataset's records (key order), or [] if none."""
        ...

    def persist(self, name: str, cfg: DatasetConfig, records: list[bytes]) -> None:
        """Durably store the dataset's records. May be a no-op (in-memory)."""
        ...


class InMemoryBackend:
    """Default: seed from the read-only DatasetConfig.path; never persist."""

    def load(self, name: str, cfg: DatasetConfig) -> list[bytes]:
        return read_flat_file(cfg.path, cfg.record_length)

    def persist(self, name: str, cfg: DatasetConfig, records: list[bytes]) -> None:
        return None


class FileBackend:
    """Write-through file persistence in a backing directory (separate from seeds).

    load() returns the backing file <backing_dir>/<NAME>.dat if it exists, else
    seeds from cfg.path (first run). persist() writes the backing file.
    """

    def __init__(self, backing_dir: Path) -> None:
        self._dir = Path(backing_dir)

    def _backing_path(self, name: str) -> Path:
        return self._dir / f"{name.upper()}.dat"

    def load(self, name: str, cfg: DatasetConfig) -> list[bytes]:
        backing = self._backing_path(name)
        if backing.exists():
            return read_flat_file(backing, cfg.record_length)
        return read_flat_file(cfg.path, cfg.record_length)

    def persist(self, name: str, cfg: DatasetConfig, records: list[bytes]) -> None:
        write_flat_file(self._backing_path(name), records, cfg.record_length)
