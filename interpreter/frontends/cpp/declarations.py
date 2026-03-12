"""C++-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.c.declarations import (
    extract_declarator_name,
    _find_function_declarator,
    lower_c_params,
    lower_declaration,
    lower_struct_field,
)
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.cpp.node_types import CppNodeType
from interpreter.type_expr import ScalarType
from interpreter.frontends.common.declarations import (
    FieldInit,
    emit_field_initializers,
    emit_synthetic_init,
    make_class_ref,
)


def lower_cpp_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a C++ declaration using C++ struct type detection."""
    struct_type = _extract_cpp_struct_type(ctx, node)
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)
    for child in node.children:
        if child.type == CppNodeType.INIT_DECLARATOR:
            from interpreter.frontends.c.declarations import _lower_init_declarator

            _lower_init_declarator(
                ctx, child, struct_type=struct_type, type_hint=type_hint
            )
        elif child.type == CppNodeType.IDENTIFIER:
            var_name = ctx.declare_block_var(ctx.node_text(child))
            if struct_type:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=val_reg,
                    operands=[struct_type],
                    node=node,
                )
            else:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[ctx.constants.none_literal],
                )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[var_name, val_reg],
                node=node,
            )
            ctx.seed_var_type(var_name, type_hint)


def _extract_cpp_struct_type(ctx: TreeSitterEmitContext, node) -> str:
    """Return struct/class type name from a declaration, or ''.

    Extends the C version to also detect bare ``type_identifier``
    nodes (``Counter c;`` without ``struct`` keyword).
    """
    from interpreter.frontends.c.declarations import _extract_struct_type

    result = _extract_struct_type(ctx, node)
    if result:
        return result
    for child in node.children:
        if child.type == CppNodeType.TYPE_IDENTIFIER:
            return ctx.node_text(child)
    return ""


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
        Opcode.STORE_VAR,
        operands=["this", param_reg],
    )
    ctx.seed_var_type("this", class_type)


def _extract_cpp_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class names from a C++ class/struct specifier."""
    base_clause = next(
        (c for c in node.children if c.type == CppNodeType.BASE_CLASS_CLAUSE), None
    )
    if base_clause is None:
        return []
    return [
        ctx.node_text(c)
        for c in base_clause.children
        if c.type == CppNodeType.TYPE_IDENTIFIER
    ]


def _collect_cpp_field_init(ctx: TreeSitterEmitContext, node) -> list[FieldInit]:
    """Collect (field_name, value_node) from a C++ field_declaration.

    Returns a list with at most one element.  The value_node is the
    ``default_value`` field (e.g. the ``0`` in ``int count = 0;``).
    Field declarations without a default_value are skipped.
    """
    name_node = node.child_by_field_name("declarator")
    value_node = node.child_by_field_name("default_value")
    if name_node and value_node:
        return [(ctx.node_text(name_node), value_node)]
    return []


def _is_cpp_constructor(ctx: TreeSitterEmitContext, child, class_name: str) -> bool:
    """Return True if *child* is a constructor (method named same as class)."""
    if child.type != CppNodeType.FUNCTION_DEFINITION:
        return False
    decl = child.child_by_field_name("declarator")
    if decl is None:
        return False
    if decl.type == CppNodeType.FUNCTION_DECLARATOR:
        name_node = decl.child_by_field_name("declarator")
        return name_node is not None and ctx.node_text(name_node) == class_name
    func_decl = _find_function_declarator(decl)
    if func_decl:
        name_node = func_decl.child_by_field_name("declarator")
        return name_node is not None and ctx.node_text(name_node) == class_name
    return False


def _lower_cpp_constructor_with_field_inits(
    ctx: TreeSitterEmitContext, node, field_inits: list[FieldInit] = []
) -> None:
    """Lower an explicit C++ constructor, prepending field initializers.

    Emits as ``__init__`` so the VM constructor mechanism can find it.
    """
    declarator_node = node.child_by_field_name("declarator")
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    init_list_node = next(
        (c for c in node.children if c.type == CppNodeType.FIELD_INITIALIZER_LIST),
        None,
    )

    params_node = None
    if declarator_node:
        if declarator_node.type == CppNodeType.FUNCTION_DECLARATOR:
            params_node = declarator_node.child_by_field_name(
                ctx.constants.func_params_field
            )
        else:
            func_decl = _find_function_declarator(declarator_node)
            if func_decl:
                params_node = func_decl.child_by_field_name(
                    ctx.constants.func_params_field
                )

    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    _emit_this_param(ctx)

    if params_node:
        lower_c_params(ctx, params_node)

    # Prepend field initializers before body
    emit_field_initializers(ctx, field_inits)

    if init_list_node:
        lower_field_initializer_list(ctx, init_list_node)

    if body_node:
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
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def lower_class_specifier(ctx: TreeSitterEmitContext, node) -> None:
    """Lower class_specifier (C++ class with field_declaration_list body)."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_cpp_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    # Collect field initializers from field_declaration nodes
    field_inits: list[FieldInit] = []
    if body_node:
        field_inits = [
            init
            for child in body_node.children
            if child.type == CppNodeType.FIELD_DECLARATION
            for init in _collect_cpp_field_init(ctx, child)
        ]

    has_constructor = body_node is not None and any(
        _is_cpp_constructor(ctx, child, class_name) for child in body_node.children
    )

    if body_node:
        _lower_cpp_class_body_b2(ctx, body_node, class_name, field_inits)

    if not has_constructor and field_inits:
        emit_synthetic_init(ctx, field_inits)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[make_class_ref(class_name, class_label, parents)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])


def _lower_cpp_class_body_b2(
    ctx: TreeSitterEmitContext,
    node,
    class_name: str,
    field_inits: list[FieldInit],
) -> None:
    """Lower class body with B2 field-init routing.

    Field declarations with initializers are skipped (handled via
    constructor prepending or synthetic ``__init__``).  Constructors
    are routed through ``_lower_cpp_constructor_with_field_inits``.
    """
    from interpreter.frontends.cpp.control_flow import lower_template_decl

    saved_class = ctx._current_class_name
    ctx._current_class_name = class_name

    for child in node.children:
        if child.type == CppNodeType.FUNCTION_DEFINITION:
            if _is_cpp_constructor(ctx, child, class_name):
                _lower_cpp_constructor_with_field_inits(ctx, child, field_inits)
            else:
                lower_cpp_method(ctx, child)
        elif child.type == CppNodeType.DECLARATION:
            lower_declaration(ctx, child)
        elif child.type == CppNodeType.FIELD_DECLARATION:
            if _collect_cpp_field_init(ctx, child):
                continue  # Instance field with init — handled via constructor
            lower_struct_field(ctx, child)
        elif child.type == CppNodeType.TEMPLATE_DECLARATION:
            lower_template_decl(ctx, child)
        elif child.type == CppNodeType.FRIEND_DECLARATION:
            continue
        elif child.type == CppNodeType.ACCESS_SPECIFIER:
            continue
        elif child.type == CppNodeType.FIELD_INITIALIZER_LIST:
            lower_field_initializer_list(ctx, child)
        elif child.is_named and child.type not in ("{", "}"):
            ctx.lower_stmt(child)

    ctx._current_class_name = saved_class


def lower_cpp_class_body(ctx: TreeSitterEmitContext, node) -> None:
    """Lower field_declaration_list (C++ class/struct body)."""
    from interpreter.frontends.cpp.control_flow import lower_template_decl

    for child in node.children:
        if child.type == CppNodeType.FUNCTION_DEFINITION:
            lower_cpp_method(ctx, child)
        elif child.type == CppNodeType.DECLARATION:
            lower_declaration(ctx, child)
        elif child.type == CppNodeType.FIELD_DECLARATION:
            lower_struct_field(ctx, child)
        elif child.type == CppNodeType.TEMPLATE_DECLARATION:
            lower_template_decl(ctx, child)
        elif child.type == CppNodeType.FRIEND_DECLARATION:
            continue
        elif child.type == CppNodeType.ACCESS_SPECIFIER:
            continue
        elif child.type == CppNodeType.FIELD_INITIALIZER_LIST:
            lower_field_initializer_list(ctx, child)
        elif child.is_named and child.type not in ("{", "}"):
            ctx.lower_stmt(child)


def lower_cpp_method(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a function_definition inside a class/struct body, injecting param:this."""
    declarator_node = node.child_by_field_name("declarator")
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    init_list_node = next(
        (c for c in node.children if c.type == CppNodeType.FIELD_INITIALIZER_LIST),
        None,
    )

    func_name = "__anon"
    params_node = None

    if declarator_node:
        if declarator_node.type == CppNodeType.FUNCTION_DECLARATOR:
            name_node = declarator_node.child_by_field_name("declarator")
            params_node = declarator_node.child_by_field_name(
                ctx.constants.func_params_field
            )
            func_name = (
                extract_declarator_name(ctx, name_node) if name_node else "__anon"
            )
        else:
            func_decl = _find_function_declarator(declarator_node)
            if func_decl:
                name_node = func_decl.child_by_field_name("declarator")
                params_node = func_decl.child_by_field_name(
                    ctx.constants.func_params_field
                )
                func_name = (
                    extract_declarator_name(ctx, name_node) if name_node else "__anon"
                )
            else:
                func_name = extract_declarator_name(ctx, declarator_node)

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    _emit_this_param(ctx)

    if params_node:
        lower_c_params(ctx, params_node)

    if init_list_node:
        lower_field_initializer_list(ctx, init_list_node)

    if body_node:
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
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def lower_field_initializer_list(ctx: TreeSitterEmitContext, node) -> None:
    """Lower field_initializer_list: : field(val), field2(val2).

    Emits: LOAD_VAR this -> [lower_expr(arg) -> STORE_FIELD this, field, val] x N
    """
    this_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_VAR,
        result_reg=this_reg,
        operands=["this"],
        node=node,
    )
    for child in node.children:
        if child.type == CppNodeType.FIELD_INITIALIZER:
            field_node = next(
                (c for c in child.children if c.type == CppNodeType.FIELD_IDENTIFIER),
                None,
            )
            args_node = next(
                (c for c in child.children if c.type == CppNodeType.ARGUMENT_LIST),
                None,
            )
            if field_node is None:
                continue
            field_name = ctx.node_text(field_node)
            if args_node:
                arg_children = [c for c in args_node.children if c.is_named]
                val_reg = (
                    ctx.lower_expr(arg_children[0]) if arg_children else ctx.fresh_reg()
                )
            else:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[ctx.constants.default_return_value],
                )
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[this_reg, field_name, val_reg],
                node=child,
            )


def lower_cpp_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Override C function_def to detect and lower field_initializer_list in constructors."""
    declarator_node = node.child_by_field_name("declarator")
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    init_list_node = next(
        (c for c in node.children if c.type == CppNodeType.FIELD_INITIALIZER_LIST),
        None,
    )

    func_name = "__anon"
    params_node = None

    if declarator_node:
        if declarator_node.type == CppNodeType.FUNCTION_DECLARATOR:
            name_node = declarator_node.child_by_field_name("declarator")
            params_node = declarator_node.child_by_field_name(
                ctx.constants.func_params_field
            )
            func_name = (
                extract_declarator_name(ctx, name_node) if name_node else "__anon"
            )
        else:
            func_decl = _find_function_declarator(declarator_node)
            if func_decl:
                name_node = func_decl.child_by_field_name("declarator")
                params_node = func_decl.child_by_field_name(
                    ctx.constants.func_params_field
                )
                func_name = (
                    extract_declarator_name(ctx, name_node) if name_node else "__anon"
                )
            else:
                func_name = extract_declarator_name(ctx, declarator_node)

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        lower_c_params(ctx, params_node)

    # Emit field initializer list (C++ constructor initializer) before body
    if init_list_node:
        lower_field_initializer_list(ctx, init_list_node)

    if body_node:
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
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def lower_cpp_struct_body(ctx: TreeSitterEmitContext, node) -> None:
    """Override C _lower_struct_body to handle function_definition children."""
    lower_cpp_class_body(ctx, node)


def lower_cpp_struct_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower struct_specifier using C++ class body handling."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)

    if name_node is None and body_node is None:
        return

    struct_name = ctx.node_text(name_node) if name_node else "__anon_struct"
    parents = _extract_cpp_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{struct_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{struct_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    # Collect field initializers
    field_inits: list[FieldInit] = []
    if body_node:
        field_inits = [
            init
            for child in body_node.children
            if child.type == CppNodeType.FIELD_DECLARATION
            for init in _collect_cpp_field_init(ctx, child)
        ]

    has_constructor = body_node is not None and any(
        _is_cpp_constructor(ctx, child, struct_name) for child in body_node.children
    )

    if body_node:
        _lower_cpp_class_body_b2(ctx, body_node, struct_name, field_inits)

    if not has_constructor and field_inits:
        emit_synthetic_init(ctx, field_inits)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[make_class_ref(struct_name, class_label, parents)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[struct_name, cls_reg])
