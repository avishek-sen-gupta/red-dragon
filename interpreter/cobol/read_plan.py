"""What lowering fixes about one READ: its file, the key register it reads by, whether it
reads sequentially, whether the file is OPTIONAL, and its RELATIVE KEY's digit count."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class ReadPlan:
    file_name: str
    key: Register
    sequential: bool
    optional: bool
    key_digits: int
