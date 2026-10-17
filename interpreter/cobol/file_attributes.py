"""What OPEN tells the provider about a file from its SELECT entry: organization,
access mode, prime record key, RELATIVE KEY size, whether it is OPTIONAL, and whether its records vary in length and between which sizes.
"""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.file_enums import AccessMode, FileOrganization
from interpreter.cobol.prime_key import PrimeKey


@dataclass(frozen=True)
class FileAttributes:
    organization: FileOrganization
    access: AccessMode
    prime_key: PrimeKey
    relative_key_digits: int
    optional: bool
    variable: bool
    minimum_record_length: int
    maximum_record_length: int
