# pyright: standard
"""An assembler warning raised while encoding one DC value, carried on its image for the unit's diagnostics."""

from dataclasses import dataclass

from interpreter.hlasm.dc_warning_kind import DcWarningKind


@dataclass(frozen=True)
class DcWarning:
    constant: str
    kind: DcWarningKind
