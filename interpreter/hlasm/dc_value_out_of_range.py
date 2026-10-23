# pyright: standard
"""A DC value that does not fit its length, an assembly error in HLASM (ASMA072E), named with the statement that holds it."""

from hlasm_asg.program.origin import Origin


class DcValueOutOfRange(Exception):
    def __init__(self, constant: str, origin: Origin) -> None:
        super().__init__(
            f"{constant} at line {origin.line} of {origin.file} does not fit its length — ASMA072E"
        )
