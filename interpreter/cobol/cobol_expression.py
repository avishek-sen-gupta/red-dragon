# pyright: standard
"""COBOL arithmetic expression tree.

Expression trees are emitted in structured JSON by the ProLeap bridge
(``serializeArithmeticExpr`` / ``serializeBasis`` / ``serializeBasisCtx``) and
consumed via :func:`expr_from_dict`. This module defines the :data:`ExprNode`
dataclass hierarchy plus the :func:`expr_from_dict` / :func:`expr_to_dict`
(de)serialization pair.

:data:`_BUILDERS` carries one entry per ``kind`` the bridge can write, and that
is the point of the table: a kind the bridge emits and this side does not know
raises, the raise escapes ``CobolASG.from_dict``, and the program loses every
fact it had -- not just the one operand. ``figurative``, ``length_of`` and
``dfhresp`` were missing, so ``COMPUTE WS-PCT = ZEROES`` cost a whole member.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias

# An expression node as the bridge writes it: string leaves, nested nodes, and
# lists of nodes. ``TypeAlias`` rather than a 3.12 ``type`` statement because
# the lint config still parses this package as 3.11.
JsonExpr: TypeAlias = Mapping[str, "str | JsonExpr | Sequence[JsonExpr]"]

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
    """Reference modification: field reference with start position and length."""

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


# ── Reading the bridge's JSON ─────────────────────────────────────


def _text(d: JsonExpr, key: str) -> str:
    """A string leaf of the node, empty when the bridge omitted it."""
    value = d.get(key, "")
    return value if isinstance(value, str) else ""


def _child(d: JsonExpr, key: str) -> ExprNode:
    """A nested expression, which the bridge always writes as an object.

    The message names the field but never the value: an expression carries data
    names lifted from the source, and this text can reach a log.
    """
    value = d[key]
    if isinstance(value, Mapping):
        return expr_from_dict(value)
    raise ValueError(f"Expression node field {key!r} is not an object")


def _children(d: JsonExpr, key: str) -> tuple[ExprNode, ...]:
    """A list of nested expressions -- subscripts, or function arguments."""
    value = d.get(key) or ()
    return tuple(expr_from_dict(item) for item in value if isinstance(item, Mapping))


def _literal(d: JsonExpr) -> ExprNode:
    return LiteralNode(value=_text(d, "value"))


def _figurative(d: JsonExpr) -> ExprNode:
    return FigurativeNode(value=_text(d, "value"))


def _length_of(d: JsonExpr) -> ExprNode:
    return LengthOfNode(name=_text(d, "name"))


def _dfhresp(d: JsonExpr) -> ExprNode:
    return DfhRespNode(condition=_text(d, "condition"))


def _ref_mod(d: JsonExpr) -> ExprNode:
    return RefModNode(
        name=_text(d, "name"),
        ref_mod_start=_child(d, "ref_mod_start"),
        ref_mod_length=(_child(d, "ref_mod_length") if "ref_mod_length" in d else None),
        subscripts=_children(d, "subscripts"),
    )


def _reference(d: JsonExpr) -> ExprNode:
    """A field reference, sliced or whole -- both arrive as ``kind: "ref"``."""
    if "ref_mod_start" in d:
        return _ref_mod(d)
    return FieldRefNode(name=_text(d, "name"), subscripts=_children(d, "subscripts"))


def _binop(d: JsonExpr) -> ExprNode:
    return BinOpNode(
        op=_text(d, "op"), left=_child(d, "left"), right=_child(d, "right")
    )


def _negation(d: JsonExpr) -> ExprNode:
    """Unary minus, folded into * -1: the tree carries no unary node."""
    return BinOpNode(op="*", left=LiteralNode(value="-1"), right=_child(d, "expr"))


def _function(d: JsonExpr) -> ExprNode:
    return FunctionNode(name=_text(d, "name"), args=_children(d, "args"))


_BUILDERS: Mapping[str, Callable[[JsonExpr], ExprNode]] = {
    "lit": _literal,
    "ref": _reference,
    "binop": _binop,
    "neg": _negation,
    "function": _function,
    "figurative": _figurative,
    "length_of": _length_of,
    "dfhresp": _dfhresp,
}


def expr_from_dict(d: JsonExpr) -> ExprNode:
    """Deserialize a structured JSON expression tree into an ExprNode.

    The JSON uses "kind" as the discriminant, one value per :data:`_BUILDERS`
    entry:
    - {"kind": "lit", "value": "5"} — literal
    - {"kind": "ref", "name": "WS-FIELD"} — plain field reference
    - {"kind": "ref", "name": "WS-FIELD", "ref_mod_start": {...}, "ref_mod_length": {...}} — reference modification
    - {"kind": "binop", "op": "+", "left": {...}, "right": {...}} — binary operation
    - {"kind": "neg", "expr": {...}} — unary negation (folded into binop * -1)
    - {"kind": "function", "name": "TRIM", "args": [{...}]} — intrinsic function
    - {"kind": "figurative", "value": "ZEROS"} — figurative constant operand
    - {"kind": "length_of", "name": "WS-A"} — LENGTH OF special register
    - {"kind": "dfhresp", "condition": "NORMAL"} — CICS response code
    """
    kind = _text(d, "kind")
    if kind not in _BUILDERS:
        raise ValueError(f"Unknown expression node kind: {kind!r}")
    return _BUILDERS[kind](d)


# ── Writing it back ───────────────────────────────────────────────


def _subscripts_dict(subscripts: Sequence[ExprNode]) -> dict:
    """The subscripts key, present only when there are subscripts."""
    return {"subscripts": [expr_to_dict(s) for s in subscripts]} if subscripts else {}


def _ref_mod_length_dict(length: ExprNode | None) -> dict:
    """The length key, absent for a slice that runs to the field's end."""
    if length is None:
        return {}
    return {"ref_mod_length": expr_to_dict(length)}


def _literal_dict(node: LiteralNode) -> dict:
    return {"kind": "lit", "value": node.value}


def _figurative_dict(node: FigurativeNode) -> dict:
    return {"kind": "figurative", "value": node.value}


def _length_of_dict(node: LengthOfNode) -> dict:
    return {"kind": "length_of", "name": node.name}


def _dfhresp_dict(node: DfhRespNode) -> dict:
    return {"kind": "dfhresp", "condition": node.condition}


def _field_ref_dict(node: FieldRefNode) -> dict:
    return {"kind": "ref", "name": node.name, **_subscripts_dict(node.subscripts)}


def _ref_mod_dict(node: RefModNode) -> dict:
    return {
        "kind": "ref",
        "name": node.name,
        "ref_mod_start": expr_to_dict(node.ref_mod_start),
        **_ref_mod_length_dict(node.ref_mod_length),
        **_subscripts_dict(node.subscripts),
    }


def _binop_dict(node: BinOpNode) -> dict:
    return {
        "kind": "binop",
        "op": node.op,
        "left": expr_to_dict(node.left),
        "right": expr_to_dict(node.right),
    }


def _function_dict(node: FunctionNode) -> dict:
    return {
        "kind": "function",
        "name": node.name,
        "args": [expr_to_dict(a) for a in node.args],
    }


_SERIALIZERS: Mapping[type, Callable[..., dict]] = {
    LiteralNode: _literal_dict,
    FigurativeNode: _figurative_dict,
    LengthOfNode: _length_of_dict,
    DfhRespNode: _dfhresp_dict,
    FieldRefNode: _field_ref_dict,
    RefModNode: _ref_mod_dict,
    BinOpNode: _binop_dict,
    FunctionNode: _function_dict,
}


def expr_to_dict(node: ExprNode) -> dict:
    """Serialize an ExprNode back to its structured JSON dict form.

    Inverse of :func:`expr_from_dict`. Used to round-trip subscript interiors
    (red-dragon-l445). ``neg`` is not re-emitted — a folded negation already
    lives as a ``binop`` after deserialization.
    """
    if type(node) not in _SERIALIZERS:
        raise ValueError(f"Unknown expression node type: {type(node).__name__}")
    return _SERIALIZERS[type(node)](node)
