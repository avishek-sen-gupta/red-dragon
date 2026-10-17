"""A field of a CORRESPONDING sending group and the like-named field of the receiving group."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.data_layout import FieldLayout


@dataclass(frozen=True)
class CorrespondingPair:
    source: FieldLayout
    target: FieldLayout
