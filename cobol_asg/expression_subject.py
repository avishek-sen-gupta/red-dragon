"""ExpressionSubject — an EVALUATE subject that is an identifier, literal or arithmetic expression."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.cobol_expression import ExprNode, expr_to_dict


@dataclass(frozen=True)
class ExpressionSubject:
    expr: ExprNode

    def to_dict(self) -> dict:
        return {"kind": "expr", "expr": expr_to_dict(self.expr)}
