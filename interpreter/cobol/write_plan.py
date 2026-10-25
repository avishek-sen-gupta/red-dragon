"""What lowering fixes about one WRITE: its record register, the prime key it keeps in
sequence by (if any), whether it reports a record number to a RELATIVE KEY, and whether
its file is relative or indexed, so can hold a current record."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.record_io.prime_key import PrimeKey
from interpreter.register import Register


@dataclass(frozen=True)
class WritePlan:
    record: Register
    sequence: tuple[PrimeKey, ...]
    numbered: bool
    keyed: bool
