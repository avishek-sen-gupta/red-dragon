# pyright: standard
"""Field reference resolution — subscript parsing and offset computation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from interpreter.cobol.data_layout import FieldLayout

_SUBSCRIPT_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)\((.+)\)$")


def parse_subscript_notation(name: str) -> tuple[str, str]:
    """Parse 'FIELD(SUBSCRIPT)' notation into (base_name, subscript).

    Returns (name, "") for bare names without subscripts.
    """
    match = _SUBSCRIPT_RE.match(name)
    if match:
        return match.group(1), match.group(2)
    return name, ""


@dataclass(frozen=True)
class ResolvedFieldRef:
    """Result of resolving a field reference, possibly with a subscript.

    Attributes:
        fl: The FieldLayout for the base field.
        offset_reg: Register holding the computed byte offset.
            For bare refs, this is a CONST of fl.offset.
            For subscripted refs, this is base + (idx - 1) * element_size.
    """

    fl: FieldLayout
    offset_reg: str
