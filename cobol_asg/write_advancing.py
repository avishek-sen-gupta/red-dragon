"""A WRITE's ADVANCING phrase, read from the bridge: lines, PAGE or a mnemonic-name.
Without one a WRITE advances as if AFTER ADVANCING 1 LINE were written (IBM Enterprise
COBOL LR, WRITE statement, ADVANCING phrase)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from cobol_asg.advancing_lines import AdvancingLines
from cobol_asg.advancing_mnemonic import AdvancingMnemonic
from cobol_asg.advancing_page import AdvancingPage
from cobol_asg.advancing_position import AdvancingPosition
from cobol_asg.cobol_expression import (
    JsonExpr,
    LiteralNode,
    expr_from_dict,
    expr_to_dict,
)

WriteAdvancing = AdvancingLines | AdvancingPage | AdvancingMnemonic

ONE_LINE_AFTER = AdvancingLines(AdvancingPosition.AFTER, LiteralNode("1", numeric=True))

_KINDS: dict[
    str, Callable[[AdvancingPosition, Mapping[str, JsonExpr]], WriteAdvancing]
] = {
    "LINES": lambda position, data: AdvancingLines(
        position, expr_from_dict(data["lines"])
    ),
    "PAGE": lambda position, data: AdvancingPage(position),
    "MNEMONIC": lambda position, data: AdvancingMnemonic(
        position, str(data["mnemonic"])
    ),
}


def advancing_from_dict(data: Mapping[str, JsonExpr]) -> WriteAdvancing:
    return _KINDS[str(data["kind"])](AdvancingPosition(str(data["position"])), data)


def advancing_to_dict(advancing: WriteAdvancing) -> dict[str, JsonExpr | str]:
    position = {"position": advancing.position.value}
    if isinstance(advancing, AdvancingLines):
        return {**position, "kind": "LINES", "lines": expr_to_dict(advancing.lines)}
    if isinstance(advancing, AdvancingPage):
        return {**position, "kind": "PAGE"}
    return {**position, "kind": "MNEMONIC", "mnemonic": advancing.mnemonic}
