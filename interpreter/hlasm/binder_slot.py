# pyright: standard
"""Bytes of a Q, J or CXD constant: a field the binder fills with an external dummy section's offset or length, or the total of them all."""

from dataclasses import dataclass

from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_target import RelocationTarget


@dataclass(frozen=True)
class BinderSlot:
    kind: RelocationKind
    target: RelocationTarget
    width: int
