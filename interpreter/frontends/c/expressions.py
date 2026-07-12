"""C-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
import re
from typing import Any

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.frontends.c.node_types import CNodeType
from interpreter.frontends.common.expressions import (
    lower_float_literal,
    lower_int_literal,
    lower_null_literal,
    lower_string_literal,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.func_name import FuncName
from interpreter.instructions import (
    AddressOf,
    Branch,
    BranchIf,
    CallFunction,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadIndirect,
    LoadVar,
    NewArray,
    NewObject,
    StoreField,
    StoreIndex,
    StoreIndirect,
    StoreVar,
    Unop,
)
from interpreter.operator_kind import resolve_unop
from interpreter.register import Register
from interpreter.type_name import TypeName
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)

# ── C typed literal lowerers ──────────────────────────────────────────────────

# C integer suffixes: u/U, l/L, ll/LL (any combination)
_C_INT_SUFFIX_RE = re.compile(r"[uUlL]+$")

# C float suffixes: f/F (float), l/L (long double)
_C_FLOAT_SUFFIX_RE = re.compile(r"[fFlL]$")

# C char escape sequences (same as C++)
_C_CHAR_ESCAPES: dict[str, str] = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\\\": "\\",
    "\\'": "'",
    '\\"': '"',
    "\\b": "\b",
    "\\f": "\f",
    "\\0": "\0",
    "\\a": "\a",
    "\\v": "\v",
    "\\?": "?",
}


def _parse_c_char(text: str) -> int:
    """Return the ordinal of a C char literal (e.g. \"'A'\" -> 65, \"'\\\\n'\" -> 10).

    Handles:
    - Simple chars:   'x'
    - Common escapes: '\\\\n', '\\\\t', '\\\\r', '\\\\\\\\', etc.
    - Hex escapes:    '\\\\xFF'
    - Octal escapes:  '\\\\077'
    """
    # Strip surrounding single quotes
    inner = text[1:-1]
    if inner in _C_CHAR_ESCAPES:
        return ord(_C_CHAR_ESCAPES[inner])
    if inner.startswith("\\x"):
        return int(inner[2:], 16)
    if inner.startswith("\\") and len(inner) > 1 and inner[1].isdigit():
        return int(inner[1:], 8)
    return ord(inner)


def _unescape_c_string(s: str) -> str:
    """Resolve C string escape sequences in an already-unquoted string."""

    def replace_escape(m: re.Match) -> str:  # type: ignore[type-arg]
        seq = m.group(0)
        if seq in _C_CHAR_ESCAPES:
            return _C_CHAR_ESCAPES[seq]
        if seq.startswith("\\x"):
            return chr(int(seq[2:], 16))
        if seq.startswith("\\") and seq[1:].isdigit():
            return chr(int(seq[1:], 8))
        return seq

    return re.sub(
        r"\\x[0-9a-fA-F]+|\\[0-7]{1,3}|\\[ntrb\\f'\"0av?]",
        replace_escape,
        s,
    )


def lower_c_number_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> str:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C number literal to a typed int or float Const.

    Handles:
    - Integer suffixes: u/U/l/L/ll/LL (any combination), stripped before parse.
    - All int bases via int(text, 0): decimal, hex 0x, octal 0, binary 0b.
    - Float suffixes: f/F, l/L → stripped, then parsed as float.
    - Float literals detected by '.' or 'e/E/p/P' in the suffix-stripped text.
    """
    raw = ctx.node_text(node)

    # Detect float: first strip float suffix to check for '.', 'e', 'E', 'p', 'P'
    float_suffix_stripped = _C_FLOAT_SUFFIX_RE.sub("", raw)
    is_float = "." in float_suffix_stripped or any(
        c in float_suffix_stripped for c in ("e", "E", "p", "P")
    )

    if is_float:
        return lower_float_literal(ctx, node, text=float_suffix_stripped)

    # Integer: strip suffixes
    int_text = _C_INT_SUFFIX_RE.sub("", raw)
    return lower_int_literal(ctx, node, text=int_text)


def lower_c_char_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> str:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C char literal to its integer ordinal value (typed Const.int_).

    Examples: 'A' → 65, '\\\\n' → 10, '\\\\0' → 0.
    """
    ordinal = _parse_c_char(ctx.node_text(node))
    return lower_int_literal(ctx, node, text=str(ordinal))


def lower_c_string_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> str:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C string literal as Const.string.

    Strips surrounding double-quotes and resolves escape sequences.
    For concatenated strings, returns the full text as-is.
    """
    raw = ctx.node_text(node)
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        value = _unescape_c_string(inner)
    else:
        value = raw
    return lower_string_literal(ctx, node, value)


def lower_c_concatenated_string(
    ctx: TreeSitterEmitContext, node: Any
) -> str:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C concatenated string literal (e.g. \"hello\" \" world\") as Const.string."""
    raw = ctx.node_text(node)
    # Concatenated strings: just strip outer quotes from combined text if possible
    # tree-sitter gives us the full source text; join all string_literal children
    parts: list[str] = []
    for child in node.children:
        if child.is_named:
            child_raw = ctx.node_text(child)
            if len(child_raw) >= 2 and child_raw[0] == '"' and child_raw[-1] == '"':
                parts.append(_unescape_c_string(child_raw[1:-1]))
            else:
                parts.append(child_raw)
    if parts:
        return lower_string_literal(ctx, node, "".join(parts))
    return lower_string_literal(ctx, node, raw)


def lower_c_preproc_arg(
    ctx: TreeSitterEmitContext, node: Any
) -> str:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a preproc_arg (macro body) as a symbolic placeholder.

    preproc_arg nodes contain raw macro body text (e.g. ``((a) > (b) ? (a) : (b))``).
    Tree-sitter doesn't parse them as expression trees, so we emit a symbolic
    to avoid crashing when the body isn't a plain numeric literal.
    """
    from interpreter.instructions import Symbolic

    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(result_reg=reg, hint=f"preproc_arg:{ctx.node_text(node)}"), node=node
    )
    return reg


# ── fallback for unrecognized literal nodes ───────────────────────────────────


def _lower_c_fallback_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> str:  # Any: tree-sitter node — untyped at Python boundary
    """Emit a symbolic placeholder for an unrecognized C literal node.

    Used as the fallback in field_expr, subscript_expr, cast_expr, and
    initializer_pair when the normal child traversal finds nothing.
    """
    from interpreter.instructions import Symbolic

    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(result_reg=reg, hint=f"c_literal_fallback:{node.type}"), node=node
    )
    return reg


def lower_field_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower field_expression (e.g., obj.field or ptr->field)."""
    obj_node = node.child_by_field_name("argument")
    field_node = node.child_by_field_name("field")
    if obj_node is None or field_node is None:
        return _lower_c_fallback_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg


def lower_subscript_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower subscript_expression (arr[idx])."""
    arr_node = node.child_by_field_name("argument")
    idx_node = node.child_by_field_name("index")
    if arr_node is None or idx_node is None:
        return _lower_c_fallback_literal(ctx, node)
    arr_reg = ctx.lower_expr(arr_node)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=arr_reg, index_reg=idx_reg), node=node
    )
    return reg


def lower_assignment_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower assignment_expression (x = val)."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_c_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_c_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """C-specific store target handling (field_expression, subscript, pointer)."""
    if target.type == CNodeType.IDENTIFIER:
        name = ctx.node_text(target)
        if ctx.symbol_table.resolve_field(
            ClassName(ctx._current_class_name), FieldName(name)
        ).name.is_present():
            this_reg = ctx.fresh_reg()
            ctx.emit_inst(LoadVar(result_reg=this_reg, name=VarName("this")))
            ctx.emit_inst(
                StoreField(
                    obj_reg=this_reg, field_name=FieldName(name), value_reg=val_reg
                ),
                node=parent_node,
            )
        else:
            ctx.emit_inst(
                StoreVar(name=VarName(name), value_reg=val_reg), node=parent_node
            )
    elif target.type == CNodeType.FIELD_EXPRESSION:
        obj_node = target.child_by_field_name("argument")
        field_node = target.child_by_field_name("field")
        if obj_node and field_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=FieldName(ctx.node_text(field_node)),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == CNodeType.SUBSCRIPT_EXPRESSION:
        arr_node = target.child_by_field_name("argument")
        idx_node = target.child_by_field_name("index")
        if arr_node and idx_node:
            arr_reg = ctx.lower_expr(arr_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
    elif target.type == CNodeType.POINTER_EXPRESSION:
        # *ptr = val -> lower_expr(ptr_operand) -> STORE_INDIRECT ptr_reg, val_reg
        operand_node = target.child_by_field_name("argument")
        if operand_node is None:
            operand_node = next((c for c in target.children if c.is_named), None)
        ptr_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
        ctx.emit_inst(
            StoreIndirect(ptr_reg=ptr_reg, value_reg=val_reg), node=parent_node
        )
    else:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )


def lower_cast_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower cast_expression — pass through the value."""
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    return _lower_c_fallback_literal(ctx, node)


def lower_pointer_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower pointer dereference (*p) as LOAD_INDIRECT or address-of (&x) as ADDRESS_OF."""
    operand_node = node.child_by_field_name("argument")
    # Detect operator: first non-named child is '*' or '&'
    op_char = next(
        (
            ctx.node_text(c)
            for c in node.children
            if not c.is_named and ctx.node_text(c) in ("*", "&")
        ),
        "*",
    )
    if operand_node is None:
        operand_node = next((c for c in node.children if c.is_named), None)

    if op_char == "&":
        # For simple identifiers, emit ADDRESS_OF for alias tracking.
        # For complex expressions (field access, array index), fall back to UNOP.
        if operand_node and operand_node.type == CNodeType.IDENTIFIER:
            var_name = ctx.node_text(operand_node)
            reg = ctx.fresh_reg()
            ctx.emit_inst(
                AddressOf(result_reg=reg, var_name=VarName(var_name)), node=node
            )
            return reg
        inner_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            Unop(result_reg=reg, operator=resolve_unop("&"), operand=inner_reg),
            node=node,
        )
        return reg

    # Dereference *this → just load this (our VM references aren't real pointers)
    if operand_node is not None and ctx.node_text(operand_node) == "this":
        return ctx.lower_expr(operand_node)

    # Dereference: *ptr -> LOAD_INDIRECT ptr
    inner_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndirect(result_reg=reg, ptr_reg=inner_reg), node=node)
    return reg


def lower_sizeof(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower sizeof(type) or sizeof(expr) as CALL_FUNCTION sizeof(arg)."""
    type_node = next(
        (c for c in node.children if c.type == CNodeType.TYPE_DESCRIPTOR),
        None,
    )
    if type_node:
        arg_reg = lower_string_literal(ctx, type_node, ctx.node_text(type_node))
    else:
        expr_node = next(
            (c for c in node.children if c.is_named and c.type != CNodeType.SIZEOF),
            None,
        )
        arg_reg = ctx.lower_expr(expr_node) if expr_node else ctx.fresh_reg()

    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("sizeof"), args=(arg_reg,)),
        node=node,
    )
    return reg


def lower_ternary(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower conditional_expression (ternary operator)."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    true_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    false_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)))
    ctx.emit_inst(Label_(label=true_label))
    true_reg = ctx.lower_expr(true_node)
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    false_reg = ctx.lower_expr(false_node)
    ctx.emit_inst(DeclVar(name=VarName(result_var), value_reg=false_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=VarName(result_var)))
    return result_reg


def lower_comma_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower comma expression (a, b) — evaluate both, return last."""
    children = [c for c in node.children if c.is_named]
    reg = lower_null_literal(ctx, node)
    for child in children:
        reg = ctx.lower_expr(child)
    return reg


def lower_compound_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower (type){elem1, elem2, ...} as NEW_OBJECT + STORE_INDEX per element."""
    type_node = next(
        (c for c in node.children if c.type == CNodeType.TYPE_DESCRIPTOR),
        None,
    )
    init_node = next(
        (c for c in node.children if c.type == CNodeType.INITIALIZER_LIST),
        None,
    )
    type_name = ctx.node_text(type_node) if type_node else "compound"
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=scalar(TypeName(type_name))), node=node
    )
    if init_node:
        elements = [c for c in init_node.children if c.is_named]
        for i, elem in enumerate(elements):
            idx_reg = lower_int_literal(ctx, elem, text=str(i))
            val_reg = ctx.lower_expr(elem)
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg)
            )
    return obj_reg


def lower_initializer_list(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower initializer_list {a, b, c} as NEW_ARRAY + STORE_INDEX per element."""
    elements = [c for c in node.children if c.is_named]
    size_reg = lower_int_literal(ctx, node, text=str(len(elements)))
    arr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(
            result_reg=arr_reg, type_hint=scalar(TypeName("array")), size_reg=size_reg
        ),
        node=node,
    )
    for i, elem in enumerate(elements):
        idx_reg = lower_int_literal(ctx, elem, text=str(i))
        val_reg = ctx.lower_expr(elem)
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


def lower_initializer_pair(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `.field = value` — lower the value (field binding handled by parent)."""
    value_node = next(
        (
            c
            for c in node.children
            if c.is_named and c.type != CNodeType.FIELD_DESIGNATOR
        ),
        None,
    )
    if value_node:
        return ctx.lower_expr(value_node)
    return _lower_c_fallback_literal(ctx, node)
