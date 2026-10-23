# pyright: standard
"""A fixed-point DC nominal whose exponent, with the exponent modifier, lies outside HLASM's -85 to +75."""

from hlasm_asg.program.origin import Origin


class DcExponentOutOfRange(Exception):
    def __init__(self, constant: str, origin: Origin) -> None:
        super().__init__(
            f"{constant} at line {origin.line} of {origin.file} has an exponent outside -85 to +75"
        )
