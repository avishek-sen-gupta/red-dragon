"""SetOperand — one target or value of a SET statement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cobol_asg.operand_kind import OperandKind


@dataclass(frozen=True)
class SetOperand:
    kind: OperandKind
    name: str = ""
    qualifiers: tuple[str, ...] = ()
    subscripts: tuple[str, ...] = ()
    value: str = ""

    @property
    def text(self) -> str:
        """The name a reference or ADDRESS OF names, or a literal's text."""
        return self.name if self.kind in _NAMED else self.value

    def to_dict(self) -> dict:
        if self.kind in _NAMED:
            return {
                "kind": self.kind.value,
                "name": self.name,
                "qualifiers": list(self.qualifiers),
                "subscripts": list(self.subscripts),
            }
        return {"kind": self.kind.value, "value": self.value}


_NAMED = frozenset({OperandKind.REF, OperandKind.ADDRESS_OF})


def set_operand_from_dict(data: Mapping[str, str | Sequence[str]]) -> SetOperand:
    return SetOperand(
        kind=OperandKind(str(data["kind"])),
        name=str(data.get("name", "")),
        qualifiers=tuple(str(q) for q in data.get("qualifiers", ())),
        subscripts=tuple(str(s) for s in data.get("subscripts", ())),
        value=str(data.get("value", "")),
    )
