"""ValueObject — WHEN [NOT] value: equal (or, negated, unequal) to its subject."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.cobol_expression import ExprNode, expr_to_dict


@dataclass(frozen=True)
class ValueObject:
    value: ExprNode
    negated: bool = False

    def to_dict(self) -> dict:
        return {"kind": "value", "value": expr_to_dict(self.value), "not": self.negated}
