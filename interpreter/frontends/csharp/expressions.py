"""C#-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.instructions import (
    AddressOf,
    Branch,
    BranchIf,
    CallCtorFunction,
    CallFunction,
    CallMethod,
    CallUnknown,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadIndirect,
    LoadVar,
    NewArray,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    StoreIndirect,
    StoreVar,
    Symbolic,
)
from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    lower_interpolated_string_parts,
)
from interpreter.frontends.common.node_types import CommonNodeType
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.types.type_expr import ScalarType, scalar
from interpreter.register import Register

_BYREF_KEYWORDS = frozenset({"out", "ref", "in"})


def extract_csharp_call_args(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    """Extract call args, emitting ADDRESS_OF for out/ref/in arguments."""
    if args_node is None:
        return []
    regs: list[str] = []
    for c in args_node.children:
        if c.type in (
            CommonNodeType.OPEN_PAREN,
            CommonNodeType.CLOSE_PAREN,
            CommonNodeType.COMMA,
        ):
            continue
        if c.type in (CommonNodeType.ARGUMENT, CommonNodeType.VALUE_ARGUMENT):
            has_byref = any(
                not gc.is_named and ctx.node_text(gc) in _BYREF_KEYWORDS
                for gc in c.children
            )
            inner = next((gc for gc in c.children if gc.is_named), None)
            if inner is None:
                continue
            if has_byref and inner.type == NT.IDENTIFIER:
                # ref x / in x / out existingVar — emit ADDRESS_OF
                reg = ctx.fresh_reg()
                ctx.emit_inst(AddressOf(result_reg=reg, var_name=ctx.node_text(inner)))
                regs.append(reg)
            else:
                # declaration_expression (out int x) or regular arg
                regs.append(ctx.lower_expr(inner))
        elif c.is_named:
            regs.append(ctx.lower_expr(c))
    return regs


def lower_invocation(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower invocation_expression (function field, arguments field)."""
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_csharp_call_args(ctx, args_node) if args_node else []

    if func_node and func_node.type == NT.MEMBER_ACCESS_EXPRESSION:
        obj_node = func_node.child_by_field_name("expression")
        name_node = func_node.child_by_field_name("name")
        if obj_node and name_node:
            obj_reg = ctx.lower_expr(obj_node)
            method_name = ctx.node_text(name_node)
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

    if func_node and func_node.type == NT.IDENTIFIER:
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(result_reg=reg, func_name=func_name, args=tuple(arg_regs)),
            node=node,
        )
        return reg

    # Dynamic / unknown call target
    if func_node:
        target_reg = ctx.lower_expr(func_node)
    else:
        target_reg = ctx.fresh_reg()
        ctx.emit_inst(Symbolic(result_reg=target_reg, hint="unknown_call_target"))
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),
        node=node,
    )
    return reg


def lower_object_creation(ctx: TreeSitterEmitContext, node) -> Register:
    type_node = node.child_by_field_name("type")
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_csharp_call_args(ctx, args_node) if args_node else []
    type_name = ctx.node_text(type_node) if type_node else "Object"
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallCtorFunction(
            result_reg=reg,
            func_name=type_name,
            type_hint=scalar(type_name),
            args=tuple(arg_regs),
        ),
        node=node,
    )
    ctx.seed_register_type(reg, ScalarType(type_name))
    return reg


def lower_member_access(ctx: TreeSitterEmitContext, node) -> Register:
    obj_node = node.child_by_field_name("expression")
    name_node = node.child_by_field_name("name")
    if obj_node is None or name_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(name_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=field_name), node=node
    )
    return reg


def _extract_bracket_index(ctx: TreeSitterEmitContext, bracket_node) -> Register:
    """Unwrap bracketed_argument_list -> argument -> inner expression."""
    if bracket_node is None:
        reg = ctx.fresh_reg()
        ctx.emit_inst(Symbolic(result_reg=reg, hint="unknown_index"))
        return reg
    if bracket_node.type == NT.BRACKETED_ARGUMENT_LIST:
        args = [c for c in bracket_node.children if c.is_named]
        if args:
            inner = args[0]
            # argument node wraps the actual expression
            if inner.type == NT.ARGUMENT:
                expr_children = [c for c in inner.children if c.is_named]
                return (
                    ctx.lower_expr(expr_children[0])
                    if expr_children
                    else ctx.lower_expr(inner)
                )
            return ctx.lower_expr(inner)
        reg = ctx.fresh_reg()
        ctx.emit_inst(Symbolic(result_reg=reg, hint="unknown_index"))
        return reg
    return ctx.lower_expr(bracket_node)


def lower_element_access(ctx: TreeSitterEmitContext, node) -> Register:
    obj_node = node.child_by_field_name("expression")
    bracket_node = node.child_by_field_name("subscript")
    if obj_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    if bracket_node is None:
        bracket_node = next(
            (
                c
                for c in node.children
                if c.is_named and c.type == NT.BRACKETED_ARGUMENT_LIST
            ),
            None,
        )
    idx_reg = _extract_bracket_index(ctx, bracket_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
    )
    return reg


def lower_initializer_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower initializer_expression {a, b, c} as NEW_ARRAY + STORE_INDEX."""
    elems = [
        c
        for c in node.children
        if c.is_named and c.type not in (NT.LBRACE, NT.RBRACE, ",")
    ]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elems))))
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("list"), size_reg=size_reg),
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> Register:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_csharp_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_cast_expr(ctx: TreeSitterEmitContext, node) -> Register:
    value_node = node.child_by_field_name("value")
    if value_node:
        return ctx.lower_expr(value_node)
    children = [c for c in node.children if c.is_named]
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    return lower_const_literal(ctx, node)


def lower_ternary(ctx: TreeSitterEmitContext, node) -> Register:
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
    ctx.emit_inst(DeclVar(name=result_var, value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    false_reg = ctx.lower_expr(false_node)
    ctx.emit_inst(DeclVar(name=result_var, value_reg=false_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=result_var))
    return result_reg


def lower_typeof(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower typeof_expression: typeof(Type)."""
    named_children = [c for c in node.children if c.is_named]
    type_node = next(
        (c for c in named_children if c.type != NT.TYPEOF),
        named_children[0] if named_children else None,
    )
    type_name = ctx.node_text(type_node) if type_node else "Object"
    type_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=type_reg, value=type_name))
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name="typeof", args=(type_reg,)), node=node
    )
    return reg


def lower_is_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower is_expression: operand is Type."""
    named_children = [c for c in node.children if c.is_named]
    operand_node = named_children[0] if named_children else None
    type_node = named_children[1] if len(named_children) > 1 else None

    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    type_reg = ctx.fresh_reg()
    type_name = ctx.node_text(type_node) if type_node else "Object"
    ctx.emit_inst(Const(result_reg=type_reg, value=type_name))
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="is_check",
            args=(
                obj_reg,
                type_reg,
            ),
        ),
        node=node,
    )
    return reg


def lower_as_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower 'as' cast -- lower the left operand, treat cast as passthrough."""
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return lower_const_literal(ctx, node)


def emit_byref_load(ctx: TreeSitterEmitContext, name: str, *, node=None) -> Register:
    """Load a variable, dereferencing if it's a byref (out/ref/in) param."""
    reg = ctx.fresh_reg()
    resolved = ctx.resolve_var(name)
    ctx.emit_inst(LoadVar(result_reg=reg, name=resolved), node=node)
    if name in ctx.byref_params:
        deref_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadIndirect(result_reg=deref_reg, ptr_reg=reg), node=node)
        return deref_reg
    return reg


def emit_byref_store(
    ctx: TreeSitterEmitContext, name: str, val_reg: str, *, node=None
) -> None:
    """Store to a variable, writing through pointer if it's a byref param."""
    if name in ctx.byref_params:
        ptr_reg = ctx.fresh_reg()
        resolved = ctx.resolve_var(name)
        ctx.emit_inst(LoadVar(result_reg=ptr_reg, name=resolved), node=node)
        ctx.emit_inst(StoreIndirect(ptr_reg=ptr_reg, value_reg=val_reg), node=node)
    else:
        ctx.emit_inst(
            StoreVar(name=ctx.resolve_var(name), value_reg=val_reg), node=node
        )


def lower_ref_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower ``ref <expr>`` — emit ADDRESS_OF for identifier targets."""
    inner = next((c for c in node.children if c.is_named), None)
    if inner is not None and inner.type == NT.IDENTIFIER:
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            AddressOf(result_reg=reg, var_name=ctx.node_text(inner)), node=node
        )
        return reg
    # Degraded: unsupported inner expression (arr[i], obj.field) — lower as value
    return ctx.lower_expr(inner) if inner else ctx.fresh_reg()


def lower_csharp_identifier(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower identifier with byref dereference support."""
    name = ctx.node_text(node)
    return emit_byref_load(ctx, name, node=node)


def lower_declaration_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `out int x` / `out var x` declaration_expression.

    Declares the variable in the current scope with a default value (0)
    and emits ADDRESS_OF to produce a Pointer for pass-by-reference.
    """
    name_node = next(
        (c for c in node.children if c.type == NT.IDENTIFIER),
        None,
    )
    var_name = ctx.node_text(name_node) if name_node else "__out_var"
    default_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=default_reg, value="0"))
    ctx.emit_inst(DeclVar(name=var_name, value_reg=default_reg), node=node)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(AddressOf(result_reg=result_reg, var_name=var_name))
    return result_reg


def lower_declaration_pattern(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `int i` declaration pattern -> CONST type + STORE_VAR binding."""
    named_children = [c for c in node.children if c.is_named]
    type_node = named_children[0] if named_children else None
    designation = named_children[1] if len(named_children) > 1 else None

    type_reg = ctx.fresh_reg()
    type_name = ctx.node_text(type_node) if type_node else "Object"
    ctx.emit_inst(Const(result_reg=type_reg, value=type_name))

    if designation:
        var_name = ctx.node_text(designation)
        ctx.emit_inst(DeclVar(name=var_name, value_reg=type_reg), node=node)
    return type_reg


def lower_lambda(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower C# lambda: (params) => expr or (params) => { body }."""
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label("lambda_end")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    saved_byref = ctx.byref_params.copy()
    # Lower parameters
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        lower_csharp_params(ctx, params_node)

    # Lower body
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    if body_node and body_node.type == NT.BLOCK:
        ctx.lower_block(body_node)
    elif body_node:
        # Expression body -- evaluate and return
        body_reg = ctx.lower_expr(body_node)
        ctx.emit_inst(Return_(value_reg=body_reg))

    # Implicit return for block bodies (if no explicit return)
    if body_node and body_node.type == NT.BLOCK:
        none_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=none_reg, value=ctx.constants.default_return_value)
        )
        ctx.emit_inst(Return_(value_reg=none_reg))

    ctx.byref_params = saved_byref
    ctx.emit_inst(Label_(label=end_label))

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=ref_reg, node=node)
    return ref_reg


def lower_array_creation(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower array_creation_expression / implicit_array_creation_expression."""
    # Find initializer: initializer_expression for both explicit and implicit
    init_node = node.child_by_field_name("initializer")
    if init_node is None:
        init_node = next(
            (c for c in node.children if c.type == NT.INITIALIZER_EXPRESSION),
            None,
        )

    if init_node is not None:
        elements = [c for c in init_node.children if c.is_named]
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elements))))
        arr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewArray(result_reg=arr_reg, type_hint=scalar("array"), size_reg=size_reg),
            node=node,
        )
        for i, elem in enumerate(elements):
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
            val_reg = ctx.lower_expr(elem)
            ctx.emit_inst(
                StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg)
            )
        return arr_reg

    # Sized array without initializer: new int[5]
    size_children = [
        c
        for c in node.children
        if c.is_named
        and c.type not in (NT.PREDEFINED_TYPE, NT.TYPE_IDENTIFIER, NT.ARRAY_TYPE)
    ]
    size_node = size_children[0] if size_children else None
    if size_node and size_node.type not in (NT.INITIALIZER_EXPRESSION,):
        size_reg = ctx.lower_expr(size_node)
    else:
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=size_reg, value="0"))
    arr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("array"), size_reg=size_reg),
        node=node,
    )
    return arr_reg


def lower_csharp_interpolated_string(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower C# $\"...{expr}...\" into CONST + expr + BINOP '+' chain."""
    has_interpolation = any(c.type == NT.INTERPOLATION for c in node.children)
    if not has_interpolation:
        return lower_const_literal(ctx, node)

    _INTERPOLATION_NOISE = frozenset(
        {
            NT.INTERPOLATION_BRACE,
            NT.INTERPOLATION_FORMAT_CLAUSE,
            NT.INTERPOLATION_ALIGNMENT_CLAUSE,
        }
    )

    parts: list[str] = []
    for child in node.children:
        if child.type == NT.STRING_CONTENT:
            frag_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Const(result_reg=frag_reg, value=ctx.node_text(child)), node=child
            )
            parts.append(frag_reg)
        elif child.type == NT.INTERPOLATION:
            named = [
                c
                for c in child.children
                if c.is_named and c.type not in _INTERPOLATION_NOISE
            ]
            if named:
                parts.append(ctx.lower_expr(named[0]))
        # skip: interpolation_start, ", punctuation
    return lower_interpolated_string_parts(ctx, parts, node)


def lower_await_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower await_expression as CALL_FUNCTION('await', expr)."""
    children = [c for c in node.children if c.is_named]
    if children:
        inner_reg = ctx.lower_expr(children[0])
    else:
        inner_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=inner_reg, value=ctx.constants.none_literal))
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name="await", args=(inner_reg,)), node=node
    )
    return reg


def lower_conditional_access(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower obj?.Field as LOAD_FIELD (null-safety is semantic)."""
    named = [c for c in node.children if c.is_named]
    if len(named) < 2:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(named[0])
    # The second named child is typically member_binding_expression
    binding_node = named[1]
    if binding_node.type == NT.MEMBER_BINDING_EXPRESSION:
        # Extract the field name from member_binding_expression
        field_node = next(
            (c for c in binding_node.children if c.type == NT.IDENTIFIER), None
        )
        field_name = ctx.node_text(field_node) if field_node else "unknown"
    else:
        field_name = ctx.node_text(binding_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=field_name), node=node
    )
    return reg


def lower_member_binding(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower .Field part of conditional access -- standalone fallback."""
    field_node = next((c for c in node.children if c.type == NT.IDENTIFIER), None)
    field_name = ctx.node_text(field_node) if field_node else "unknown"
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(result_reg=reg, hint=f"member_binding:{field_name}"), node=node
    )
    return reg


def lower_tuple_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower tuple (a, b, c) as NEW_ARRAY with elements."""
    arguments = [c for c in node.children if c.type == NT.ARGUMENT]
    elem_regs = [
        ctx.lower_expr(next((gc for gc in arg.children if gc.is_named), arg))
        for arg in arguments
    ]

    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elem_regs))))
    arr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint=scalar("tuple"), size_reg=size_reg),
        node=node,
    )
    for i, elem_reg in enumerate(elem_regs):
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(
            StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=elem_reg)
        )
    return arr_reg


def lower_is_pattern_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `x is int y` as CALL_FUNCTION('is_check', expr, type)."""
    named = [c for c in node.children if c.is_named]
    operand_node = named[0] if named else None
    pattern_node = named[1] if len(named) > 1 else None

    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()

    # Extract the type from the pattern
    type_name = ctx.node_text(pattern_node) if pattern_node else "Object"
    type_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=type_reg, value=type_name))

    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="is_check",
            args=(
                obj_reg,
                type_reg,
            ),
        ),
        node=node,
    )
    return reg


def lower_implicit_object_creation(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `new()` or `new() { ... }` as NEW_OBJECT + CALL_METHOD constructor."""
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = (
        [
            ctx.lower_expr(c)
            for c in args_node.children
            if c.is_named and c.type not in ("(", ")", ",")
        ]
        if args_node
        else []
    )
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=scalar("__implicit")), node=node
    )
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallMethod(
            result_reg=result_reg,
            obj_reg=obj_reg,
            method_name="constructor",
            args=tuple(arg_regs),
        ),
        node=node,
    )
    return result_reg


def lower_with_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `p1 with { Age = 31 }` as clone(p1) + STORE_FIELD per override."""
    named = [c for c in node.children if c.is_named]
    obj_reg = ctx.lower_expr(named[0]) if named else ctx.fresh_reg()

    # Clone the source object
    clone_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=clone_reg, func_name="clone", args=(obj_reg,)),
        node=node,
    )

    # Apply property overrides from with_initializer children
    for child in node.children:
        if child.type == NT.WITH_INITIALIZER:
            init_named = [c for c in child.children if c.is_named]
            if len(init_named) >= 2:
                field_name = ctx.node_text(init_named[0])
                val_reg = ctx.lower_expr(init_named[1])
                ctx.emit_inst(
                    StoreField(
                        obj_reg=clone_reg, field_name=field_name, value_reg=val_reg
                    ),
                    node=child,
                )

    return clone_reg


def lower_anonymous_object_creation(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `new { Name = expr, Age = expr }` as NEW_OBJECT + STORE_FIELD per property."""
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=scalar("__anon_object")), node=node
    )
    named = [c for c in node.children if c.is_named]
    # Children alternate: identifier, value, identifier, value, ...
    i = 0
    while i + 1 < len(named):
        field_name = ctx.node_text(named[i])
        val_reg = ctx.lower_expr(named[i + 1])
        ctx.emit_inst(
            StoreField(obj_reg=obj_reg, field_name=field_name, value_reg=val_reg),
            node=named[i],
        )
        i += 2
    return obj_reg


def lower_query_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower LINQ `from n in nums where ... select ...` as CALL_FUNCTION chain."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name="linq_query", args=tuple(arg_regs)),
        node=node,
    )
    return reg


def lower_linq_clause(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower LINQ clause (from/select/where) -- lower named children only."""
    named_children = [c for c in node.children if c.is_named]
    last_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=last_reg, value=ctx.constants.none_literal))
    for child in named_children:
        last_reg = ctx.lower_expr(child)
    return last_reg


def lower_csharp_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == NT.IDENTIFIER:
        name = ctx.node_text(target)
        if ctx.symbol_table.resolve_field(ctx._current_class_name, name).name:
            this_reg = ctx.fresh_reg()
            ctx.emit_inst(LoadVar(result_reg=this_reg, name="this"))
            ctx.emit_inst(
                StoreField(obj_reg=this_reg, field_name=name, value_reg=val_reg),
                node=parent_node,
            )
        else:
            emit_byref_store(ctx, name, val_reg, node=parent_node)
    elif target.type == NT.MEMBER_ACCESS_EXPRESSION:
        obj_node = target.child_by_field_name("expression")
        name_node = target.child_by_field_name("name")
        if obj_node and name_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=ctx.node_text(name_node),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == NT.ELEMENT_ACCESS_EXPRESSION:
        obj_node = target.child_by_field_name("expression")
        bracket_node = target.child_by_field_name("subscript")
        if obj_node:
            obj_reg = ctx.lower_expr(obj_node)
            if bracket_node is None:
                bracket_node = next(
                    (
                        c
                        for c in target.children
                        if c.is_named and c.type == NT.BRACKETED_ARGUMENT_LIST
                    ),
                    None,
                )
            idx_reg = _extract_bracket_index(ctx, bracket_node)
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
    else:
        ctx.emit_inst(
            StoreVar(name=ctx.node_text(target), value_reg=val_reg), node=parent_node
        )


# -- shared C# param helper (used by expressions + declarations) ------


def _extract_csharp_default_value(child) -> object:
    """Extract the default value node from a C# parameter (child after '=')."""
    found_eq = False
    for c in child.children:
        if found_eq:
            return c
        if c.type == "=" and c.child_count == 0:
            found_eq = True
    return None


def lower_csharp_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower C# formal parameters (parameter nodes)."""
    ctx.byref_params.clear()
    param_index = 0
    for child in params_node.children:
        if child.type == NT.PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                # Detect out/ref/in modifier
                modifier = next(
                    (
                        c
                        for c in child.children
                        if c.type == NT.MODIFIER
                        and ctx.node_text(c) in ("out", "ref", "in")
                    ),
                    None,
                )
                if modifier:
                    ctx.byref_params.add(pname)
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
                ctx.emit_inst(DeclVar(name=pname, value_reg=param_reg))
                ctx.seed_var_type(pname, type_hint)
                default_value_node = _extract_csharp_default_value(child)
                if default_value_node:
                    from interpreter.frontends.common.default_params import (
                        emit_default_param_guard,
                    )

                    emit_default_param_guard(
                        ctx, pname, param_index, default_value_node
                    )
                param_index += 1


# -- P1 gap handlers ------------------------------------------------------


def lower_checked_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower checked(expr) / unchecked(expr) — just lower the inner expression."""
    named_children = [c for c in node.children if c.is_named]
    return (
        ctx.lower_expr(named_children[0])
        if named_children
        else lower_const_literal(ctx, node)
    )


def lower_range_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `0..5` or `..5` or `0..` as CALL_FUNCTION("range", start, end)."""
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) >= 2:
        start_reg = ctx.lower_expr(named_children[0])
        end_reg = ctx.lower_expr(named_children[1])
    elif len(named_children) == 1:
        start_reg = ctx.lower_expr(named_children[0])
        end_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=end_reg, value=""))
    else:
        start_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=start_reg, value=""))
        end_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=end_reg, value=""))
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
