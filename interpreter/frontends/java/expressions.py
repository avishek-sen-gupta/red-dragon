"""Java-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import Any

from interpreter import constants
from interpreter.class_name import ClassName
from interpreter.field_name import FieldKind, FieldName
from interpreter.frontends.common.declarations import emit_implicit_return
from interpreter.frontends.common.expressions import (
    extract_call_args_unwrap,
    lower_default_return,
    lower_float_literal,
    lower_int_literal,
    lower_null_literal,
    lower_string_literal,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.java.node_types import JavaNodeType

# lower_const_literal is intentionally NOT imported — it now raises TypeError.
# All literal sites must use the typed helpers above (gjoy.4 migration).
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    BranchIf,
    CallCtorFunction,
    CallFunction,
    CallMethod,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    NewArray,
    Return_,
    StoreField,
    StoreIndex,
    StoreVar,
    Symbolic,
    Throw_,
)
from interpreter.register import Register
from interpreter.type_name import TypeName
from interpreter.types.type_expr import ScalarType, scalar
from interpreter.var_name import VarName


def _parse_java_integer(text: str) -> int:
    """Parse a Java integer literal (hex/octal/binary/decimal) to a Python int.

    Strips trailing L/l long suffixes and underscore digit separators before
    parsing.  hex/octal/binary/decimal are all handled.
    """
    # Strip trailing type suffixes (L, l) and digit separators
    clean = text.rstrip("Ll").replace("_", "")
    if clean.startswith(("0x", "0X")):
        return int(clean, 16)
    if clean.startswith(("0b", "0B")):
        return int(clean, 2)
    # Octal: starts with 0 and has more digits (but not just "0")
    if len(clean) > 1 and clean.startswith("0") and clean.isdigit():
        return int(clean, 8)
    return int(clean, 10)


_JAVA_CHAR_ESCAPES: dict[str, str] = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\\\": "\\",
    "\\'": "'",
    '\\"': '"',
    "\\b": "\b",
    "\\f": "\f",
    "\\0": "\0",
}


def _parse_java_char(text: str) -> int:
    """Return the ordinal of a Java character literal (e.g. "'c'" -> 99, "'\\n'" -> 10)."""
    # text is the raw node text, e.g. "'c'" or "'\\n'" or "'\\u0041'"
    inner = text[1:-1]  # strip surrounding single quotes
    if inner in _JAVA_CHAR_ESCAPES:
        return ord(_JAVA_CHAR_ESCAPES[inner])
    if inner.startswith("\\u") and len(inner) == 6:
        return int(inner[2:], 16)
    return ord(inner)


def lower_java_char_literal(ctx: TreeSitterEmitContext, node: Any) -> Register:
    """Lower a Java character literal to its integer ordinal value (typed Const.int_)."""
    ordinal = _parse_java_char(ctx.node_text(node))
    return lower_int_literal(ctx, node, text=str(ordinal))


def _parse_java_hex_float(text: str) -> float:
    """Parse a Java hex floating-point literal to a Python float."""
    clean = text.rstrip("fFdD")
    return float.fromhex(clean)


def lower_java_hex_float_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Java hex floating-point literal (e.g. 0x1.0p10 → 1024.0) as typed Const.float_."""
    return lower_float_literal(
        ctx, node, text=str(_parse_java_hex_float(ctx.node_text(node)))
    )


def lower_java_integer_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Java integer literal, converting hex/octal/binary to a typed Const.int_."""
    return lower_int_literal(
        ctx, node, text=str(_parse_java_integer(ctx.node_text(node)))
    )


_JAVA_STRING_ESCAPES: dict[str, str] = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\\\": "\\",
    "\\'": "'",
    '\\"': '"',
    "\\b": "\b",
    "\\f": "\f",
    "\\0": "\0",
}


def _unescape_java_string(s: str) -> str:
    """Resolve Java string escape sequences in an already-unquoted string."""
    import re

    def replace_escape(m: re.Match) -> str:  # type: ignore[type-arg]
        seq = m.group(0)
        if seq in _JAVA_STRING_ESCAPES:
            return _JAVA_STRING_ESCAPES[seq]
        if seq.startswith("\\u") and len(seq) == 6:
            return chr(int(seq[2:], 16))
        # octal: \NNN
        if seq.startswith("\\") and seq[1:].isdigit():
            return chr(int(seq[1:], 8))
        return seq

    return re.sub(r'\\u[0-9a-fA-F]{4}|\\[0-7]{1,3}|\\[ntrb\\f\'"0]', replace_escape, s)


def lower_java_float_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower Java decimal floating-point literal (e.g. 3.14, 3.14f, 1.5d) as typed Const.float_.

    Strips trailing f/F (float) and d/D (double) suffixes; both map to Python float.
    """
    raw = ctx.node_text(node).rstrip("fFdD").replace("_", "")
    return lower_float_literal(ctx, node, text=raw)


def lower_java_string_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a Java string literal (regular or text block) as typed Const.string.

    Strips surrounding double-quotes (or triple-quotes for text blocks) and
    resolves escape sequences.
    """
    raw = ctx.node_text(node)
    # Text block: triple-quoted string (Java 15+)
    if raw.startswith('"""'):
        inner = raw[3:]
        if inner.endswith('"""'):
            inner = inner[:-3]
        value = _unescape_java_string(inner)
    elif len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        value = _unescape_java_string(raw[1:-1])
    else:
        value = raw
    return lower_string_literal(ctx, node, value)


def lower_method_invocation(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    name_node = node.child_by_field_name("name")
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    if obj_node:
        obj_reg = ctx.lower_expr(obj_node)
        method_name = ctx.node_text(name_node) if name_node else "unknown"
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallMethod(
                result_reg=reg,
                obj_reg=obj_reg,
                method_name=FuncName(method_name),
                args=tuple(arg_regs),
            ),
            node=node,
        )
        return reg

    func_name = ctx.node_text(name_node) if name_node else "unknown"
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg, func_name=FuncName(func_name), args=tuple(arg_regs)
        ),
        node=node,
    )
    return reg


def lower_object_creation(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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


def lower_field_access(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    # Try namespace resolution first
    from interpreter.namespace_resolver import NO_RESOLUTION

    result = ctx.namespace_resolver.try_resolve_field_access(ctx, node)
    if result is not NO_RESOLUTION:
        return result

    # Existing behavior: recursive lowering
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    field_node = node.child_by_field_name("field")
    if obj_node is None or field_node is None:
        return lower_null_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg


def lower_method_reference(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower method_reference: Type::method or obj::method or Type::new."""
    obj_node = node.children[0]
    method_node = node.children[-1]
    obj_reg = ctx.lower_expr(obj_node)
    method_name = ctx.node_text(method_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(method_name)),
        node=node,
    )
    return reg


def lower_scoped_identifier(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower scoped_identifier (e.g., java.lang.System) as LOAD_VAR."""
    qualified_name = ctx.node_text(node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=VarName(qualified_name)), node=node)
    return reg


def lower_class_literal(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower class_literal: Type.class -> LOAD_FIELD(type_reg, 'class')."""
    type_node = node.children[0]
    type_reg = ctx.lower_expr(type_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=type_reg, field_name=FieldName("class")),
        node=node,
    )
    return reg


def lower_lambda(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower lambda_expression: (params) -> expr or (params) -> { body }."""
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}__lambda")
    end_label = ctx.fresh_label("lambda_end")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        _lower_lambda_params(ctx, params_node)

    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    if body_node and body_node.type == JavaNodeType.BLOCK:
        ctx.lower_block(body_node)
        emit_implicit_return(ctx, node)
    elif body_node:
        body_reg = ctx.lower_expr(body_node)
        ctx.emit_inst(Return_(value_reg=body_reg))

    ctx.emit_inst(Label_(label=end_label))

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref("__lambda", func_label, result_reg=ref_reg, node=node)
    return ref_reg


def _lower_lambda_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower parameters for lambda expressions."""
    if params_node.type == JavaNodeType.FORMAL_PARAMETERS:
        lower_java_params(ctx, params_node)
    else:
        for child in params_node.children:
            if child.type == JavaNodeType.IDENTIFIER:
                pname = ctx.node_text(child)
                ctx.emit_inst(
                    Symbolic(
                        result_reg=ctx.fresh_reg(),
                        hint=f"{constants.PARAM_PREFIX}{pname}",
                    ),
                    node=child,
                )
                ctx.emit_inst(
                    DeclVar(
                        name=VarName(pname),
                        value_reg=Register(f"%{ctx.reg_counter - 1}"),
                    )
                )


def lower_array_access(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    arr_node = node.child_by_field_name("array")
    idx_node = node.child_by_field_name("index")
    if arr_node is None or idx_node is None:
        return lower_null_literal(ctx, node)
    arr_reg = ctx.lower_expr(arr_node)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=arr_reg, index_reg=idx_reg), node=node
    )
    return reg


def _emit_array_length(
    ctx: TreeSitterEmitContext, arr_reg: Register, size_reg: Register
) -> None:
    """Emit store_field arr.length = size so .length resolves concretely."""
    ctx.emit_inst(
        StoreField(
            obj_reg=arr_reg,
            field_name=FieldName("length", FieldKind.SPECIAL),
            value_reg=size_reg,
        )
    )


def lower_array_creation(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower array_creation_expression or standalone array_initializer."""
    # Handle standalone array_initializer: {1, 2, 3}
    if node.type == JavaNodeType.ARRAY_INITIALIZER:
        elements = [c for c in node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const.int_(size_reg, len(elements)))
        arr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewArray(
                result_reg=arr_reg,
                type_hint=scalar(TypeName("array")),
                size_reg=size_reg,
            ),
            node=node,
        )
        _emit_array_length(ctx, arr_reg, size_reg)
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const.int_(idx_reg, i))
            val_reg = ctx.lower_expr(elem)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg)
            )
        return arr_reg

    # array_creation_expression: look for array_initializer child
    init_node = next(
        (c for c in node.children if c.type == JavaNodeType.ARRAY_INITIALIZER),
        None,
    )
    if init_node is not None:
        elements = [c for c in init_node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const.int_(size_reg, len(elements)))
        arr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewArray(
                result_reg=arr_reg,
                type_hint=scalar(TypeName("array")),
                size_reg=size_reg,
            ),
            node=node,
        )
        _emit_array_length(ctx, arr_reg, size_reg)
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const.int_(idx_reg, i))
            val_reg = ctx.lower_expr(elem)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg)
            )
        return arr_reg

    # Sized array without initializer: new int[5]
    dims_node = next(
        (c for c in node.children if c.type == JavaNodeType.DIMENSIONS_EXPR),
        None,
    )
    if dims_node:
        dim_children = [c for c in dims_node.children if c.is_named]
        size_reg = ctx.lower_expr(dim_children[0]) if dim_children else ctx.fresh_reg()
    else:
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const.int_(size_reg, 0))
    arr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(
            result_reg=arr_reg, type_hint=scalar(TypeName("array")), size_reg=size_reg
        ),
        node=node,
    )
    _emit_array_length(ctx, arr_reg, size_reg)
    return arr_reg


def lower_assignment_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_java_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_java_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == JavaNodeType.IDENTIFIER:
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
    elif target.type == JavaNodeType.FIELD_ACCESS:
        obj_node = target.child_by_field_name(ctx.constants.attr_object_field)
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
    elif target.type == JavaNodeType.ARRAY_ACCESS:
        arr_node = target.child_by_field_name("array")
        idx_node = target.child_by_field_name("index")
        if arr_node and idx_node:
            arr_reg = ctx.lower_expr(arr_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
    else:
        ctx.emit_inst(
            StoreVar(name=VarName(ctx.node_text(target)), value_reg=val_reg),
            node=parent_node,
        )


def lower_cast_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_instanceof(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower instanceof_expression: operand instanceof Type [binding].

    Java 16+ type patterns: ``o instanceof String s`` binds ``s`` to
    the matched value after the type check.
    Java 16+ record patterns: ``o instanceof Point(int a, int b)``
    destructures via the Pattern ADT.
    """
    named_children = [c for c in node.children if c.is_named]
    operand_node = named_children[0] if named_children else None
    pattern_or_type_node = named_children[1] if len(named_children) > 1 else None

    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()

    # Record pattern: o instanceof Point(int a, int b)
    if pattern_or_type_node and pattern_or_type_node.type == "record_pattern":
        from interpreter.frontends.common.patterns import (
            compile_pattern_bindings,
            compile_pattern_test,
        )
        from interpreter.frontends.java.patterns import parse_java_pattern

        pattern = parse_java_pattern(ctx, pattern_or_type_node)
        test_reg = compile_pattern_test(ctx, obj_reg, pattern)
        compile_pattern_bindings(ctx, obj_reg, pattern)
        return test_reg

    # Simple type pattern: o instanceof String s
    type_node = pattern_or_type_node
    binding_node = named_children[2] if len(named_children) > 2 else None

    type_name = ctx.node_text(type_node) if type_node else "Object"
    type_reg = lower_string_literal(ctx, type_node or node, type_name)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name=FuncName("isinstance"),
            args=(
                obj_reg,
                type_reg,
            ),
        ),
        node=node,
    )
    # Java 16+ type pattern binding: o instanceof String s → bind s = o
    if binding_node:
        binding_name = ctx.node_text(binding_node)
        if binding_name != "_":
            ctx.emit_inst(
                StoreVar(name=VarName(binding_name), value_reg=obj_reg), node=node
            )
    return reg


def lower_ternary(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
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


def lower_expr_stmt_as_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower expression_statement in expr context (e.g., inside switch expression)."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_throw_as_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower throw_statement in expr context (e.g., switch expression arm)."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        val_reg = ctx.lower_expr(named_children[0])
    else:
        val_reg = lower_default_return(ctx, node, ctx.constants.default_return_value)
    ctx.emit_inst(Throw_(value_reg=val_reg), node=node)
    return val_reg


# ── shared Java param helper (used by expressions + declarations) ─────


def lower_java_params(ctx: TreeSitterEmitContext, params_node) -> None:
    param_index = 0
    for child in params_node.children:
        if child.type == JavaNodeType.FORMAL_PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                type_hint = extract_normalized_type(ctx, child, "type", ctx.type_map)
                param_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Symbolic(
                        result_reg=param_reg, hint=f"{constants.PARAM_PREFIX}{pname}"
                    ),
                    node=child,
                )
                ctx.seed_register_type(param_reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit_inst(
                    DeclVar(
                        name=VarName(pname),
                        value_reg=Register(f"%{ctx.reg_counter - 1}"),
                    )
                )
                ctx.seed_var_type(pname, type_hint)
                param_index += 1
        elif child.type == JavaNodeType.SPREAD_PARAMETER:
            var_decl = next(
                (c for c in child.children if c.type == "variable_declarator"), None
            )
            name_node = var_decl.child_by_field_name("name") if var_decl else None
            if name_node:
                pname = ctx.node_text(name_node)
                args_reg = ctx.fresh_reg()
                ctx.emit_inst(LoadVar(result_reg=args_reg, name=VarName("arguments")))
                idx_reg = ctx.fresh_reg()
                ctx.emit_inst(Const.int_(idx_reg, param_index))
                rest_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    CallFunction(
                        result_reg=rest_reg,
                        func_name=FuncName("slice"),
                        args=(args_reg, idx_reg),
                    ),
                    node=child,
                )
                ctx.emit_inst(DeclVar(name=VarName(pname), value_reg=rest_reg))
