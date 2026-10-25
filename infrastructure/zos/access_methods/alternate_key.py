"""Where an alternate record key lies in a file's records, and whether its values are unique."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.zos.access_methods.prime_key import PrimeKey


@dataclass(frozen=True)
class AlternateKey:
    key: PrimeKey
    unique: bool
