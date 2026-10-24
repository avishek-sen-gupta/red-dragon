# pyright: standard
"""A fixed-point or HFP DC nominal whose exponent, with the exponent modifier, lies outside HLASM's -85 to +75 (ASMA071E)."""

from hlasm_asg.program.origin import Origin

NOMINAL_EXPONENT_RANGE = range(-85, 76)


class DcExponentOutOfRange(Exception):
    def __init__(self, constant: str, origin: Origin) -> None:
        super().__init__(
            f"{constant} at line {origin.line} of {origin.file} has an exponent outside -85 to +75 — ASMA071E"
        )
