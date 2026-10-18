# pyright: standard
"""Reference modification expression structures for COBOL MOVE operands.

Represents arithmetic expressions used in reference modification syntax:
  WS-FIELD(start:length)

Where start and length can be:
  - Numeric literals: 2, 3
  - Data item references: WS-A, WS-B
  - Arithmetic expressions: WS-A + 1, WS-B - 1, WS-A * WS-B, etc.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Union

from cobol_asg.cobol_expression import (
    ExprNode,
    JsonExpr,
    expr_from_dict,
    expr_to_dict,
)
from cobol_asg.operand_kind import OperandKind


@dataclass(frozen=True)
class RefModLiteral:
    """Numeric literal in reference modification: 2, 3, etc."""

    value: str  # String representation of the numeric literal


@dataclass(frozen=True)
class RefModReference:
    """Data item reference in reference modification: WS-A, WS-B, etc.

    ``qualifiers`` are the bound's own ``OF``/``IN`` group names -- the GB in
    ``FA OF GA(1:FB OF GB)`` qualifies the bound, never the slice
    (red-dragon-64s4, red-dragon-2afo).
    """

    name: str
    qualifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefModLengthOf:
    """LENGTH OF <field> special register inside a reference modification.

    Resolves to the byte length of the named field (a compile-time constant),
    NOT a decode of the field's value. Example: WS-DEST(LENGTH OF G + 1 : ...).
    ``qualifiers`` are the measured item's ``OF``/``IN`` group names.
    """

    name: str
    qualifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefModFunction:
    """An intrinsic FUNCTION call computing a reference-modification bound.

    ``M(1:FUNCTION LENGTH(M))`` — the call is the bound; the operand is still the
    slice of ``M`` (red-dragon-pe45). ``args`` are structured expression dicts,
    the same shape ``FunctionCallOperand`` carries.
    """

    name: str
    args: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RefModBinOp:
    """Binary arithmetic operation in reference modification.

    Examples: WS-A + 1, WS-B - 1, WS-C * WS-A
    """

    op: str  # "+", "-", "*", "/"
    left: RefModExpr
    right: RefModExpr


# Discriminated union of all reference modification expression types
RefModExpr = Union[
    RefModLiteral, RefModReference, RefModLengthOf, RefModFunction, RefModBinOp
]


def length_of_from_dict(data: JsonExpr) -> RefModLengthOf:
    """The ``LENGTH OF`` node the bridge writes: the measured item's name and
    qualifiers."""
    qualifiers = data.get("qualifiers", ())
    return RefModLengthOf(
        name=str(data.get("name", "")),
        qualifiers=(
            tuple(str(q) for q in qualifiers) if isinstance(qualifiers, list) else ()
        ),
    )


def ref_mod_expr_from_dict(data: dict) -> RefModExpr:
    """Construct RefModExpr from JSON dict representation.

    Expected formats:
      {"kind": "lit", "value": "2"}
      {"kind": "ref", "name": "WS-A"}
      {"kind": "binop", "op": "+", "left": {...}, "right": {...}}
      {"kind": "function", "name": "LENGTH", "args": [{...}]}
    """
    kind = data.get("kind")

    if kind == "lit":
        return RefModLiteral(value=data.get("value", ""))

    elif kind == "ref":
        return RefModReference(
            name=data.get("name", ""),
            qualifiers=tuple(data.get("qualifiers", ())),
        )

    elif kind == "length_of":
        return length_of_from_dict(data)

    elif kind == "function":
        return RefModFunction(
            name=data.get("name", ""), args=tuple(data.get("args", []) or [])
        )

    elif kind == "binop":
        left = ref_mod_expr_from_dict(data.get("left", {}))
        right = ref_mod_expr_from_dict(data.get("right", {}))
        return RefModBinOp(op=data.get("op", ""), left=left, right=right)

    else:
        # Unknown kind—default to literal with empty value
        return RefModLiteral(value="")


def ref_mod_expr_to_dict(expr: RefModExpr) -> dict:
    """Serialize RefModExpr back to JSON dict format."""
    if isinstance(expr, RefModLiteral):
        return {"kind": "lit", "value": expr.value}
    elif isinstance(expr, RefModReference):
        ref: dict = {"kind": "ref", "name": expr.name}
        if expr.qualifiers:
            ref["qualifiers"] = list(expr.qualifiers)
        return ref
    elif isinstance(expr, RefModLengthOf):
        return {
            "kind": "length_of",
            "name": expr.name,
            **({"qualifiers": list(expr.qualifiers)} if expr.qualifiers else {}),
        }
    elif isinstance(expr, RefModFunction):
        return {"kind": "function", "name": expr.name, "args": list(expr.args)}
    elif isinstance(expr, RefModBinOp):
        return {
            "kind": "binop",
            "op": expr.op,
            "left": ref_mod_expr_to_dict(expr.left),
            "right": ref_mod_expr_to_dict(expr.right),
        }
    return {"kind": "lit", "value": "0"}


@dataclass(frozen=True)
class FunctionCallOperand:
    """COBOL intrinsic FUNCTION call used as a value source.

    Serialized by the bridge as {"kind": "function", "name": "...", "args": [...]}.
    Each arg is a structured expression dict (the same shape consumed by the
    COBOL expression lowering): {"kind": "ref"|"lit"|"binop"|..., ...}.

    Example: FUNCTION UPPER-CASE(WS-IN) → FunctionCallOperand(
        name="UPPER-CASE", args=[{"kind": "ref", "name": "WS-IN"}])
    """

    name: str
    args: tuple[dict, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping) -> FunctionCallOperand:
        raw_args = data.get("args", []) or []
        return cls(name=data.get("name", ""), args=tuple(raw_args))


def is_function_operand(data: object) -> bool:
    """True when an operand dict represents an intrinsic FUNCTION call node."""
    return isinstance(data, dict) and data.get("kind") == "function"


@dataclass(frozen=True)
class RefModOperand:
    """MOVE statement operand with optional reference modification.

    Examples:
      RefModOperand(name="WS-FIELD", ref_mod_start=None, ref_mod_length=None)
      RefModOperand(name="WS-FIELD", ref_mod_start=RefModLiteral("2"), ref_mod_length=RefModLiteral("3"))
      RefModOperand(name="WS-FIELD", ref_mod_start=RefModReference("WS-A"), ref_mod_length=RefModReference("WS-B"))
    """

    name: str
    ref_mod_start: RefModExpr | None = None
    ref_mod_length: RefModExpr | None = None
    length_of: RefModLengthOf = RefModLengthOf(name="")
    qualifiers: tuple[str, ...] = ()
    subscripts: tuple[ExprNode, ...] = ()
    rounded: bool = False
    kind: OperandKind = OperandKind.REF

    @property
    def is_reference_modified(self) -> bool:
        return self.ref_mod_start is not None

    @property
    def names_data(self) -> bool:
        """A data reference was written, not a literal or figurative constant."""
        return self.kind is OperandKind.REF and bool(self.name)

    @classmethod
    def of_all(cls, data: Mapping) -> RefModOperand:
        """The figurative constant ALL literal: the literal, repeated.

        ALL of a figurative constant is that figurative constant (ANSI X3.23-1985
        figurative constants).
        """
        if data["literal_kind"] == OperandKind.FIGURATIVE.value:
            return cls(name=data["literal"], kind=OperandKind.FIGURATIVE)
        return cls(name=data["literal"], kind=OperandKind.ALL_LITERAL)

    @classmethod
    def from_dict(cls, data: dict) -> RefModOperand:
        """Construct RefModOperand from JSON dict representation.

        Expected formats:
          {"name": "WS-FIELD"}
          {"name": "WS-FIELD", "ref_mod_start": {...}, "ref_mod_length": {...}}
          {"kind": "length_of", "name": "WS-FIELD"}  (a ``LENGTH OF`` source)

        A ``LENGTH OF X`` source operand carries ``length_of`` (the qualified
        data name whose byte length is the source value), with ``name`` left empty so
        it never resolves as a field. This mirrors the bridge's structured
        ``length_of`` node already used for PERFORM VARYING FROM (red-dragon).
        """
        if isinstance(data, str):
            # Fallback for legacy string format
            return cls(name=data)

        if data.get("kind") == "length_of":
            return cls(
                name="",
                length_of=length_of_from_dict(data),
                kind=OperandKind.LENGTH_OF,
            )

        if data.get("kind") == OperandKind.FIGURATIVE.value and "literal" in data:
            return cls.of_all(data)

        name = data.get("name", "")
        ref_mod_start_data = data.get("ref_mod_start")
        ref_mod_length_data = data.get("ref_mod_length")

        ref_mod_start = None
        if ref_mod_start_data is not None:
            ref_mod_start = ref_mod_expr_from_dict(ref_mod_start_data)

        ref_mod_length = None
        if ref_mod_length_data is not None:
            ref_mod_length = ref_mod_expr_from_dict(ref_mod_length_data)

        qualifiers = tuple(data.get("qualifiers", ()))
        subscripts = tuple(expr_from_dict(s) for s in data.get("subscripts", []))
        rounded = data.get("rounded", False) if isinstance(data, dict) else False

        return cls(
            name=name,
            ref_mod_start=ref_mod_start,
            ref_mod_length=ref_mod_length,
            qualifiers=qualifiers,
            subscripts=subscripts,
            rounded=rounded,
            kind=_LITERAL_KINDS.get(data.get("kind", ""), OperandKind.REF),
        )

    def to_dict(self) -> dict:
        """Serialize RefModOperand to JSON dict format."""
        if self.length_of.name:
            return ref_mod_expr_to_dict(self.length_of)
        if self.kind is OperandKind.ALL_LITERAL:
            return {
                "kind": OperandKind.FIGURATIVE.value,
                "name": _ALL,
                "literal": self.name,
                "literal_kind": OperandKind.LIT.value,
            }
        result: dict = {
            **literal_kind_dict(self),
            "name": self.name,
        }
        if self.ref_mod_start is not None:
            result["ref_mod_start"] = ref_mod_expr_to_dict(self.ref_mod_start)
        if self.ref_mod_length is not None:
            result["ref_mod_length"] = ref_mod_expr_to_dict(self.ref_mod_length)
        if self.qualifiers:
            result["qualifiers"] = list(self.qualifiers)
        if self.subscripts:
            result["subscripts"] = [expr_to_dict(s) for s in self.subscripts]
        if self.rounded:
            result["rounded"] = True
        return result


_ALL = "ALL"

_LITERAL_KINDS = {
    OperandKind.LIT.value: OperandKind.LIT,
    OperandKind.FIGURATIVE.value: OperandKind.FIGURATIVE,
}


def literal_kind_dict(operand: RefModOperand) -> dict:
    """The kind key a literal or figurative operand is written with; none for a reference."""
    return {"kind": operand.kind.value} if operand.kind.value in _LITERAL_KINDS else {}
