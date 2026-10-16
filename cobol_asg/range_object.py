"""RangeObject — WHEN [NOT] low THRU high: its subject within (or, negated, outside) the range."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.cobol_expression import ExprNode, expr_to_dict


@dataclass(frozen=True)
class RangeObject:
    low: ExprNode
    high: ExprNode
    negated: bool = False

    def to_dict(self) -> dict:
        return {
            "kind": "range",
            "from": expr_to_dict(self.low),
            "thru": expr_to_dict(self.high),
            "not": self.negated,
        }
