# pyright: standard
"""Two units linked into one image declare the same program."""

from pathlib import Path


class DuplicateProgramInImage(Exception):
    def __init__(self, program: str, first: Path, second: Path) -> None:
        super().__init__(
            f"program {program} is in the image twice: {first.name} and {second.name}"
        )
