# pyright: standard
"""An object module's RLD record: a field of a section that the binder fills with the target's value, signed, plus the addend."""

from dataclasses import dataclass

from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.relocation_target import RelocationTarget


@dataclass(frozen=True)
class RelocationRecord:
    section: str
    offset: int
    length: int
    kind: RelocationKind
    target: RelocationTarget
    sign: RelocationSign
    addend: int
