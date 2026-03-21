"""C#-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.csharp.expressions import lower_csharp_params
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.frontends.common.declarations import (
    FieldInit,
    emit_field_initializers,
    emit_synthetic_init,
)
from interpreter.type_expr import ScalarType


def lower_local_decl_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower local_declaration_statement -> variable_declaration -> variable_declarator."""
    for child in node.children:
        if child.type == NT.VARIABLE_DECLARATION:
            lower_variable_declaration(ctx, child)


def lower_variable_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a variable_declaration node with one or more declarators."""
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    is_ref = any(child.type == NT.REF_TYPE for child in node.children)
    for child in node.children:
        if child.type == NT.VARIABLE_DECLARATOR:
            _lower_csharp_declarator(ctx, child, type_hint=type_hint, is_ref=is_ref)


def _lower_csharp_declarator(
    ctx: TreeSitterEmitContext, node, type_hint: str = "", is_ref: bool = False
) -> None:
    """Lower a C# variable_declarator.

    The name is the first named child (identifier).
    The initializer value is the named child after the '=' token.
    When *is_ref* is True, the variable is a ref local and joins
    ``ctx.byref_params`` so reads/writes dereference through the pointer.
    """
    name_node = None
    value_node = None
    found_equals = False
    for child in node.children:
        if child.type == NT.IDENTIFIER and name_node is None:
            name_node = child
        elif child.type == NT.EQUALS_SIGN or ctx.node_text(child) == "=":
            found_equals = True
        elif found_equals and child.is_named and value_node is None:
            value_node = child

    if name_node is None:
        return

    var_name = ctx.declare_block_var(ctx.node_text(name_node))
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
        )
    ctx.emit(
        Opcode.DECL_VAR,
        operands=[var_name, val_reg],
        node=node,
    )
    ctx.seed_var_type(var_name, type_hint)
    if is_ref:
        ctx.byref_params.add(var_name)


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


def _has_static_modifier(ctx: TreeSitterEmitContext, node) -> bool:
    """Return True if *node* has a ``static`` modifier."""
    return any(
        c.type == NT.MODIFIER and ctx.node_text(c) == "static" for c in node.children
    )


def lower_method_decl(
    ctx: TreeSitterEmitContext, node, inject_this: bool = False
) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_normalized_type(ctx, node, "returns", ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    saved_byref = ctx.byref_params.copy()
    if inject_this:
        _emit_this_param(ctx)

    if params_node:
        lower_csharp_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    ctx.byref_params = saved_byref

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


def lower_constructor_decl(
    ctx: TreeSitterEmitContext, node, field_inits: list[FieldInit] = []
) -> None:
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    initializer_node = next(
        (c for c in node.children if c.type == NT.CONSTRUCTOR_INITIALIZER),
        None,
    )

    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    saved_byref = ctx.byref_params.copy()
    _emit_this_param(ctx)

    if params_node:
        lower_csharp_params(ctx, params_node)

    # Prepend field initializers before the constructor body
    emit_field_initializers(ctx, field_inits)

    # Handle : this(args) constructor chaining
    if initializer_node:
        _lower_constructor_initializer(ctx, initializer_node)

    if body_node:
        ctx.lower_block(body_node)

    ctx.byref_params = saved_byref

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


def _lower_constructor_initializer(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``: this(args)`` as CALL_METHOD on this for __init__."""
    target = next(
        (c for c in node.children if c.type == NT.THIS),
        None,
    )
    if target is None:
        return  # :base() — not yet supported
    args_node = next(
        (c for c in node.children if c.type == NT.ARGUMENT_LIST),
        None,
    )
    arg_regs = [
        ctx.lower_expr(next((gc for gc in arg.children if gc.is_named), arg))
        for arg in (args_node.children if args_node else [])
        if arg.type == NT.ARGUMENT
    ]
    this_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
    ctx.emit(
        Opcode.CALL_METHOD,
        result_reg=ctx.fresh_reg(),
        operands=[this_reg, "__init__"] + arg_regs,
        node=node,
    )


_CLASS_BODY_METHOD_TYPES = frozenset(
    {NT.METHOD_DECLARATION, NT.CONSTRUCTOR_DECLARATION}
)
_CLASS_BODY_SKIP_TYPES = frozenset(
    {NT.MODIFIER, NT.ATTRIBUTE_LIST, NT.LBRACE, NT.RBRACE}
)


def _lower_class_body(ctx: TreeSitterEmitContext, node) -> list:
    """Collect class-body children for top-level hoisting. Methods first, then rest."""
    methods: list = []
    rest: list = []
    for child in node.children:
        if child.type in _CLASS_BODY_SKIP_TYPES or not child.is_named:
            continue
        elif child.type in _CLASS_BODY_METHOD_TYPES:
            methods.append(child)
        else:
            rest.append(child)
    return methods + rest


def _lower_deferred_class_child(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single deferred class-body child at top level."""
    if child.type == NT.METHOD_DECLARATION:
        lower_method_decl(ctx, child, inject_this=not _has_static_modifier(ctx, child))
    elif child.type == NT.CONSTRUCTOR_DECLARATION:
        lower_constructor_decl(ctx, child)
    elif child.type == NT.FIELD_DECLARATION:
        lower_field_decl(ctx, child)
    elif child.type == NT.PROPERTY_DECLARATION:
        lower_property_decl(ctx, child)
    else:
        ctx.lower_stmt(child)


def _extract_csharp_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class/interface names from a C# class_declaration node."""
    base_list = next((c for c in node.children if c.type == NT.BASE_LIST), None)
    if base_list is None:
        return []
    return [
        ctx.node_text(c)
        for c in base_list.children
        if c.type in (NT.IDENTIFIER, NT.TYPE_IDENTIFIER, NT.GENERIC_NAME)
    ]


def _collect_csharp_all_field_names(
    ctx: TreeSitterEmitContext, deferred: list
) -> set[str]:
    """Collect ALL instance field names from deferred class-body children."""
    names: set[str] = set()
    for child in deferred:
        if child.type != NT.FIELD_DECLARATION or _has_static_modifier(ctx, child):
            continue
        for vdecl_child in child.children:
            if vdecl_child.type != NT.VARIABLE_DECLARATION:
                continue
            for decl in vdecl_child.children:
                if decl.type != NT.VARIABLE_DECLARATOR:
                    continue
                name_node = next(
                    (c for c in decl.children if c.type == NT.IDENTIFIER), None
                )
                if name_node is not None:
                    names.add(ctx.node_text(name_node))
    return names


def lower_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_csharp_parents(ctx, node)
    for parent in parents:
        ctx.seed_interface_impl(class_name, parent)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    deferred = _lower_class_body(ctx, body_node) if body_node else []
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])

    saved_class = ctx._current_class_name
    saved_field_names = ctx._class_field_names
    ctx._current_class_name = class_name

    # Collect ALL instance field names for implicit-this detection in constructors
    ctx._class_field_names = _collect_csharp_all_field_names(ctx, deferred)

    # Collect field initializers from non-static field declarations
    field_inits: list[FieldInit] = [
        init
        for child in deferred
        if child.type == NT.FIELD_DECLARATION and not _has_static_modifier(ctx, child)
        for init in _collect_csharp_field_inits(ctx, child)
    ]
    has_constructor = any(
        child.type == NT.CONSTRUCTOR_DECLARATION for child in deferred
    )

    for child in deferred:
        if child.type == NT.FIELD_DECLARATION and not _has_static_modifier(ctx, child):
            continue  # Instance field — already collected for __init__
        elif child.type == NT.CONSTRUCTOR_DECLARATION:
            lower_constructor_decl(ctx, child, field_inits=field_inits)
        else:
            _lower_deferred_class_child(ctx, child)

    if not has_constructor and field_inits:
        emit_synthetic_init(ctx, field_inits)

    ctx._current_class_name = saved_class
    ctx._class_field_names = saved_field_names


def _collect_csharp_field_inits(ctx: TreeSitterEmitContext, node) -> list[FieldInit]:
    """Collect (field_name, value_node) pairs from a C# field_declaration.

    Does NOT emit any IR — callers pass the result to
    ``emit_field_initializers`` or ``emit_synthetic_init``.
    """
    inits: list[FieldInit] = []
    for child in node.children:
        if child.type == NT.VARIABLE_DECLARATION:
            for decl in child.children:
                if decl.type == NT.VARIABLE_DECLARATOR:
                    name_node = None
                    value_node = None
                    found_equals = False
                    for sub in decl.children:
                        if sub.type == NT.IDENTIFIER and name_node is None:
                            name_node = sub
                        elif sub.type == NT.EQUALS_SIGN or ctx.node_text(sub) == "=":
                            found_equals = True
                        elif found_equals and sub.is_named and value_node is None:
                            value_node = sub
                    if name_node and value_node:
                        inits.append((ctx.node_text(name_node), value_node))
    return inits


def lower_field_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a field declaration inside a class body."""
    for child in node.children:
        if child.type == NT.VARIABLE_DECLARATION:
            lower_variable_declaration(ctx, child)


def lower_property_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a property declaration as STORE_FIELD on this."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return
    prop_name = ctx.node_text(name_node)

    this_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])

    # Check for an initializer (e.g. ``= 42``)
    initializer_node = _find_property_initializer(ctx, node)
    if initializer_node:
        val_reg = ctx.lower_expr(initializer_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
            node=node,
        )

    ctx.emit(
        Opcode.STORE_FIELD,
        operands=[this_reg, prop_name, val_reg],
        node=node,
    )

    # Lower accessor bodies (get { ... } / set { ... }) if present
    accessor_list = next((c for c in node.children if c.type == NT.ACCESSOR_LIST), None)
    if accessor_list:
        for accessor in (
            c for c in accessor_list.children if c.type == NT.ACCESSOR_DECLARATION
        ):
            body_block = next(
                (b for b in accessor.children if b.type == NT.BLOCK), None
            )
            if body_block:
                ctx.lower_block(body_block)


def _find_property_initializer(ctx: TreeSitterEmitContext, node) -> object | None:
    """Find the initializer expression after ``=`` in a property_declaration."""
    found_eq = False
    for child in node.children:
        if not child.is_named and ctx.node_text(child) == "=":
            found_eq = True
            continue
        if found_eq and child.is_named and child.type != NT.ACCESSOR_LIST:
            return child
    return None


def lower_interface_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower interface_declaration as CLASS block with method definitions.

    Mirrors lower_class_def so that interface method return types are seeded
    into func_return_types for type inference.
    """
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    if not name_node:
        return
    iface_name = ctx.node_text(name_node)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{iface_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{iface_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    deferred = _lower_class_body(ctx, body_node) if body_node else []
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(iface_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[iface_name, cls_reg])

    saved_class = ctx._current_class_name
    ctx._current_class_name = iface_name
    for child in deferred:
        _lower_deferred_class_child(ctx, child)
    ctx._current_class_name = saved_class


def lower_enum_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_declaration as NEW_OBJECT with STORE_INDEX per member."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = next(
        (c for c in node.children if c.type == NT.ENUM_MEMBER_DECLARATION_LIST),
        None,
    )
    if name_node:
        enum_name = ctx.node_text(name_node)
        obj_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[f"enum:{enum_name}"],
            node=node,
        )
        if body_node:
            for i, child in enumerate(
                c for c in body_node.children if c.type == NT.ENUM_MEMBER_DECLARATION
            ):
                member_name_node = child.child_by_field_name("name")
                member_name = (
                    ctx.node_text(member_name_node)
                    if member_name_node
                    else ctx.node_text(child)
                )
                key_reg = ctx.fresh_reg()
                ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                val_reg = ctx.fresh_reg()
                ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        ctx.emit(Opcode.DECL_VAR, operands=[enum_name, obj_reg])


def lower_namespace(ctx: TreeSitterEmitContext, node) -> None:
    """Lower namespace as a block -- descend into its body."""
    body_node = node.child_by_field_name("body")
    if body_node:
        ctx.lower_block(body_node)


def lower_file_scoped_namespace(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `namespace Foo;` — lower all child declarations (no body block)."""
    for child in node.children:
        if (
            child.is_named
            and child.type != NT.IDENTIFIER
            and child.type != NT.QUALIFIED_NAME
        ):
            ctx.lower_stmt(child)


def lower_local_function_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower local functions inside method bodies -- like method_declaration."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    if name_node is None:
        name_node = next((c for c in node.children if c.type == NT.IDENTIFIER), None)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node is None:
        params_node = next(
            (c for c in node.children if c.type == NT.PARAMETER_LIST), None
        )
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    if body_node is None:
        body_node = next((c for c in node.children if c.type == NT.BLOCK), None)

    func_name = ctx.node_text(name_node) if name_node else "__local_fn"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    saved_byref = ctx.byref_params.copy()
    if params_node:
        lower_csharp_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    ctx.byref_params = saved_byref

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


def lower_event_field_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower event_field_declaration by delegating to variable_declaration child."""
    for child in node.children:
        if child.type == NT.VARIABLE_DECLARATION:
            lower_variable_declaration(ctx, child)


def lower_event_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower event_declaration: extract name, CONST + STORE_VAR."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return
    event_name = ctx.node_text(name_node)
    val_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=val_reg,
        operands=[f"event:{event_name}"],
        node=node,
    )
    ctx.emit(
        Opcode.DECL_VAR,
        operands=[event_name, val_reg],
        node=node,
    )


def lower_delegate_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `public delegate void Notify(string message);` as function stub."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    func_name = ctx.node_text(name_node) if name_node else "__delegate"
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
