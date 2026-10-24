# pyright: standard
"""One SVC 10 or SVC 120 request as its registers give it: the length, subpool and alignment, and the abend a bad release ends in."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class StorageRequest:
    length: Register
    subpool: Register
    alignment: Register
    abend: str
