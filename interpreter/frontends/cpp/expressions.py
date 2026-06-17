"""C++-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import re
from interpreter.type_name import TypeName

from typing import Any

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Const,
    LoadVar,
    CallCtorFunction,
    CallFunction,
    CallMethod,
    LoadIndex,
    StoreIndex,
    Throw_,
    Symbolic,
    Label_,
    Branch,
    Return_,
)
from interpreter.frontends.common.expressions import (
    extract_call_args_unwrap,
    lower_identifier,
    lower_canonical_none,
    lower_int_literal,
    lower_float_literal,
    lower_string_literal,
    lower_null_literal,
    lower_default_return,
)
from interpreter.frontends.common.declarations import emit_implicit_return
from interpreter.frontends.c.expressions import lower_c_store_target
from interpreter.frontends.cpp.node_types import CppNodeType
from interpreter.types.type_expr import ScalarType
from interpreter.register import Register

# ── C++ typed literal lowerers ────────────────────────────────────────────────

# C++ integer suffixes (u/l/ll in any case combination)
_CPP_INT_SUFFIX_RE = re.compile(r"[uUlL]+$")

# C++ float suffixes (f/F/l/L)
_CPP_FLOAT_SUFFIX_RE = re.compile(r"[fFlL]$")

# C++ escape sequences for char/string literals
_CPP_CHAR_ESCAPES: dict[str, str] = {
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


def _strip_cpp_int_suffix(text: str) -> str:
    """Strip C++ integer suffixes (u/l/ll) and C++14 apostrophe digit separators."""
    # Remove apostrophe digit separators first
    text = text.replace("'", "")
    # Strip trailing integer suffixes
    return _CPP_INT_SUFFIX_RE.sub("", text)


def _parse_cpp_char(text: str) -> int:
    """Return the ordinal of a C++ char literal (e.g. "'A'" -> 65, "'\\n'" -> 10).

    Handles:
    - Simple chars:   'x'
    - Common escapes: '\\n', '\\t', '\\r', '\\\\', etc.
    - Hex escapes:    '\\xFF'
    - Octal escapes:  '\\077'
    """
    # Strip wide/u8/u/U prefix if present (L'x', u8'x', u'x', U'x')
    if text.startswith(("L'", "u'", "U'")):
        text = text[1:]
    elif text.startswith("u8'"):
        text = text[2:]

    # Strip surrounding single quotes
    inner = text[1:-1]

    if inner in _CPP_CHAR_ESCAPES:
        return ord(_CPP_CHAR_ESCAPES[inner])
    if inner.startswith("\\x"):
        return int(inner[2:], 16)
    if inner.startswith("\\") and len(inner) > 1 and inner[1].isdigit():
        return int(inner[1:], 8)
    if inner.startswith("\\u") and len(inner) == 6:
        return int(inner[2:], 16)
    if inner.startswith("\\U") and len(inner) == 10:
        return int(inner[2:], 16)
    return ord(inner)


def _unescape_cpp_string(s: str) -> str:
    """Resolve C++ string escape sequences in an already-unquoted string."""

    def replace_escape(m: re.Match) -> str:  # type: ignore[type-arg]
        seq = m.group(0)
        if seq in _CPP_CHAR_ESCAPES:
            return _CPP_CHAR_ESCAPES[seq]
        if seq.startswith("\\x"):
            return chr(int(seq[2:], 16))
        if seq.startswith("\\u") and len(seq) == 6:
            return chr(int(seq[2:], 16))
        if seq.startswith("\\U") and len(seq) == 10:
            return chr(int(seq[2:], 16))
        if seq.startswith("\\") and seq[1:].isdigit():
            return chr(int(seq[1:], 8))
        return seq

    return re.sub(
        r'\\x[0-9a-fA-F]+|\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{8}|\\[0-7]{1,3}|\\[ntrb\\f\'"0av?]',
        replace_escape,
        s,
    )


def lower_cpp_number_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C++ number literal to a typed int or float Const.

    Handles:
    - Integer suffixes: u/U/l/L/ll/LL (any combination), stripped before parse.
    - C++14 apostrophe digit separators: 1'000'000 → 1000000.
    - All int bases via int(text, 0): decimal, hex 0x, octal 0, binary 0b.
    - Float suffixes: f/F (float), l/L (long double → float).
    - Float literals detected by '.' or 'e/E/p/P' in the (suffix-stripped) text.
    """
    raw = ctx.node_text(node)
    # Remove C++14 apostrophe digit separators
    no_sep = raw.replace("'", "")

    # Detect float: suffix f/l or contains '.', 'e', 'E', 'p', 'P'
    # But only after stripping the suffix
    float_suffix_stripped = _CPP_FLOAT_SUFFIX_RE.sub("", no_sep)
    is_float = "." in float_suffix_stripped or any(
        c in float_suffix_stripped for c in ("e", "E", "p", "P")
    )

    if is_float:
        return lower_float_literal(ctx, node, text=float_suffix_stripped)

    # Integer: strip suffixes
    int_text = _strip_cpp_int_suffix(no_sep)
    return lower_int_literal(ctx, node, text=int_text)


def lower_cpp_char_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C++ char literal to its integer ordinal value (typed Const.int_).

    Examples: 'A' → 65, '\\n' → 10, L'x' → 120.
    """
    ordinal = _parse_cpp_char(ctx.node_text(node))
    return lower_int_literal(ctx, node, text=str(ordinal))


def lower_cpp_string_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C++ regular string literal (including wide/u8/u/U prefixes) as Const.string.

    Strips surrounding double-quotes and optional prefix (L, u8, u, U),
    then resolves escape sequences.
    """
    raw = ctx.node_text(node)
    # Strip wide/unicode prefix
    if raw.startswith(('L"', 'u"', 'U"')):
        raw = raw[1:]
    elif raw.startswith('u8"'):
        raw = raw[2:]

    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        value = _unescape_cpp_string(inner)
    else:
        value = raw
    return lower_string_literal(ctx, node, value)


def lower_cpp_concatenated_string(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C++ concatenated string literal (adjacent string literals) as Const.string.

    C++ allows adjacent string literals to be concatenated at compile time:
    "hello" " " "world" → "hello world".
    We collect the text from all string-literal children and concatenate.
    """
    parts: list[str] = []
    for child in node.children:
        if child.type in ("string_literal", "raw_string_literal"):
            child_reg = ctx.lower_expr(child)
            # We need the string value; re-parse is simpler here
            raw = ctx.node_text(child)
            # Strip prefix
            if raw.startswith(('L"', 'u"', 'U"')):
                raw = raw[1:]
            elif raw.startswith('u8"'):
                raw = raw[2:]
            # Raw string
            if raw.startswith('R"'):
                value = _strip_raw_string_delimiters(raw)
            elif len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
                value = _unescape_cpp_string(raw[1:-1])
            else:
                value = raw
            parts.append(value)
    return lower_string_literal(ctx, node, "".join(parts))


def _strip_raw_string_delimiters(raw: str) -> str:
    """Extract content from a C++ raw string literal R"delimiter(content)delimiter".

    Handles any delimiter (including empty delimiter R"(content)").
    The content is literal — no escape processing.
    """
    # raw starts with optional prefix chars then R"
    r_idx = raw.find('R"')
    if r_idx == -1:
        return raw
    after_r = raw[r_idx + 2 :]  # everything after R"
    # Find opening paren
    paren_idx = after_r.find("(")
    if paren_idx == -1:
        return raw
    delimiter = after_r[:paren_idx]
    # Content is between ( and )delimiter"
    content_start = paren_idx + 1
    end_marker = f'){delimiter}"'
    end_idx = after_r.rfind(end_marker)
    if end_idx == -1:
        return after_r[content_start:]
    content = after_r[content_start:end_idx]
    return content


def lower_cpp_raw_string_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C++ raw string literal R"delimiter(content)delimiter" as Const.string.

    Raw strings have NO escape processing — the content is taken verbatim.
    """
    raw = ctx.node_text(node)
    value = _strip_raw_string_delimiters(raw)
    return lower_string_literal(ctx, node, value)


def lower_cpp_user_defined_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a C++ user-defined literal (e.g. 42_km, 1.5_s) as a typed Const.

    Strips the UDL suffix (starts at the first '_' or letter after digits),
    then dispatches to the appropriate typed helper based on the base literal.
    This is a best-effort approximation; the UDL operator is not called.
    """
    raw = ctx.node_text(node)
    # UDL suffixes start after the numeric/string portion.
    # Common patterns: 42_km (integer), 1.5_s (float), "hello"_s (string)
    if raw.startswith('"') or raw.startswith(('L"', 'u"', 'U"', 'u8"')):
        # String UDL: lower as string, strip UDL suffix (starts after closing quote)
        closing_q = raw.rfind('"')
        if closing_q > 0:
            string_part = raw[: closing_q + 1]
            # Temporarily wrap in a fake node by passing text= directly
            return lower_string_literal(
                ctx,
                node,
                _unescape_cpp_string(
                    string_part[1:-1] if len(string_part) >= 2 else string_part
                ),
            )
        return lower_string_literal(ctx, node, raw)
    # Numeric UDL: strip UDL suffix (letters/underscores after numeric chars)
    # Find where the numeric part ends
    numeric_end = len(raw)
    for i, ch in enumerate(raw):
        if ch == "_" or (
            ch.isalpha()
            and raw[:i]
            and not raw[i - 1 : i] in ("x", "X", "b", "B", "o", "O", "p", "P", "e", "E")
        ):
            numeric_end = i
            break
    numeric_part = raw[:numeric_end] if numeric_end > 0 else raw
    # Dispatch as number
    no_sep = numeric_part.replace("'", "")
    float_stripped = _CPP_FLOAT_SUFFIX_RE.sub("", no_sep)
    is_float = "." in float_stripped or any(
        c in float_stripped for c in ("e", "E", "p", "P")
    )
    if is_float:
        return lower_float_literal(ctx, node, text=float_stripped)
    int_text = _strip_cpp_int_suffix(no_sep)
    try:
        return lower_int_literal(ctx, node, text=int_text)
    except (ValueError, TypeError):
        return lower_string_literal(ctx, node, raw)


def lower_new_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower new T(args) as CALL_CTOR."""
    type_node = node.child_by_field_name("type")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []
    type_name = ctx.node_text(type_node) if type_node else "Object"
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallCtorFunction(
            result_reg=reg,
            func_name=FuncName(type_name),
            type_hint=scalar(TypeName(type_name)),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    ctx.seed_register_type(reg, ScalarType(TypeName(type_name)))
    return reg


def lower_delete_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower delete ptr as CALL_FUNCTION delete(ptr_reg)."""
    named_children = [c for c in node.children if c.is_named]
    operand_node = named_children[0] if named_children else None
    ptr_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("delete"), args=(ptr_reg,)),
        node=node,
    )
    return reg


def lower_lambda(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower lambda_expression like an arrow function."""
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    params_node = node.child_by_field_name("declarator")

    from interpreter.frontends.c.declarations import lower_c_params

    func_name = "__lambda"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        param_list = next(
            (c for c in params_node.children if c.type == CppNodeType.PARAMETER_LIST),
            params_node,
        )
        lower_c_params(ctx, param_list)

    if body_node:
        if body_node.type == CppNodeType.COMPOUND_STATEMENT:
            ctx.lower_block(body_node)
        else:
            val_reg = ctx.lower_expr(body_node)
            ctx.emit_inst(Return_(value_reg=val_reg))

    emit_implicit_return(ctx, node)
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    return func_reg


def lower_qualified_id(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower qualified_identifier (e.g., std::cout) as LOAD_VAR."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(ctx.node_text(node))), node=node)
    return reg


def _extract_scoped_parts(node) -> tuple[str, str] | None:
    """Extract (namespace, member) from a qualified_identifier/scoped_identifier node.

    Returns None if the node is not a recognizable Class::method pattern.
    """
    ns_node = next(
        (c for c in node.children if c.type == CppNodeType.NAMESPACE_IDENTIFIER),
        None,
    )
    member_node = next(
        (c for c in node.children if c.type == CppNodeType.IDENTIFIER),
        None,
    )
    if ns_node is None or member_node is None:
        return None
    return ns_node.text.decode("utf-8"), member_node.text.decode("utf-8")


def lower_cpp_call(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower call_expression, promoting Class::method(args) to CALL_METHOD.

    For ``Util::square(5)``, tree-sitter produces::

        call_expression
          qualified_identifier
            namespace_identifier  ← "Util"
            identifier            ← "square"
          argument_list

    We emit ``LOAD_VAR Util`` + ``CALL_METHOD %obj method args``, exactly as
    Java/C# do for ``MathUtil.square(5)``.  All other calls fall through to the
    common ``lower_call`` implementation.
    """
    from interpreter.frontends.common.expressions import (
        lower_call_impl,
        extract_call_args,
    )

    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    if func_node and func_node.type in (
        CppNodeType.QUALIFIED_IDENTIFIER,
        CppNodeType.SCOPED_IDENTIFIER,
    ):
        parts = _extract_scoped_parts(func_node)
        if parts is not None:
            class_name, method_name = parts
            obj_reg = ctx.fresh_reg()
            ctx.emit_inst(
                LoadVar(result_reg=obj_reg, name=VarName(class_name)), node=func_node
            )
            arg_regs = extract_call_args(ctx, args_node)
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallMethod(
                    result_reg=result_reg,
                    obj_reg=obj_reg,
                    method_name=FuncName(method_name),
                    args=tuple(arg_regs),
                ),
                node=node,
            )
            return result_reg

    return lower_call_impl(ctx, func_node, args_node, node)


def lower_throw_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower throw as an expression (C++ throw can appear in expressions)."""
    children = [
        c for c in node.children if c.type != CppNodeType.THROW_KEYWORD and c.is_named
    ]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = lower_default_return(ctx, node, ctx.constants.default_return_value)
    ctx.emit_inst(Throw_(value_reg=val_reg), node=node)
    return val_reg


def lower_cpp_cast(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower static_cast<T>(expr) etc. — pass through the value."""
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[-1])
    return lower_null_literal(ctx, node)


def lower_condition_clause(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Unwrap condition_clause to reach the inner expression.

    Skips init_statement children (handled by the enclosing if/while lowerer).
    """
    for child in node.children:
        if (
            child.is_named
            and child.type not in ("(", ")")
            and child.type != CppNodeType.INIT_STATEMENT
        ):
            return ctx.lower_expr(child)
    return lower_null_literal(ctx, node)


def lower_cpp_subscript_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower subscript_expression — C++ wraps index in subscript_argument_list."""
    arr_node = node.child_by_field_name("argument")
    idx_node = node.child_by_field_name("index")
    if arr_node and idx_node:
        # Standard C-style subscript
        from interpreter.frontends.c.expressions import lower_subscript_expr

        return lower_subscript_expr(ctx, node)
    # C++ tree-sitter: first named child = object, subscript_argument_list = index wrapper
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_null_literal(ctx, node)
    obj_reg = ctx.lower_expr(named_children[0])
    suffix = next(
        (c for c in node.children if c.type == CppNodeType.SUBSCRIPT_ARGUMENT_LIST),
        None,
    )
    if suffix:
        idx_children = [c for c in suffix.children if c.is_named]
        idx_reg = ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
    else:
        idx_reg = ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
    )
    return reg


def lower_cpp_assignment_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower assignment_expression with C++ subscript support."""
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_cpp_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_cpp_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Override C store target to handle C++ subscript_expression with subscript_argument_list."""
    if target.type == CppNodeType.SUBSCRIPT_EXPRESSION:
        arr_node = target.child_by_field_name("argument")
        idx_node = target.child_by_field_name("index")
        if arr_node and idx_node:
            lower_c_store_target(ctx, target, val_reg, parent_node)
            return
        named_children = [c for c in target.children if c.is_named]
        if not named_children:
            lower_c_store_target(ctx, target, val_reg, parent_node)
            return
        obj_reg = ctx.lower_expr(named_children[0])
        suffix = next(
            (
                c
                for c in target.children
                if c.type == CppNodeType.SUBSCRIPT_ARGUMENT_LIST
            ),
            None,
        )
        if suffix:
            idx_children = [c for c in suffix.children if c.is_named]
            idx_reg = (
                ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
            )
        else:
            idx_reg = ctx.fresh_reg()
        ctx.emit_inst(
            StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
            node=parent_node,
        )
    else:
        lower_c_store_target(ctx, target, val_reg, parent_node)
