"""VSAM dataset seeding from EBCDIC flat files."""

from __future__ import annotations

from pathlib import Path

from interpreter.cics.vsam.fct import FctConfig
from interpreter.cics.vsam.format import read_flat_file, write_flat_file


def _read_seed(
    fct_path: Path, data_dir: Path
) -> tuple[FctConfig, dict[str, list[bytes]]]:
    fct = FctConfig.from_yaml(fct_path)
    records = {
        name: read_flat_file(data_dir / cfg.file, cfg.record_length)
        for name, cfg in fct.datasets.items()
    }
    return fct, records


def load_vsam_seed(fct_path: Path, data_dir: Path) -> dict[str, list[bytes]]:
    """Read EBCDIC flat files and return {dataset_name: [records]} for InMemoryBackend."""
    _, records = _read_seed(fct_path, data_dir)
    return records


def seed_vsam(fct_path: Path, data_dir: Path, vsam_dir: Path) -> None:
    """Read EBCDIC flat files and write .dat files into vsam_dir for FileBackend."""
    fct, records = _read_seed(fct_path, data_dir)
    vsam_dir.mkdir(parents=True, exist_ok=True)
    for name, recs in records.items():
        cfg = fct.datasets[name]
        write_flat_file(vsam_dir / f"{name}.dat", recs, cfg.record_length)
