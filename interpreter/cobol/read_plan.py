"""What lowering fixes about one READ: its file, the key register it reads by, whether it
reads sequentially, whether the file is OPTIONAL, its RELATIVE KEY's digit count, and the
prime key it keeps in sequence by, if any, whether it needs the record number, and the
key of reference a keyed READ of a file with alternate keys establishes, if any."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.record_io.prime_key import PrimeKey
from interpreter.register import Register


@dataclass(frozen=True)
class ReadPlan:
    file_name: str
    key: Register
    sequential: bool
    optional: bool
    key_digits: int
    sequence: tuple[PrimeKey, ...]
    numbered: bool
    reference: tuple[int, ...] = ()
