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

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class RefModLiteral:
    """Numeric literal in reference modification: 2, 3, etc."""

    value: str  # String representation of the numeric literal


@dataclass(frozen=True)
class RefModReference:
    """Data item reference in reference modification: WS-A, WS-B, etc."""

    name: str


@dataclass(frozen=True)
class RefModLengthOf:
    """LENGTH OF <field> special register inside a reference modification.

    Resolves to the byte length of the named field (a compile-time constant),
    NOT a decode of the field's value. Example: WS-DEST(LENGTH OF G + 1 : ...).
    """

    name: str


@dataclass(frozen=True)
class RefModBinOp:
    """Binary arithmetic operation in reference modification.

    Examples: WS-A + 1, WS-B - 1, WS-C * WS-A
    """

    op: str  # "+", "-", "*", "/"
    left: RefModExpr
    right: RefModExpr


# Discriminated union of all reference modification expression types
RefModExpr = Union[RefModLiteral, RefModReference, RefModLengthOf, RefModBinOp]


def ref_mod_expr_from_dict(data: dict) -> RefModExpr:
    """Construct RefModExpr from JSON dict representation.

    Expected formats:
      {"kind": "lit", "value": "2"}
      {"kind": "ref", "name": "WS-A"}
      {"kind": "binop", "op": "+", "left": {...}, "right": {...}}
    """
    kind = data.get("kind")

    if kind == "lit":
        return RefModLiteral(value=data.get("value", ""))

    elif kind == "ref":
        return RefModReference(name=data.get("name", ""))

    elif kind == "length_of":
        return RefModLengthOf(name=data.get("name", ""))

    elif kind == "binop":
        left = ref_mod_expr_from_dict(data.get("left", {}))
        right = ref_mod_expr_from_dict(data.get("right", {}))
        return RefModBinOp(op=data.get("op", ""), left=left, right=right)

    else:
        # Unknown kind—default to literal with empty value
        return RefModLiteral(value="")


def _ref_mod_expr_to_dict(expr: RefModExpr) -> dict:
    """Serialize RefModExpr back to JSON dict format."""
    if isinstance(expr, RefModLiteral):
        return {"kind": "lit", "value": expr.value}
    elif isinstance(expr, RefModReference):
        return {"kind": "ref", "name": expr.name}
    elif isinstance(expr, RefModLengthOf):
        return {"kind": "length_of", "name": expr.name}
    elif isinstance(expr, RefModBinOp):
        return {
            "kind": "binop",
            "op": expr.op,
            "left": _ref_mod_expr_to_dict(expr.left),
            "right": _ref_mod_expr_to_dict(expr.right),
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
    def from_dict(cls, data: dict) -> FunctionCallOperand:
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
    length_of: str = ""
    qualifiers: tuple[str, ...] = ()
    subscripts: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> RefModOperand:
        """Construct RefModOperand from JSON dict representation.

        Expected formats:
          {"name": "WS-FIELD"}
          {"name": "WS-FIELD", "ref_mod_start": {...}, "ref_mod_length": {...}}
          {"kind": "length_of", "name": "WS-FIELD"}  (a ``LENGTH OF`` source)

        A ``LENGTH OF X`` source operand carries ``length_of="X"`` (the data
        name whose byte length is the source value), with ``name`` left empty so
        it never resolves as a field. This mirrors the bridge's structured
        ``length_of`` node already used for PERFORM VARYING FROM (red-dragon).
        """
        if isinstance(data, str):
            # Fallback for legacy string format
            return cls(name=data)

        if data.get("kind") == "length_of":
            return cls(name="", length_of=data.get("name", ""))

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
        subscripts = tuple(data.get("subscripts", ()))

        return cls(
            name=name,
            ref_mod_start=ref_mod_start,
            ref_mod_length=ref_mod_length,
            qualifiers=qualifiers,
            subscripts=subscripts,
        )

    def to_dict(self) -> dict:
        """Serialize RefModOperand to JSON dict format."""
        if self.length_of:
            return {"kind": "length_of", "name": self.length_of}
        result: dict = {"name": self.name}
        if self.ref_mod_start is not None:
            result["ref_mod_start"] = _ref_mod_expr_to_dict(self.ref_mod_start)
        if self.ref_mod_length is not None:
            result["ref_mod_length"] = _ref_mod_expr_to_dict(self.ref_mod_length)
        if self.qualifiers:
            result["qualifiers"] = list(self.qualifiers)
        if self.subscripts:
            result["subscripts"] = list(self.subscripts)
        return result
