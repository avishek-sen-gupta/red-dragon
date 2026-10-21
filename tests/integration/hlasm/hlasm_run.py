# pyright: standard
"""What a standalone run left: R15 on return, the abend code, the console."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HlasmRun:
    return_code: int
    abend: str
    stdout: str
