"""Ruby-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    CallMethod,
    CallUnknown,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    NewArray,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    StoreVar,
    Symbolic,
    Throw_,
)
from interpreter import constants
from interpreter.frontends.common.expressions import (
    extract_call_args,
    lower_const_literal,
    lower_interpolated_string_parts,
)
from interpreter.frontends.ruby.node_types import RubyNodeType
from interpreter.register import Register
from interpreter.types.type_expr import scalar


def lower_scope_resolution(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``Foo::Bar`` as LOAD_VAR(Foo) + LOAD_FIELD(scope_reg, 'Bar').

    For root scope ``::TopLevel`` (no scope child), emits LOAD_VAR('TopLevel').
    """
    scope_node = node.child_by_field_name("scope")
    name_node = node.child_by_field_name("name")
    name_text = ctx.node_text(name_node)

    if scope_node is None:
        # ::TopLevel — root scope resolution
        reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=reg, name=name_text), node=node)
        return reg

    scope_reg = ctx.lower_expr(scope_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=scope_reg, field_name=name_text), node=node
    )
    return reg


def lower_instance_variable(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``@var`` as ``LOAD_VAR self`` + ``LOAD_FIELD self_reg 'var'``."""
    raw = ctx.node_text(node)
    field_name = raw.lstrip("@")
    self_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=self_reg, name=constants.PARAM_SELF), node=node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=self_reg, field_name=field_name), node=node
    )
    return reg


def lower_ruby_string(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower Ruby string, decomposing interpolation into CONST + LOAD_VAR + BINOP '+'."""
    has_interpolation = any(c.type == RubyNodeType.INTERPOLATION for c in node.children)
    if not has_interpolation:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    for child in node.children:
        if child.type == RubyNodeType.STRING_CONTENT:
            frag_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Const(result_reg=frag_reg, value=ctx.node_text(child)), node=child
            )
            parts.append(frag_reg)
        elif child.type == RubyNodeType.INTERPOLATION:
            named = [c for c in child.children if c.is_named]
            if named:
                parts.append(ctx.lower_expr(named[0]))
        # skip punctuation: ", #{, }
    return lower_interpolated_string_parts(ctx, parts, node)


def lower_ruby_heredoc_body(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower Ruby heredoc body, decomposing interpolation like lower_ruby_string."""
    has_interpolation = any(c.type == RubyNodeType.INTERPOLATION for c in node.children)
    if not has_interpolation:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    for child in node.children:
        if child.type == RubyNodeType.HEREDOC_CONTENT:
            frag_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Const(result_reg=frag_reg, value=ctx.node_text(child)), node=child
            )
            parts.append(frag_reg)
        elif child.type == RubyNodeType.INTERPOLATION:
            named = [c for c in child.children if c.is_named]
            if named:
                parts.append(ctx.lower_expr(named[0]))
        # skip heredoc_end and punctuation
    return lower_interpolated_string_parts(ctx, parts, node)


def lower_ruby_call(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower Ruby method call with receiver, block, and raise handling."""
    receiver_node = node.child_by_field_name("receiver")
    method_node = node.child_by_field_name("method")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args(ctx, args_node) if args_node else []

    # Detect block/do_block child and lower it as a closure argument
    block_node = next(
        (
            c
            for c in node.children
            if c.type in (RubyNodeType.BLOCK, RubyNodeType.DO_BLOCK)
        ),
        None,
    )
    if block_node:
        block_reg = lower_ruby_block(ctx, block_node)
        arg_regs = arg_regs + [block_reg]

    # Class.new(...) -> NEW_OBJECT + CALL_METHOD __init__
    if receiver_node and method_node:
        method_name = ctx.node_text(method_node)
        receiver_text = ctx.node_text(receiver_node)
        if method_name == "new" and receiver_text[0:1].isupper():
            obj_reg = ctx.fresh_reg()
            ctx.emit_inst(
                NewObject(result_reg=obj_reg, type_hint=scalar(receiver_text)),
                node=node,
            )
            ctor_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallMethod(
                    result_reg=ctor_reg,
                    obj_reg=obj_reg,
                    method_name="__init__",
                    args=tuple(arg_regs),
                ),
                node=node,
            )
            return obj_reg

        # Method call on receiver: obj.method(...)
        obj_reg = ctx.lower_expr(receiver_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallMethod(
                result_reg=reg,
                obj_reg=obj_reg,
                method_name=method_name,
                args=tuple(arg_regs),
            ),
            node=node,
        )
        return reg

    # Standalone function call: method(args)
    if method_node:
        func_name = ctx.node_text(method_node)
        # Ruby raise -> THROW
        if func_name == "raise":
            val_reg = arg_regs[0] if arg_regs else ctx.fresh_reg()
            ctx.emit_inst(Throw_(value_reg=val_reg), node=node)
            return val_reg
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(result_reg=reg, func_name=func_name, args=tuple(arg_regs)),
            node=node,
        )
        return reg

    # Fallback: unknown call
    target_reg = ctx.fresh_reg()
    ctx.emit_inst(Symbolic(result_reg=target_reg, hint="unknown_call_target"))
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),
        node=node,
    )
    return reg


def lower_ruby_argument_list(ctx: TreeSitterEmitContext, node) -> Register:
    """Unwrap argument_list to its first named child (e.g. return value)."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.default_return_value))
    return reg


def lower_ruby_hash(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower Ruby hash literal as NEW_OBJECT + STORE_INDEX per pair."""
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint=scalar("hash")), node=node)
    for child in node.children:
        if child.type == RubyNodeType.PAIR:
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            if key_node and val_node:
                key_reg = ctx.lower_expr(key_node)
                val_reg = ctx.lower_expr(val_node)
                ctx.emit_inst(
                    StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
                )
    return obj_reg


def lower_ruby_range(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `a..b` or `a...b` as CALL_FUNCTION("range", start, end)."""
    named = [c for c in node.children if c.is_named]
    start_reg = ctx.lower_expr(named[0]) if len(named) > 0 else ctx.fresh_reg()
    end_reg = ctx.lower_expr(named[1]) if len(named) > 1 else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="range",
            args=(
                start_reg,
                end_reg,
            ),
        ),
        node=node,
    )
    return reg


def lower_ruby_lambda(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `-> (params) { body }` as anonymous function."""
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        lower_ruby_params(ctx, params_node)

    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    if body_node:
        # Inline the block body directly -- avoid dispatching a `block`
        # node to lower_ruby_block which would create a nested
        # sub-function instead of inlining the lambda body.
        inner = next(
            (
                c
                for c in body_node.children
                if c.type in (RubyNodeType.BLOCK_BODY, RubyNodeType.BODY_STATEMENT)
            ),
            None,
        )
        target = inner if inner else body_node
        for child in target.children:
            if (
                child.is_named
                and child.type not in ctx.constants.noise_types
                and child.type not in ctx.constants.comment_types
            ):
                ctx.lower_stmt(child)
    else:
        # Inline body: lower named children except params and delimiters
        for child in node.children:
            if (
                child.is_named
                and child.type
                not in (
                    RubyNodeType.LAMBDA_PARAMETERS,
                    RubyNodeType.BLOCK_PARAMETERS,
                    RubyNodeType.ARROW,
                )
                and child.type not in ctx.constants.noise_types
                and child.type not in ctx.constants.comment_types
            ):
                ctx.lower_stmt(child)

    nil_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=nil_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=nil_reg))
    ctx.emit_inst(Label_(label=end_label))

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=ref_reg)
    return ref_reg


def lower_ruby_word_array(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `%w[a b c]` or `%i[a b c]` as NEW_ARRAY + STORE_INDEX per element."""
    elems = [
        c
        for c in node.children
        if c.is_named
        and c.type
        not in (
            RubyNodeType.OPEN_BRACE,
            RubyNodeType.CLOSE_BRACE,
            RubyNodeType.OPEN_BRACKET,
            RubyNodeType.CLOSE_BRACKET,
        )
    ]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elems))))
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("list"), size_reg=size_reg),
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=ctx.node_text(elem)))
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


def lower_element_reference(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `arr[idx]` as LOAD_INDEX, `arr[1..3]` as CALL_FUNCTION('slice')."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(named_children[0])
    if len(named_children) > 1 and named_children[1].type == RubyNodeType.RANGE:
        return _lower_range_slice(ctx, named_children[1], obj_reg)
    # arr[start, length] — Ruby's two-arg slice: start at index, take N elements
    if len(named_children) == 3:
        return _lower_positional_slice(ctx, named_children, obj_reg, node)
    idx_reg = (
        ctx.lower_expr(named_children[1])
        if len(named_children) > 1
        else ctx.fresh_reg()
    )
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
    )
    return reg


def _lower_range_slice(
    ctx: TreeSitterEmitContext, range_node, collection_reg: str
) -> Register:
    """Lower arr[start..end] as CALL_FUNCTION('slice', collection, start, end+1).

    Ruby's inclusive range (1..3) maps to Python's slice(1, 4).
    Exclusive range (1...3) maps to slice(1, 3).
    """
    named = [c for c in range_node.children if c.is_named]
    start_reg = ctx.lower_expr(named[0]) if len(named) > 0 else _make_const(ctx, "0")
    end_reg = (
        ctx.lower_expr(named[1])
        if len(named) > 1
        else _make_const(ctx, ctx.constants.none_literal)
    )
    # Inclusive range (..) needs end+1; exclusive (...) uses end directly
    is_exclusive = any(c.type == "..." for c in range_node.children)
    if not is_exclusive and len(named) > 1:
        one_reg = _make_const(ctx, "1")
        adjusted_end = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(result_reg=adjusted_end, operator="+", left=end_reg, right=one_reg),
            node=range_node,
        )
        end_reg = adjusted_end
    none_reg = _make_const(ctx, ctx.constants.none_literal)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="slice",
            args=(
                collection_reg,
                start_reg,
                end_reg,
                none_reg,
            ),
        ),
        node=range_node,
    )
    return reg


def _lower_positional_slice(
    ctx: TreeSitterEmitContext, named_children: list, collection_reg: str, node
) -> Register:
    """Lower arr[start, length] as CALL_FUNCTION('slice', arr, start, start+length)."""
    start_reg = ctx.lower_expr(named_children[1])
    length_reg = ctx.lower_expr(named_children[2])
    stop_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(result_reg=stop_reg, operator="+", left=start_reg, right=length_reg),
        node=node,
    )
    none_reg = _make_const(ctx, ctx.constants.none_literal)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="slice",
            args=(
                collection_reg,
                start_reg,
                stop_reg,
                none_reg,
            ),
        ),
        node=node,
    )
    return reg


def _make_const(ctx: TreeSitterEmitContext, value: str) -> Register:
    """Emit a CONST and return the register."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=value))
    return reg


def lower_ruby_conditional(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `condition ? true_expr : false_expr` as ternary."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    true_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    false_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)))

    ctx.emit_inst(Label_(label=true_label))
    true_reg = ctx.lower_expr(true_node) if true_node else ctx.fresh_reg()
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit_inst(DeclVar(name=result_var, value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    false_reg = ctx.lower_expr(false_node) if false_node else ctx.fresh_reg()
    ctx.emit_inst(DeclVar(name=result_var, value_reg=false_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=result_var))
    return result_reg


def lower_ruby_self(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `self` as LOAD_VAR('self')."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=reg, name=constants.PARAM_SELF), node=node)
    return reg


def lower_ruby_super(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `super` or `super(args)` as CALL_FUNCTION("super", ...args)."""
    args_node = next(
        (c for c in node.children if c.type == RubyNodeType.ARGUMENT_LIST),
        None,
    )
    arg_regs = extract_call_args(ctx, args_node) if args_node else []
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name="super", args=tuple(arg_regs)), node=node
    )
    return reg


def lower_ruby_yield(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `yield` or `yield expr` as CALL_FUNCTION("yield", ...args)."""
    args_node = next(
        (c for c in node.children if c.type == RubyNodeType.ARGUMENT_LIST),
        None,
    )
    arg_regs = extract_call_args(ctx, args_node) if args_node else []
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name="yield", args=tuple(arg_regs)), node=node
    )
    return reg


def lower_ruby_pattern(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower a `pattern` wrapper node by lowering its inner child."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


# ── Ruby block as inline closure ─────────────────────────────────────


def lower_ruby_block(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower a Ruby block (curly brace) or do_block (do/end) as inline closure.

    BRANCH end -> LABEL block_ -> params -> body -> CONST nil -> RETURN -> LABEL end -> CONST func:label
    """
    block_label = ctx.fresh_label("block")
    end_label = ctx.fresh_label("block_end")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=block_label))

    # Lower block parameters from block_parameters or |x, y| syntax
    params_node = next(
        (c for c in node.children if c.type == RubyNodeType.BLOCK_PARAMETERS),
        None,
    )
    if params_node:
        lower_ruby_params(ctx, params_node)

    # Lower block body
    body_node = next(
        (
            c
            for c in node.children
            if c.type in (RubyNodeType.BLOCK_BODY, RubyNodeType.BODY_STATEMENT)
        ),
        None,
    )
    if body_node:
        ctx.lower_block(body_node)
    else:
        # Inline body: lower all named children except params and delimiters
        for child in node.children:
            if (
                child.is_named
                and child.type
                not in (
                    RubyNodeType.BLOCK_PARAMETERS,
                    RubyNodeType.OPEN_BRACE,
                    RubyNodeType.CLOSE_BRACE,
                    RubyNodeType.DO,
                    RubyNodeType.END,
                )
                and child.type not in ctx.constants.noise_types
                and child.type not in ctx.constants.comment_types
            ):
                ctx.lower_stmt(child)

    nil_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=nil_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=nil_reg))

    ctx.emit_inst(Label_(label=end_label))

    ref_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=ref_reg, value=f"func:{block_label}"), node=node)
    return ref_reg


# ── Ruby params ──────────────────────────────────────────────────────


def lower_ruby_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower Ruby function/block parameters."""
    param_index = 0
    for child in params_node.children:
        if child.type in (
            RubyNodeType.OPEN_PAREN,
            RubyNodeType.CLOSE_PAREN,
            RubyNodeType.COMMA,
            RubyNodeType.PIPE,
        ):
            continue
        default_value_node = None
        if child.type == RubyNodeType.OPTIONAL_PARAMETER:
            pname = ctx.node_text(child.children[0])
            default_value_node = child.children[-1]
        elif child.type == RubyNodeType.IDENTIFIER:
            pname = ctx.node_text(child)
        else:
            pname = _extract_param_name(ctx, child)
        if pname is None:
            continue
        ctx.emit_inst(
            Symbolic(
                result_reg=ctx.fresh_reg(), hint=f"{constants.PARAM_PREFIX}{pname}"
            ),
            node=child,
        )
        ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
        if default_value_node is not None:
            from interpreter.frontends.common.default_params import (
                emit_default_param_guard,
            )

            emit_default_param_guard(ctx, pname, param_index, default_value_node)
        param_index += 1


def _extract_param_name(ctx: TreeSitterEmitContext, child) -> str | None:
    """Extract parameter name from a parameter node."""
    if child.type == RubyNodeType.IDENTIFIER:
        return ctx.node_text(child)
    # Try common field names
    for field in ("name", "pattern"):
        name_node = child.child_by_field_name(field)
        if name_node:
            return ctx.node_text(name_node)
    # Try first identifier child
    id_node = next(
        (sub for sub in child.children if sub.type == RubyNodeType.IDENTIFIER),
        None,
    )
    if id_node:
        return ctx.node_text(id_node)
    return None


# ── Ruby store target ────────────────────────────────────────────────


def lower_ruby_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Ruby-specific store target handling for instance variables and element references."""
    if target.type == RubyNodeType.INSTANCE_VARIABLE:
        raw = ctx.node_text(target)
        field_name = raw.lstrip("@")
        self_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadVar(result_reg=self_reg, name=constants.PARAM_SELF), node=parent_node
        )
        ctx.emit_inst(
            StoreField(obj_reg=self_reg, field_name=field_name, value_reg=val_reg),
            node=parent_node,
        )
    elif target.type in (
        RubyNodeType.IDENTIFIER,
        RubyNodeType.CONSTANT,
        RubyNodeType.GLOBAL_VARIABLE,
        RubyNodeType.CLASS_VARIABLE,
    ):
        ctx.emit_inst(
            StoreVar(name=ctx.node_text(target), value_reg=val_reg), node=parent_node
        )
    elif target.type == RubyNodeType.ELEMENT_REFERENCE:
        named_children = [c for c in target.children if c.is_named]
        if len(named_children) >= 2:
            obj_reg = ctx.lower_expr(named_children[0])
            idx_reg = ctx.lower_expr(named_children[1])
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
        else:
            _fallback_store(ctx, target, val_reg, parent_node)
    else:
        _fallback_store(ctx, target, val_reg, parent_node)


def _fallback_store(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Fallback store: delegate to common store_target logic."""
    from interpreter.frontends.common.expressions import lower_store_target

    lower_store_target(ctx, target, val_reg, parent_node)
