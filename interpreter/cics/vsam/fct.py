"""FCT (File Control Table) config — dataset schema metadata only (no paths)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatasetConfig:
    record_length: int
    # Filename within the data directory (for seed_vsam / load_vsam_seed).
    file: str = ""
    # Offset (bytes) of the key within each record. 0 for a primary KSDS whose
    # key is at the record start; non-zero for alternate-index paths where the
    # key field sits inside the record (e.g. CARD-XREF ACCT-ID at offset 25).
    key_offset: int = 0
    # Declared key length in bytes. 0 means "use the length supplied at the
    # operation" (back-compat); a positive value pins the slice width so the
    # engine matches record[key_offset : key_offset + key_length].
    key_length: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> DatasetConfig:
        return cls(
            record_length=int(data["record_length"]),
            file=str(data.get("file", "")),
            key_offset=int(data.get("key_offset", 0)),
            key_length=int(data.get("key_length", 0)),
        )


@dataclass
class FctConfig:
    datasets: dict[str, DatasetConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> FctConfig:
        ds = {
            name.upper(): DatasetConfig.from_dict(cfg)
            for name, cfg in data.get("datasets", {}).items()
        }
        return cls(datasets=ds)

    @classmethod
    def from_yaml(cls, path: Path) -> FctConfig:
        import yaml

        with path.open() as f:
            return cls.from_dict(yaml.safe_load(f))
