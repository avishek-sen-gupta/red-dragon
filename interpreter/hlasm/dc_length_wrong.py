# pyright: standard
"""A DC length modifier too short for the value it holds, an assembly error in HLASM (ASMA068S)."""

from hlasm_asg.program.origin import Origin


class DcLengthWrong(Exception):
    def __init__(self, constant: str, shortest: int, origin: Origin) -> None:
        super().__init__(
            f"{constant} at line {origin.line} of {origin.file} needs a length of at least {shortest} bits — ASMA068S"
        )
