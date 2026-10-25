"""How a dataset's records are laid out: its organization, its records' length, and where
its prime record key and each alternate record key lie in them."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.file_enums import FileOrganization
from infrastructure.zos.access_methods.alternate_key import AlternateKey
from infrastructure.zos.access_methods.prime_key import PrimeKey


@dataclass(frozen=True)
class RecordShape:
    organization: FileOrganization
    record_length: int
    key: PrimeKey
    alternates: tuple[AlternateKey, ...] = ()
