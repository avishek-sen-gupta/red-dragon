"""Java-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import Any

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.field_name import FieldName
from interpreter.var_name import VarName
from interpreter.instructions import (
    Branch,
    Const,
    DeclVar,
    Label_,
    LoadVar,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    Symbolic,
)
from interpreter import constants
from interpreter.frontends.java.expressions import lower_java_params
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.frontends.java.node_types import JavaNodeType
from interpreter.frontends.common.declarations import (
    FieldInit,
    emit_field_initializers,
    emit_synthetic_init,
)
from interpreter.types.type_expr import AnnotationType, EnumType, ScalarType, scalar


def lower_local_var_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    for child in node.children:
        if child.type == JavaNodeType.VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                var_name = ctx.declare_block_var(ctx.node_text(name_node))
                val_reg = ctx.lower_expr(value_node)
                ctx.emit_inst(
                    DeclVar(name=VarName(var_name), value_reg=val_reg), node=node
                )
                ctx.seed_var_type(var_name, type_hint)
            elif name_node:
                var_name = ctx.declare_block_var(ctx.node_text(name_node))
                val_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Const(result_reg=val_reg, value=ctx.constants.none_literal)
                )
                ctx.emit_inst(
                    DeclVar(name=VarName(var_name), value_reg=val_reg), node=node
                )
                ctx.seed_var_type(var_name, type_hint)


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:this`` + ``STORE_VAR this`` for instance methods."""
    param_reg = ctx.fresh_reg()
    class_type = ScalarType(ctx._current_class_name)
    ctx.emit_inst(Symbolic(result_reg=param_reg, hint=f"{constants.PARAM_PREFIX}this"))
    ctx.seed_register_type(param_reg, class_type)
    ctx.seed_param_type(constants.PARAM_THIS, class_type)
    ctx.emit_inst(DeclVar(name=VarName(constants.PARAM_THIS), value_reg=param_reg))
    ctx.seed_var_type(constants.PARAM_THIS, class_type)


def _has_static_modifier(node) -> bool:
    """Return True if *node* has a ``static`` modifier."""
    return any(
        c.type == JavaNodeType.MODIFIERS
        and any(m.type == JavaNodeType.STATIC for m in c.children)
        for c in node.children
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

    return_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)
    ctx.reset_method_scope()

    if inject_this:
        _emit_this_param(ctx)

    if params_node:
        lower_java_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_method_decl_stmt(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Statement-dispatch wrapper: method_declaration as statement."""
    lower_method_decl(ctx, node)


_CLASS_BODY_METHOD_TYPES = frozenset(
    {
        JavaNodeType.METHOD_DECLARATION,
        JavaNodeType.CONSTRUCTOR_DECLARATION,
        JavaNodeType.COMPACT_CONSTRUCTOR_DECLARATION,
    }
)
_CLASS_BODY_SKIP_TYPES = frozenset(
    {JavaNodeType.MODIFIERS, JavaNodeType.MARKER_ANNOTATION, JavaNodeType.ANNOTATION}
)


def _lower_class_body(
    ctx: TreeSitterEmitContext, node: Any
) -> list:  # Any: tree-sitter node — untyped at Python boundary
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
    if child.type == JavaNodeType.METHOD_DECLARATION:
        lower_method_decl(ctx, child, inject_this=not _has_static_modifier(child))
    elif child.type == JavaNodeType.CONSTRUCTOR_DECLARATION:
        _lower_constructor_decl(ctx, child)
    elif child.type == JavaNodeType.FIELD_DECLARATION:
        _lower_field_decl(ctx, child)
    elif child.type == JavaNodeType.STATIC_INITIALIZER:
        _lower_static_initializer(ctx, child)
    else:
        ctx.lower_stmt(child)


def _extract_java_parents(
    ctx: TreeSitterEmitContext, node: Any
) -> list[str]:  # Any: tree-sitter node — untyped at Python boundary
    """Extract parent class and interface names from a Java class_declaration node."""
    parents: list[str] = []
    superclass_node = next(
        (c for c in node.children if c.type == JavaNodeType.SUPERCLASS), None
    )
    if superclass_node:
        parent_id = next(
            (
                c
                for c in superclass_node.children
                if c.type == JavaNodeType.TYPE_IDENTIFIER
            ),
            None,
        )
        if parent_id:
            parents.append(ctx.node_text(parent_id))
    # Extract interfaces from super_interfaces clause
    interfaces_node = next(
        (c for c in node.children if c.type == JavaNodeType.SUPER_INTERFACES), None
    )
    if interfaces_node:
        type_list = next(
            (c for c in interfaces_node.children if c.type == JavaNodeType.TYPE_LIST),
            None,
        )
        if type_list:
            interface_names = [
                ctx.node_text(c)
                for c in type_list.children
                if c.type == JavaNodeType.TYPE_IDENTIFIER
            ]
            parents.extend(interface_names)
    return parents


def _extract_java_interfaces(
    ctx: TreeSitterEmitContext, node: Any
) -> list[str]:  # Any: tree-sitter node — untyped at Python boundary
    """Extract interface names from super_interfaces clause."""
    interfaces_node = next(
        (c for c in node.children if c.type == JavaNodeType.SUPER_INTERFACES), None
    )
    if not interfaces_node:
        return []
    type_list = next(
        (c for c in interfaces_node.children if c.type == JavaNodeType.TYPE_LIST),
        None,
    )
    if not type_list:
        return []
    return [
        ctx.node_text(c)
        for c in type_list.children
        if c.type == JavaNodeType.TYPE_IDENTIFIER
    ]


def lower_class_def(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_java_parents(ctx, node)
    # Seed interface implementations
    for iface in _extract_java_interfaces(ctx, node):
        ctx.seed_interface_impl(class_name, iface)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))
    deferred = _lower_class_body(ctx, body_node) if body_node else []
    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(class_name), value_reg=cls_reg))

    saved_class = ctx._current_class_name
    ctx._current_class_name = class_name

    # Collect field initializers from non-static field declarations
    field_inits: list[FieldInit] = [
        init
        for child in deferred
        if child.type == JavaNodeType.FIELD_DECLARATION
        and not _has_static_modifier(child)
        for init in _collect_field_inits(ctx, child)
    ]
    has_constructor = any(
        child.type == JavaNodeType.CONSTRUCTOR_DECLARATION for child in deferred
    )

    for child in deferred:
        if child.type == JavaNodeType.FIELD_DECLARATION and not _has_static_modifier(
            child
        ):
            continue  # Instance field — already collected for __init__
        elif child.type == JavaNodeType.CONSTRUCTOR_DECLARATION:
            _lower_constructor_decl(ctx, child, field_inits=field_inits)
        else:
            _lower_deferred_class_child(ctx, child)

    if not has_constructor and field_inits:
        emit_synthetic_init(ctx, field_inits)

    ctx._current_class_name = saved_class


def lower_record_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower record_declaration with primary constructor from record header params.

    Java records automatically generate an ``__init__`` from their header
    parameters (e.g. ``record Point(int x, int y)``).  A compact constructor
    (``Point { validate(x); }``) is a body that runs inside the generated
    ``__init__`` before the implicit field assignments.
    """
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    record_name = ctx.node_text(name_node) if name_node else "__anon_record"

    # Extract record header params: record Point(int x, int y) → ["x", "y"]
    record_params = _extract_record_params(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{record_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{record_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))
    deferred = _lower_class_body(ctx, body_node) if body_node else []
    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(record_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(record_name), value_reg=cls_reg))

    saved_class = ctx._current_class_name
    ctx._current_class_name = record_name

    field_inits_rec: list[FieldInit] = [
        init
        for child in deferred
        if child.type == JavaNodeType.FIELD_DECLARATION
        and not _has_static_modifier(child)
        for init in _collect_field_inits(ctx, child)
    ]
    has_constructor = any(
        child.type == JavaNodeType.CONSTRUCTOR_DECLARATION for child in deferred
    )

    # Find compact constructor body (if any)
    compact_body = next(
        (
            child.child_by_field_name(ctx.constants.func_body_field)
            for child in deferred
            if child.type == JavaNodeType.COMPACT_CONSTRUCTOR_DECLARATION
        ),
        None,
    )

    for child in deferred:
        if child.type == JavaNodeType.FIELD_DECLARATION and not _has_static_modifier(
            child
        ):
            continue
        elif child.type == JavaNodeType.CONSTRUCTOR_DECLARATION:
            _lower_constructor_decl(ctx, child, field_inits=field_inits_rec)
        elif child.type == JavaNodeType.COMPACT_CONSTRUCTOR_DECLARATION:
            continue  # Handled via _emit_record_init below
        else:
            _lower_deferred_class_child(ctx, child)

    if record_params and not has_constructor:
        _emit_record_init(ctx, record_params, field_inits_rec, compact_body)
    elif not has_constructor and field_inits_rec:
        emit_synthetic_init(ctx, field_inits_rec)

    ctx._current_class_name = saved_class


def _extract_record_params(
    ctx: TreeSitterEmitContext, node: Any
) -> list[str]:  # Any: tree-sitter node — untyped at Python boundary
    """Extract parameter names from a record header: record Foo(int x, int y) → ["x", "y"]."""
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node is None:
        return []
    return [
        ctx.node_text(param.child_by_field_name(ctx.constants.func_name_field))
        for param in params_node.children
        if param.type == JavaNodeType.FORMAL_PARAMETER
        and param.child_by_field_name(ctx.constants.func_name_field) is not None
    ]


def _emit_record_init(
    ctx: TreeSitterEmitContext,
    param_names: list[str],
    field_inits: list[FieldInit] = [],
    compact_body=None,
) -> None:
    """Emit __init__ for a Java record: params → fields, with optional compact constructor body."""
    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))
    ctx.reset_method_scope()

    _emit_this_param(ctx)

    # Declare record header params
    for name in param_names:
        param_reg = ctx.fresh_reg()
        ctx.emit_inst(Symbolic(result_reg=param_reg, hint=f"param:{name}"))
        ctx.emit_inst(DeclVar(name=VarName(name), value_reg=param_reg))

    # Compact constructor body runs before field assignments (validation etc.)
    if compact_body:
        ctx.lower_block(compact_body)

    # Prepend field initializers
    emit_field_initializers(ctx, field_inits)

    # Store record params as fields on this
    for name in param_names:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=val_reg, name=VarName(name)))
        this_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=this_reg, name=VarName("this")))
        ctx.emit_inst(
            StoreField(obj_reg=this_reg, field_name=FieldName(name), value_reg=val_reg)
        )

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def _lower_constructor_decl(
    ctx: TreeSitterEmitContext, node, field_inits: list[FieldInit] = []
) -> None:
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))
    ctx.reset_method_scope()

    _emit_this_param(ctx)

    if params_node:
        lower_java_params(ctx, params_node)

    # Prepend field initializers before the constructor body
    emit_field_initializers(ctx, field_inits)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def _lower_field_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a (static) field declaration as STORE_VAR — used for static fields."""
    lower_local_var_decl(ctx, node)


def _collect_field_inits(
    ctx: TreeSitterEmitContext, node: Any
) -> list[FieldInit]:  # Any: tree-sitter node — untyped at Python boundary
    """Collect (field_name, value_node) pairs from a field_declaration.

    Does NOT emit any IR — callers must pass the result to
    ``emit_field_initializers`` or ``emit_synthetic_init``.
    Also seeds var types for type inference.
    """
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    inits: list[FieldInit] = []
    for child in node.children:
        if child.type == JavaNodeType.VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                field_name = ctx.node_text(name_node)
                ctx.seed_var_type(field_name, type_hint)
                inits.append((field_name, value_node))
    return inits


def _lower_static_initializer(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower static { ... } — find the block child and lower it."""
    block_node = next(
        (c for c in node.children if c.type == JavaNodeType.BLOCK),
        None,
    )
    if block_node:
        ctx.lower_block(block_node)


def lower_interface_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
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

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))
    deferred = _lower_class_body(ctx, body_node) if body_node else []
    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(iface_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(iface_name), value_reg=cls_reg))

    saved_class = ctx._current_class_name
    ctx._current_class_name = iface_name
    for child in deferred:
        _lower_deferred_class_child(ctx, child)
    ctx._current_class_name = saved_class


def lower_enum_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower enum_declaration as NEW_OBJECT with STORE_INDEX per member."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if name_node:
        enum_name = ctx.node_text(name_node)
        obj_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewObject(result_reg=obj_reg, type_hint=EnumType(enum_name)),
            node=node,
        )
        if body_node:
            for i, child in enumerate(
                c for c in body_node.children if c.type == JavaNodeType.ENUM_CONSTANT
            ):
                member_name_node = child.child_by_field_name("name")
                member_name = (
                    ctx.node_text(member_name_node)
                    if member_name_node
                    else ctx.node_text(child)
                )
                key_reg = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=key_reg, value=member_name))
                val_reg = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=val_reg, value=str(i)))
                ctx.emit_inst(
                    StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
                )
        ctx.emit_inst(DeclVar(name=VarName(enum_name), value_reg=obj_reg))


def lower_annotation_type_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower @interface Name { ... } like interface declaration."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    if not name_node:
        return
    annot_name = ctx.node_text(name_node)
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=AnnotationType(annot_name)),
        node=node,
    )
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if body_node:
        for i, child in enumerate(c for c in body_node.children if c.is_named):
            member_name_node = child.child_by_field_name("name")
            member_name = (
                ctx.node_text(member_name_node)
                if member_name_node
                else ctx.node_text(child)[:40]
            )
            key_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=key_reg, value=member_name))
            val_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=val_reg, value=str(i)))
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
            )
    ctx.emit_inst(DeclVar(name=VarName(annot_name), value_reg=obj_reg))


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------
from interpreter.frontends.symbol_table import (
    ClassInfo,
    FieldInfo,
    FunctionInfo,
    SymbolTable,
)
from interpreter.class_name import ClassName
from interpreter.func_name import FuncName


def _is_java_static(node) -> bool:
    """Return True if the node has a modifiers child containing 'static'."""
    modifiers = next(
        (c for c in node.children if c.type == JavaNodeType.MODIFIERS),
        None,
    )
    if modifiers is None:
        return False
    return any(c.type == JavaNodeType.STATIC for c in modifiers.children)


def _extract_java_field_type(node) -> str:
    """Extract type hint text from a Java field_declaration node."""
    type_child = next(
        (
            c
            for c in node.children
            if c.type
            not in (";", ",", JavaNodeType.MODIFIERS, JavaNodeType.VARIABLE_DECLARATOR)
            and c.is_named
        ),
        None,
    )
    return type_child.text.decode() if type_child else ""


def _extract_java_field(node) -> tuple[str, FieldInfo] | None:
    """Extract a FieldInfo from a Java field_declaration node."""
    declarator = next(
        (c for c in node.children if c.type == JavaNodeType.VARIABLE_DECLARATOR),
        None,
    )
    if declarator is None:
        return None
    name_node = declarator.child_by_field_name("name")
    if name_node is None:
        return None
    name = name_node.text.decode()
    type_hint = _extract_java_field_type(node)
    value_node = declarator.child_by_field_name("value")
    has_initializer = value_node is not None
    return name, FieldInfo(
        name=FieldName(name), type_hint=type_hint, has_initializer=has_initializer
    )


def _extract_java_method(node) -> tuple[str, FunctionInfo] | None:
    """Extract a FunctionInfo from a Java method_declaration node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = name_node.text.decode()
    params_node = node.child_by_field_name("parameters")
    params = (
        tuple(
            p.child_by_field_name("name").text.decode()
            for p in params_node.children
            if p.type == JavaNodeType.FORMAL_PARAMETER
            and p.child_by_field_name("name") is not None
        )
        if params_node is not None
        else ()
    )
    type_node = node.child_by_field_name("type")
    return_type = type_node.text.decode() if type_node else ""
    return name, FunctionInfo(
        name=FuncName(name), params=params, return_type=return_type
    )


def _extract_java_class_parents(node) -> tuple[str, ...]:
    """Extract parent class name from a Java class_declaration's superclass node."""
    superclass = next(
        (c for c in node.children if c.type == JavaNodeType.SUPERCLASS),
        None,
    )
    if superclass is None:
        return ()
    type_id = next(
        (c for c in superclass.children if c.type == JavaNodeType.TYPE_IDENTIFIER),
        None,
    )
    if type_id is None:
        return ()
    return (ClassName(type_id.text.decode()),)


def _extract_java_class(node) -> tuple[str, ClassInfo] | None:
    """Extract a ClassInfo from a Java class_declaration node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    class_name = name_node.text.decode()
    parents = _extract_java_class_parents(node)

    body = next(
        (c for c in node.children if c.type == "class_body"),
        None,
    )
    if body is None:
        return class_name, ClassInfo(
            name=ClassName(class_name),
            fields={},
            methods={},
            constants={},
            parents=parents,
        )

    fields: dict[FieldName, FieldInfo] = {}
    constants_map: dict[str, str] = {}
    methods: dict[FuncName, FunctionInfo] = {}

    for child in body.children:
        if child.type == JavaNodeType.FIELD_DECLARATION:
            result = _extract_java_field(child)
            if result is None:
                continue
            fname, finfo = result
            if _is_java_static(child):
                constants_map[fname] = finfo.type_hint
            else:
                fields[FieldName(fname)] = finfo
        elif child.type == JavaNodeType.METHOD_DECLARATION:
            result = _extract_java_method(child)
            if result is None:
                continue
            mname, minfo = result
            methods[FuncName(mname)] = minfo

    return class_name, ClassInfo(
        name=ClassName(class_name),
        fields=fields,
        methods=methods,
        constants=constants_map,
        parents=parents,
    )


def _collect_java_classes(node, accumulator: dict[ClassName, ClassInfo]) -> None:
    """Recursively walk the AST and collect all class_declaration nodes."""
    if node.type == JavaNodeType.CLASS_DECLARATION:
        result = _extract_java_class(node)
        if result is not None:
            class_name, class_info = result
            accumulator[ClassName(class_name)] = class_info
    for child in node.children:
        _collect_java_classes(child, accumulator)


def extract_java_symbols(root) -> SymbolTable:
    """Walk the Java AST and return a SymbolTable of all class definitions."""
    classes: dict[ClassName, ClassInfo] = {}
    _collect_java_classes(root, classes)
    return SymbolTable(classes=classes)
