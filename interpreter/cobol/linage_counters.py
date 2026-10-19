"""A program's special registers: RETURN-CODE, and one LINAGE-COUNTER for each FD with
a LINAGE clause, declared under its file's name so that LINAGE-COUNTER OF file-name
selects it (IBM Enterprise COBOL LR, LINAGE-COUNTER)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_expression import ExprNode, FieldRefNode, LiteralNode
from cobol_asg.linage_clause import LinageClause
from cobol_asg.storage_layout import section_layout
from interpreter.cobol.data_layout import DataLayout, build_data_layout
from interpreter.cobol.special_registers import RETURN_CODE_FIELD
from interpreter.cobol.undeclared_data_name import UndeclaredDataName

LINAGE_COUNTER_NAME = "LINAGE-COUNTER"
_BINARY = "BINARY"
_GROUP_USAGE = "DISPLAY"
_COUNTER_LEVEL = 5


def special_registers_layout(asg: CobolASG) -> DataLayout:
    return build_data_layout(
        section_layout(
            [
                RETURN_CODE_FIELD,
                *(_counter_of(asg, name, clause) for name, clause in linage_files(asg)),
            ]
        )
    )


def linage_files(asg: CobolASG) -> tuple[tuple[str, LinageClause], ...]:
    """Each FD with a LINAGE clause, by file name."""
    return tuple(
        (fd.fd_name, fd.linage)
        for fd in asg.file_descriptions
        if isinstance(fd.linage, LinageClause)
    )


def _counter_of(asg: CobolASG, file_name: str, clause: LinageClause) -> CobolField:
    pic, usage = _description(asg, clause.lines)
    return CobolField(
        name=file_name,
        level=1,
        pic="",
        usage=_GROUP_USAGE,
        offset=0,
        children=[
            CobolField(
                name=LINAGE_COUNTER_NAME,
                level=_COUNTER_LEVEL,
                pic=pic,
                usage=usage,
                offset=0,
            )
        ],
    )


def _description(asg: CobolASG, lines: ExprNode) -> tuple[str, str]:
    """A data-name's PICTURE and USAGE; for an integer, a binary item of its digits."""
    if isinstance(lines, LiteralNode):
        return f"9({len(lines.value)})", _BINARY
    if not isinstance(lines, FieldRefNode):
        raise TypeError(f"LINAGE operand {lines!r} is neither integer nor data-name")
    item = _declared(asg, lines.name)
    return item.pic, item.usage


def _declared(asg: CobolASG, name: str) -> CobolField:
    found = [
        item
        for item in _items(
            (
                *asg.data_fields,
                *asg.local_storage_fields,
                *asg.linkage_fields,
                *asg.file_fields,
            )
        )
        if item.name.upper() == name.upper()
    ]
    if not found:
        raise UndeclaredDataName(name)
    return found[0]


def _items(items: Sequence[CobolField]) -> Iterator[CobolField]:
    for item in items:
        yield item
        yield from _items(item.children)
