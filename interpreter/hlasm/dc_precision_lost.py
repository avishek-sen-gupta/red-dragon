# pyright: standard
"""An HFP DC constant whose length or scale modifier cuts its characteristic or shifts out its whole fraction, an assembly error in HLASM (ASMA073E)."""

from hlasm_asg.program.origin import Origin


class DcPrecisionLost(Exception):
    def __init__(self, constant: str, origin: Origin) -> None:
        super().__init__(
            f"{constant} at line {origin.line} of {origin.file} loses its fraction to its modifiers — ASMA073E"
        )
