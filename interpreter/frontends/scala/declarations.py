"""Scala-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.frontends.scala.node_types import ScalaNodeType as NT
from interpreter.frontends.common.declarations import (
    FieldInit,
    emit_field_initializers,
    emit_synthetic_init,
)
from interpreter.type_expr import ScalarType


def lower_enum_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Scala 3 enum definition: enum Color { case Red, Green, Blue }.

    Emits NEW_OBJECT + STORE_FIELD per variant + DECL_VAR, following
    the Rust enum pattern.
    """
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    enum_name = ctx.node_text(name_node) if name_node else "__anon_enum"

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"enum:{enum_name}"],
        node=node,
    )

    if body_node:
        variant_names = [
            ctx.node_text(child.child_by_field_name("name"))
            for child in body_node.named_children
            if child.type == NT.ENUM_CASE_DEFINITIONS
            for child in child.named_children
            if child.type == NT.SIMPLE_ENUM_CASE
            and child.child_by_field_name("name") is not None
        ]
        for variant_name in variant_names:
            variant_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=variant_reg,
                operands=[variant_name],
            )
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, variant_name, variant_reg],
            )

    ctx.emit(Opcode.DECL_VAR, operands=[enum_name, obj_reg])


def _extract_pattern_name(ctx: TreeSitterEmitContext, pattern_node) -> str:
    """Extract name from a pattern node (identifier, typed_pattern, etc.)."""
    if pattern_node is None:
        return "__unknown"
    if pattern_node.type == NT.IDENTIFIER:
        return ctx.node_text(pattern_node)
    # typed_pattern or other wrapper: find the identifier inside
    id_child = next(
        (c for c in pattern_node.children if c.type == NT.IDENTIFIER),
        None,
    )
    if id_child:
        return ctx.node_text(id_child)
    return ctx.node_text(pattern_node)


def _lower_scala_tuple_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower `val (a, b) = expr` — emit LOAD_INDEX + STORE_VAR per element."""
    named_children = [
        c
        for c in pattern_node.children
        if c.type not in (NT.LPAREN, NT.RPAREN, NT.COMMA) and c.is_named
    ]
    for i, child in enumerate(named_children):
        var_name = _extract_pattern_name(ctx, child)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[val_reg, idx_reg],
            node=child,
        )
        ctx.emit(
            Opcode.DECL_VAR,
            operands=[var_name, elem_reg],
            node=parent_node,
        )


def _lower_val_or_var_def(ctx: TreeSitterEmitContext, node) -> None:
    """Shared logic for val_definition and var_definition, with tuple destructuring."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
        )

    if pattern_node is not None and pattern_node.type == NT.TUPLE_PATTERN:
        _lower_scala_tuple_destructure(ctx, pattern_node, val_reg, node)
    else:
        raw_name = _extract_pattern_name(ctx, pattern_node)
        var_name = ctx.declare_block_var(raw_name)
        ctx.emit(
            Opcode.DECL_VAR,
            operands=[var_name, val_reg],
            node=node,
        )
        ctx.seed_var_type(var_name, type_hint)


def lower_val_def(ctx: TreeSitterEmitContext, node) -> None:
    _lower_val_or_var_def(ctx, node)


def lower_var_def(ctx: TreeSitterEmitContext, node) -> None:
    _lower_val_or_var_def(ctx, node)


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:this`` + ``STORE_VAR this`` for instance methods."""
    param_reg = ctx.fresh_reg()
    class_type = ScalarType(ctx._current_class_name)
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=param_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.seed_register_type(param_reg, class_type)
    ctx.seed_param_type("this", class_type)
    ctx.emit(
        Opcode.DECL_VAR,
        operands=["this", param_reg],
    )
    ctx.seed_var_type("this", class_type)


def lower_scala_params(ctx: TreeSitterEmitContext, params_node) -> None:
    param_index = 0
    for child in params_node.children:
        if child.type == NT.PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                type_hint = extract_normalized_type(ctx, child, "type", ctx.type_map)
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=ctx.fresh_reg(),
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(f"%{ctx.reg_counter - 1}", type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, type_hint)
                default_value_node = child.child_by_field_name("default_value")
                if default_value_node:
                    from interpreter.frontends.common.default_params import (
                        emit_default_param_guard,
                    )

                    emit_default_param_guard(
                        ctx, pname, param_index, default_value_node
                    )
                param_index += 1


def _lower_body_with_implicit_return(ctx: TreeSitterEmitContext, body_node) -> str:
    """Lower a Scala function body, returning the last expression's register.

    In Scala, the last expression in a block is the implicit return value.
    Lower all children except the last as statements, then lower the last
    child as an expression.  Returns the register holding the result, or
    empty string if the body has no named children or ends with a statement.
    """
    children = [
        c
        for c in body_node.children
        if c.is_named
        and c.type not in (NT.LBRACE, NT.RBRACE, NT.SEMICOLON)
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
    ]
    if not children:
        return ""
    *init, last = children
    for child in init:
        ctx.lower_stmt(child)
    is_stmt = (
        ctx.stmt_dispatch.get(last.type) is not None
        or last.type in ctx.constants.block_node_types
    )
    # Explicit return already emits its own RETURN opcode
    if is_stmt or last.type == NT.RETURN_EXPRESSION:
        ctx.lower_stmt(last)
        return ""
    return ctx.lower_expr(last)


def lower_function_def(
    ctx: TreeSitterEmitContext, node, inject_this: bool = False
) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    # Scala's grammar uses the same field "parameters" for both type_parameters
    # and value parameters. Use children_by_field_name and pick by node type.
    params_node = next(
        (
            c
            for c in node.children_by_field_name(ctx.constants.func_params_field)
            if c.type == "parameters"
        ),
        None,
    )
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_normalized_type(ctx, node, "return_type", ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if inject_this:
        _emit_this_param(ctx)

    if params_node:
        lower_scala_params(ctx, params_node)

    expr_returned = False
    if body_node:
        if body_node.type in ctx.constants.block_node_types:
            # Block body: implicit return of last expression
            expr_reg = _lower_body_with_implicit_return(ctx, body_node)
            if expr_reg:
                ctx.emit(Opcode.RETURN, operands=[expr_reg])
                expr_returned = True
        else:
            # Expression body (literal, match, if, etc.)
            val_reg = ctx.lower_expr(body_node)
            ctx.emit(Opcode.RETURN, operands=[val_reg])
            expr_returned = True

    if not expr_returned:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


_CLASS_BODY_FUNC_TYPES = frozenset({NT.FUNCTION_DEFINITION})
_SCALA_FIELD_TYPES = frozenset({NT.VAL_DEFINITION, NT.VAR_DEFINITION})


def _lower_auxiliary_constructor(
    ctx: TreeSitterEmitContext,
    node,
    primary_ctor_params: list[str] = [],
    field_inits: list[FieldInit] = [],
) -> None:
    """Lower ``def this(...) = this(args)`` as an ``__init__`` overload.

    Emits this as explicit first param, inlines field initializers,
    and lowers the delegation body as CALL_METHOD on this for __init__.
    """
    params_node = next(
        (
            c
            for c in node.children_by_field_name(ctx.constants.func_params_field)
            if c.type == "parameters"
        ),
        None,
    )
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    _emit_this_param(ctx)

    if params_node:
        lower_scala_params(ctx, params_node)

    # Replay field initializers so all fields exist on the heap
    emit_field_initializers(ctx, field_inits)

    # Lower body: this(args) → CALL_METHOD this __init__ args
    if body_node and body_node.type == NT.CALL_EXPRESSION:
        _lower_this_delegation_call(ctx, body_node)
    elif body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def _lower_this_delegation_call(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``this(args)`` call as CALL_METHOD on this for __init__."""
    args_node = next(
        (c for c in node.children if c.type == NT.ARGUMENTS),
        None,
    )
    arg_regs = [
        ctx.lower_expr(c)
        for c in (args_node.children if args_node else [])
        if c.is_named
    ]
    this_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
    ctx.emit(
        Opcode.CALL_METHOD,
        result_reg=ctx.fresh_reg(),
        operands=[this_reg, "__init__"] + arg_regs,
        node=node,
    )


def _collect_scala_field_init(ctx: TreeSitterEmitContext, node) -> FieldInit | None:
    """Extract (field_name, value_node) from a val/var definition, or None."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    if pattern_node is None or value_node is None:
        return None
    name = _extract_pattern_name(ctx, pattern_node)
    return (name, value_node)


def _lower_class_body_hoisted(
    ctx: TreeSitterEmitContext,
    node,
    inject_this: bool = False,
    collect_field_inits: bool = False,
    primary_ctor_params: list[str] = [],
) -> None:
    """Hoist all class-body children to top level.

    Emits function definitions first (so their refs are registered),
    then field initializers and other statements.  When *collect_field_inits*
    is True, val/var definitions with initializers are collected and emitted
    as a synthetic ``__init__`` instead of top-level ``STORE_VAR``.
    """
    children = [
        c
        for c in node.children
        if c.is_named
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
    ]
    functions = [c for c in children if c.type in _CLASS_BODY_FUNC_TYPES]
    rest = [c for c in children if c.type not in _CLASS_BODY_FUNC_TYPES]

    # Collect field initializers from val/var definitions (only for real classes)
    field_inits: list[FieldInit] = (
        [
            init
            for c in rest
            if c.type in _SCALA_FIELD_TYPES
            for init in [_collect_scala_field_init(ctx, c)]
            if init is not None
        ]
        if collect_field_inits
        else []
    )

    for child in functions:
        name_node = child.child_by_field_name(ctx.constants.func_name_field)
        func_name = ctx.node_text(name_node) if name_node else ""
        if func_name == "this":
            _lower_auxiliary_constructor(ctx, child, primary_ctor_params, field_inits)
        else:
            lower_function_def(ctx, child, inject_this=inject_this)
    for child in rest:
        if (
            collect_field_inits
            and child.type in _SCALA_FIELD_TYPES
            and _collect_scala_field_init(ctx, child) is not None
        ):
            continue  # Skip — will be emitted via synthetic __init__
        ctx.lower_stmt(child)

    if field_inits:
        emit_synthetic_init(ctx, field_inits)


def _extract_scala_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class/trait names from a Scala class/trait/object definition."""
    extends_clause = next(
        (c for c in node.children if c.type == NT.EXTENDS_CLAUSE), None
    )
    if extends_clause is None:
        return []
    return [
        ctx.node_text(c)
        for c in extends_clause.children
        if c.type == NT.TYPE_IDENTIFIER
    ]


def _extract_class_parameter_names(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract field names from a Scala class_parameters node."""
    params_node = next(
        (c for c in node.children if c.type == NT.CLASS_PARAMETERS),
        None,
    )
    if params_node is None:
        return []
    return [
        ctx.node_text(next(c for c in param.children if c.type == NT.IDENTIFIER))
        for param in params_node.children
        if param.type == NT.CLASS_PARAMETER
    ]


def _emit_primary_constructor_init(
    ctx: TreeSitterEmitContext, param_names: list[str]
) -> None:
    """Emit a synthetic __init__ that takes primary constructor params and stores as fields."""
    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    _emit_this_param(ctx)

    for name in param_names:
        param_reg = ctx.fresh_reg()
        ctx.emit(Opcode.SYMBOLIC, result_reg=param_reg, operands=[f"param:{name}"])
        ctx.emit(Opcode.DECL_VAR, operands=[name, param_reg])

    for name in param_names:
        val_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=[name])
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, name, val_reg])

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_scala_parents(ctx, node)

    primary_ctor_params = _extract_class_parameter_names(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if primary_ctor_params:
        _emit_primary_constructor_init(ctx, primary_ctor_params)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])

    if body_node:
        saved_class = ctx._current_class_name
        ctx._current_class_name = class_name
        _lower_class_body_hoisted(
            ctx,
            body_node,
            inject_this=True,
            collect_field_inits=True,
            primary_ctor_params=primary_ctor_params,
        )
        ctx._current_class_name = saved_class


def lower_object_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    obj_name = ctx.node_text(name_node) if name_node else "__anon_object"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{obj_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{obj_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(obj_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[obj_name, cls_reg])

    if body_node:
        _lower_class_body_hoisted(ctx, body_node)


def lower_trait_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower trait_definition like class_definition."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    trait_name = ctx.node_text(name_node) if name_node else "__anon_trait"
    parents = _extract_scala_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(trait_name, class_label, parents, result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[trait_name, cls_reg])


def lower_function_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower abstract function declaration (no body) as function stub."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    func_name = ctx.node_text(name_node) if name_node else "__abstract"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_function_def_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Statement-dispatch wrapper for function_definition."""
    lower_function_def(ctx, node)


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_scala_primary_ctor_fields(class_params_node) -> "dict[str, FieldInfo]":
    """Extract val/var class parameters as fields from a class_parameters node."""
    from interpreter.frontends.symbol_table import FieldInfo

    fields: dict[str, FieldInfo] = {}
    for child in class_params_node.children:
        if child.type != NT.CLASS_PARAMETER:
            continue
        has_val_var = any(
            c.text in (b"val", b"var") for c in child.children if not c.is_named
        )
        if not has_val_var:
            continue
        name_node = child.child_by_field_name("name")
        type_node = child.child_by_field_name("type")
        if name_node is None:
            continue
        fname = name_node.text.decode()
        type_hint = type_node.text.decode() if type_node is not None else ""
        fields[fname] = FieldInfo(
            name=fname, type_hint=type_hint, has_initializer=False
        )
    return fields


def _extract_scala_class(node) -> "tuple[str, ClassInfo] | None":
    """Extract a ClassInfo from a Scala class_definition or case_class_definition node."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo

    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    class_name = name_node.text.decode()

    # Extends clause for parents
    extends_clause = next(
        (c for c in node.children if c.type == NT.EXTENDS_CLAUSE), None
    )
    parents: tuple[str, ...] = ()
    if extends_clause is not None:
        parents = tuple(
            c.text.decode().split("[")[0]
            for c in extends_clause.children
            if c.type in (NT.TYPE_IDENTIFIER, NT.IDENTIFIER)
        )

    fields: dict[str, FieldInfo] = {}

    # Primary constructor parameters with val/var
    class_params = node.child_by_field_name("class_parameters")
    if class_params is not None:
        fields.update(_extract_scala_primary_ctor_fields(class_params))

    body = next((c for c in node.children if c.type == NT.TEMPLATE_BODY), None)
    if body is None:
        return class_name, ClassInfo(
            name=class_name, fields=fields, methods={}, constants={}, parents=parents
        )

    methods: dict[str, FunctionInfo] = {}

    for child in body.children:
        if child.type in (NT.VAL_DEFINITION, NT.VAR_DEFINITION):
            # val_definition: 'val' identifier ':' type_identifier '=' expr
            pname_node = next(
                (c for c in child.children if c.type == NT.IDENTIFIER), None
            )
            ptype_node = child.child_by_field_name("type")
            if pname_node is not None:
                fname = pname_node.text.decode()
                type_hint = ptype_node.text.decode() if ptype_node is not None else ""
                fields[fname] = FieldInfo(
                    name=fname, type_hint=type_hint, has_initializer=True
                )
        elif child.type == NT.FUNCTION_DEFINITION:
            mname_node = child.child_by_field_name("name")
            if mname_node is None:
                continue
            mname = mname_node.text.decode()
            # params are in nested parameter_clause children
            params = tuple(
                p.child_by_field_name("name").text.decode()
                for grandchild in child.children
                if grandchild.type == "parameters"
                for p in grandchild.children
                if p.type == NT.PARAMETER and p.child_by_field_name("name") is not None
            )
            ret_node = child.child_by_field_name("return_type")
            return_type = ret_node.text.decode() if ret_node is not None else ""
            methods[mname] = FunctionInfo(
                name=mname, params=params, return_type=return_type
            )

    return class_name, ClassInfo(
        name=class_name,
        fields=fields,
        methods=methods,
        constants={},
        parents=parents,
    )


def _collect_scala_classes(node, accumulator: "dict[str, ClassInfo]") -> None:
    """Recursively walk the AST and collect all class/case class definition nodes."""
    from interpreter.frontends.symbol_table import ClassInfo

    if node.type in (NT.CLASS_DEFINITION, NT.CASE_CLASS_DEFINITION):
        result = _extract_scala_class(node)
        if result is not None:
            class_name, class_info = result
            accumulator[class_name] = class_info
    for child in node.children:
        _collect_scala_classes(child, accumulator)


def extract_scala_symbols(root) -> "SymbolTable":
    """Walk the Scala AST and return a SymbolTable of all class definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, SymbolTable

    classes: dict[str, ClassInfo] = {}
    _collect_scala_classes(root, classes)
    return SymbolTable(classes=classes)
