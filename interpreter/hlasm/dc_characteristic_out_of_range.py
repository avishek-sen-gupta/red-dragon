# pyright: standard
"""An HFP DC constant without type extension H whose value lies outside the HFP range, an assembly error in HLASM (ASMA064S)."""

from hlasm_asg.program.origin import Origin


class DcCharacteristicOutOfRange(Exception):
    def __init__(self, constant: str, origin: Origin) -> None:
        super().__init__(
            f"{constant} at line {origin.line} of {origin.file} is outside the HFP range — ASMA064S"
        )
