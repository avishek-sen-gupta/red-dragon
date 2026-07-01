# pyright: standard
"""COBOL arithmetic expression tree.

Expression trees are emitted in structured JSON by the ProLeap bridge
(``serializeArithmeticExpr``) and consumed via :func:`expr_from_dict`. This
module defines the :data:`ExprNode` dataclass hierarchy plus the
:func:`expr_from_dict` / :func:`expr_to_dict` (de)serialization pair.
"""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.intrinsic_arity import resolve_intrinsic_args

# ── Expression tree nodes (frozen, immutable) ────────────────────


@dataclass(frozen=True)
class LiteralNode:
    """Numeric literal (integer or decimal)."""

    value: str


@dataclass(frozen=True)
class FieldRefNode:
    """Reference to a COBOL data field by name."""

    name: str
    subscripts: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class RefModNode:
    """Reference modification: field reference with start position and optional length."""

    name: str
    ref_mod_start: "ExprNode"
    ref_mod_length: "ExprNode | None" = None
    subscripts: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class BinOpNode:
    """Binary arithmetic operation."""

    op: str  # "+", "-", "*", "/"
    left: "ExprNode"
    right: "ExprNode"


@dataclass(frozen=True)
class FunctionNode:
    """Intrinsic FUNCTION call used as an expression operand.

    Appears in COMPUTE expressions and IF relation operands, e.g.
    COMPUTE X = FUNCTION TRIM(WS-A) or
    IF FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B). The bridge serializes
    it as {"kind":"function","name":..,"args":[<expr>, ...]} (red-dragon-ge72).
    """

    name: str
    args: tuple["ExprNode", ...] = ()


ExprNode = LiteralNode | FieldRefNode | RefModNode | BinOpNode | FunctionNode


def expr_from_dict(d: dict) -> ExprNode:
    """Deserialize a structured JSON expression tree (emitted by the Java bridge) into an ExprNode.

    The JSON uses "kind" as the discriminant with values:
    - {"kind": "lit", "value": "5"} — literal
    - {"kind": "ref", "name": "WS-FIELD"} — plain field reference
    - {"kind": "ref", "name": "WS-FIELD", "ref_mod_start": {...}, "ref_mod_length": {...}} — reference modification
    - {"kind": "binop", "op": "+", "left": {...}, "right": {...}} — binary operation
    - {"kind": "neg", "expr": {...}} — unary negation (folded into binop * -1)
    """
    kind = d["kind"]
    if kind == "lit":
        return LiteralNode(value=d["value"])
    if kind == "ref":
        subscripts = tuple(expr_from_dict(s) for s in d.get("subscripts", []))
        if "ref_mod_start" in d:
            return RefModNode(
                name=d["name"],
                ref_mod_start=expr_from_dict(d["ref_mod_start"]),
                ref_mod_length=(
                    expr_from_dict(d["ref_mod_length"])
                    if "ref_mod_length" in d
                    else None
                ),
                subscripts=subscripts,
            )
        return FieldRefNode(name=d["name"], subscripts=subscripts)
    if kind == "binop":
        return BinOpNode(
            op=d["op"],
            left=expr_from_dict(d["left"]),
            right=expr_from_dict(d["right"]),
        )
    if kind == "neg":
        return BinOpNode(
            op="*",
            left=LiteralNode(value="-1"),
            right=expr_from_dict(d["expr"]),
        )
    if kind == "function":
        name = d.get("name", "")
        # Route raw args through the single disambiguator so an over-split
        # arithmetic argument F(a - b) -> [a, neg(b)] is repaired (red-dragon-zgwl).
        raw_args = resolve_intrinsic_args(name, d.get("args", []) or [])
        return FunctionNode(
            name=name,
            args=tuple(expr_from_dict(a) for a in raw_args),
        )
    raise ValueError(f"Unknown expression node kind: {kind!r}")


def expr_to_dict(node: ExprNode) -> dict:
    """Serialize an ExprNode back to its structured JSON dict form.

    Inverse of :func:`expr_from_dict`. Used to round-trip subscript interiors
    (red-dragon-l445). ``neg`` is not re-emitted — a folded negation already
    lives as a ``binop`` after deserialization.
    """
    if isinstance(node, LiteralNode):
        return {"kind": "lit", "value": node.value}
    if isinstance(node, FieldRefNode):
        d: dict = {"kind": "ref", "name": node.name}
        if node.subscripts:
            d["subscripts"] = [expr_to_dict(s) for s in node.subscripts]
        return d
    if isinstance(node, RefModNode):
        d = {"kind": "ref", "name": node.name}
        d["ref_mod_start"] = expr_to_dict(node.ref_mod_start)
        if node.ref_mod_length is not None:
            d["ref_mod_length"] = expr_to_dict(node.ref_mod_length)
        if node.subscripts:
            d["subscripts"] = [expr_to_dict(s) for s in node.subscripts]
        return d
    if isinstance(node, BinOpNode):
        return {
            "kind": "binop",
            "op": node.op,
            "left": expr_to_dict(node.left),
            "right": expr_to_dict(node.right),
        }
    if isinstance(node, FunctionNode):
        return {
            "kind": "function",
            "name": node.name,
            "args": [expr_to_dict(a) for a in node.args],
        }
    raise ValueError(f"Unknown expression node type: {type(node).__name__}")
