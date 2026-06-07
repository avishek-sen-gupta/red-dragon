"""FCT (File Control Table) config — maps dataset names to file paths and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatasetConfig:
    path: Path
    record_length: int

    @classmethod
    def from_dict(cls, data: dict) -> DatasetConfig:
        return cls(path=Path(data["path"]), record_length=int(data["record_length"]))


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
