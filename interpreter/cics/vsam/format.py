"""Raw fixed-length-record flat-file codec for VSAM dataset images.

The on-disk format is a concatenation of fixed-length records (an
IDCAMS-REPRO-style sequential image) — the same format VsamEngine seeds are in,
so a written file round-trips through read_flat_file and can itself be a seed.
This is the single source of the persisted format (used by the backends and by
VsamEngine.flush_to).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable


def read_flat_file(path: Path, record_length: int) -> list[bytes]:
    """Read a flat file as a list of fixed-length records.

    A missing file yields []. Raises ValueError if the file size is not a
    multiple of record_length (corrupt / wrong record length).
    """
    if not path.exists():
        return []
    data = path.read_bytes()
    if record_length <= 0:
        raise ValueError(f"record_length must be positive, got {record_length}")
    if len(data) % record_length != 0:
        raise ValueError(
            f"{path}: size {len(data)} is not a multiple of record_length "
            f"{record_length}"
        )
    return [data[i : i + record_length] for i in range(0, len(data), record_length)]


def write_flat_file(path: Path, records: Iterable[bytes], record_length: int) -> None:
    """Write records as a fixed-length flat file, atomically.

    Each record must be exactly record_length bytes (raises ValueError otherwise).
    Writes to a temp file in the same directory then os.replace()s it into place,
    so a crash mid-write cannot truncate the dataset.
    """
    payload = bytearray()
    for rec in records:
        if len(rec) != record_length:
            raise ValueError(
                f"record length {len(rec)} != record_length {record_length}"
            )
        payload += rec
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
