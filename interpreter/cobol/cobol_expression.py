# pyright: standard
"""COBOL arithmetic expression tree.

Expression trees are emitted in structured JSON by the ProLeap bridge
(``serializeArithmeticExpr``) and consumed via :func:`expr_from_dict`. This
module defines the :data:`ExprNode` dataclass hierarchy plus the
:func:`expr_from_dict` / :func:`expr_to_dict` (de)serialization pair.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Expression tree nodes (frozen, immutable) ────────────────────


@dataclass(frozen=True)
class LiteralNode:
    """Numeric literal (integer or decimal)."""

    value: str


@dataclass(frozen=True)
class FigurativeNode:
    """A figurative constant used as an operand: ``COMPUTE WS-PCT = ZEROES``.

    ``value`` is the canonical spelling the bridge normalises to (ZEROS, SPACES,
    LOW-VALUES, HIGH-VALUES, QUOTES), not the one the program wrote -- ZERO,
    ZEROS and ZEROES all arrive as ZEROS.
    """

    value: str


@dataclass(frozen=True)
class LengthOfNode:
    """``LENGTH OF <field>``: the field's byte length, a compile-time constant.

    Not a read of the field's value, which is why this is not a FieldRefNode --
    a consumer counting data dependencies must not treat it as one.
    """

    name: str


@dataclass(frozen=True)
class DfhRespNode:
    """``DFHRESP(<condition>)`` as an operand.

    The CICS translator substitutes the condition's number; the bridge keeps the
    name instead, because the number is release-dependent.
    """

    condition: str


@dataclass(frozen=True)
class FieldRefNode:
    """Reference to a COBOL data field by name."""

    name: str
    subscripts: tuple[ExprNode, ...] = ()


@dataclass(frozen=True)
class RefModNode:
    """Reference modification: field reference with start position and optional length."""

    name: str
    ref_mod_start: ExprNode
    ref_mod_length: ExprNode | None = None
    subscripts: tuple[ExprNode, ...] = ()


@dataclass(frozen=True)
class BinOpNode:
    """Binary arithmetic operation."""

    op: str  # "+", "-", "*", "/"
    left: ExprNode
    right: ExprNode


@dataclass(frozen=True)
class FunctionNode:
    """Intrinsic FUNCTION call used as an expression operand.

    Appears in COMPUTE expressions and IF relation operands, e.g.
    COMPUTE X = FUNCTION TRIM(WS-A) or
    IF FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B). The bridge serializes
    it as {"kind":"function","name":..,"args":[<expr>, ...]} (red-dragon-ge72).
    """

    name: str
    args: tuple[ExprNode, ...] = ()


ExprNode = (
    LiteralNode
    | FigurativeNode
    | LengthOfNode
    | DfhRespNode
    | FieldRefNode
    | RefModNode
    | BinOpNode
    | FunctionNode
)


def expr_from_dict(d: dict) -> ExprNode:
    """Deserialize a structured JSON expression tree (emitted by the Java bridge) into an ExprNode.

    The JSON uses "kind" as the discriminant with values:
    - {"kind": "lit", "value": "5"} — literal
    - {"kind": "ref", "name": "WS-FIELD"} — plain field reference
    - {"kind": "ref", "name": "WS-FIELD", "ref_mod_start": {...}, "ref_mod_length": {...}} — reference modification
    - {"kind": "binop", "op": "+", "left": {...}, "right": {...}} — binary operation
    - {"kind": "neg", "expr": {...}} — unary negation (folded into binop * -1)
    - {"kind": "function", "name": "TRIM", "args": [{...}]} — intrinsic function
    - {"kind": "figurative", "value": "ZEROS"} — figurative constant operand
    - {"kind": "length_of", "name": "WS-A"} — LENGTH OF special register
    - {"kind": "dfhresp", "condition": "NORMAL"} — CICS response code

    A kind the bridge writes and this side does not know raises, the raise
    escapes ``CobolASG.from_dict``, and the program loses every fact it had --
    not just the one operand. ``figurative``, ``length_of`` and ``dfhresp`` were
    missing, so ``COMPUTE WS-PCT = ZEROES`` cost a whole member.
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
        return FunctionNode(
            name=d.get("name", ""),
            args=tuple(expr_from_dict(a) for a in d.get("args", []) or []),
        )
    if kind == "figurative":
        return FigurativeNode(value=d.get("value", ""))
    if kind == "length_of":
        return LengthOfNode(name=d.get("name", ""))
    if kind == "dfhresp":
        return DfhRespNode(condition=d.get("condition", ""))
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
    if isinstance(node, FigurativeNode):
        return {"kind": "figurative", "value": node.value}
    if isinstance(node, LengthOfNode):
        return {"kind": "length_of", "name": node.name}
    if isinstance(node, DfhRespNode):
        return {"kind": "dfhresp", "condition": node.condition}
    raise ValueError(f"Unknown expression node type: {type(node).__name__}")
