"""An FD's LINAGE clause: the logical page of the file it describes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cobol_asg.cobol_expression import (
    ExprNode,
    JsonExpr,
    LiteralNode,
    expr_from_dict,
    expr_to_dict,
)
from cobol_asg.no_footing import NO_FOOTING, NoFooting

_NO_MARGIN = LiteralNode("0", numeric=True)


@dataclass(frozen=True)
class LinageClause:
    """LINAGE IS lines [WITH FOOTING AT footing] [LINES AT TOP top] [LINES AT
    BOTTOM bottom]: each an integer or a data-name, a margin not written being 0."""

    lines: ExprNode
    footing: ExprNode | NoFooting = NO_FOOTING
    top: ExprNode = _NO_MARGIN
    bottom: ExprNode = _NO_MARGIN

    @classmethod
    def from_dict(cls, data: Mapping[str, JsonExpr]) -> LinageClause:
        return cls(
            lines=expr_from_dict(data["lines"]),
            footing=(
                expr_from_dict(data["footing"]) if "footing" in data else NO_FOOTING
            ),
            top=expr_from_dict(data["top"]) if "top" in data else _NO_MARGIN,
            bottom=expr_from_dict(data["bottom"]) if "bottom" in data else _NO_MARGIN,
        )

    def to_dict(self) -> dict[str, JsonExpr]:
        footing = (
            {} if isinstance(self.footing, NoFooting) else {"footing": self.footing}
        )
        written = {
            "lines": self.lines,
            **footing,
            "top": self.top,
            "bottom": self.bottom,
        }
        return {key: expr_to_dict(node) for key, node in written.items()}
