"""PHP-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.instructions import (
    Branch,
    Const,
    DeclVar,
    Label_,
    LoadVar,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter import constants
from interpreter.frontends.php.control_flow import lower_php_compound
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.php.node_types import PHPNodeType
from interpreter.frontends.common.declarations import (
    FieldInit,
    emit_field_initializers,
)
from interpreter.types.type_expr import ScalarType


def lower_php_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower PHP function parameters."""
    param_index = 0
    for child in params_node.children:
        if child.type in (
            PHPNodeType.OPEN_PAREN,
            PHPNodeType.CLOSE_PAREN,
            PHPNodeType.COMMA,
        ):
            continue
        if child.type == PHPNodeType.SIMPLE_PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Symbolic(result_reg=reg, hint=f"{constants.PARAM_PREFIX}{pname}"),
                    node=child,
                )
                ctx.seed_register_type(reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
                ctx.seed_var_type(pname, type_hint)
                default_value_node = child.child_by_field_name("default_value")
                if default_value_node:
                    from interpreter.frontends.common.default_params import (
                        emit_default_param_guard,
                    )

                    emit_default_param_guard(
                        ctx, pname, param_index, default_value_node
                    )
        elif child.type == PHPNodeType.VARIADIC_PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Symbolic(result_reg=reg, hint=f"{constants.PARAM_PREFIX}{pname}"),
                    node=child,
                )
                ctx.seed_register_type(reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
                ctx.seed_var_type(pname, type_hint)
        elif child.type == PHPNodeType.VARIABLE_NAME:
            pname = ctx.node_text(child)
            ctx.emit_inst(
                Symbolic(
                    result_reg=ctx.fresh_reg(), hint=f"{constants.PARAM_PREFIX}{pname}"
                ),
                node=child,
            )
            ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
        param_index += 1


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:$this`` + ``STORE_VAR $this`` for instance methods."""
    param_reg = ctx.fresh_reg()
    class_type = ScalarType(ctx._current_class_name)
    ctx.emit_inst(Symbolic(result_reg=param_reg, hint=f"{constants.PARAM_PREFIX}$this"))
    ctx.seed_register_type(param_reg, class_type)
    ctx.seed_param_type(constants.PARAM_PHP_THIS, class_type)
    ctx.emit_inst(DeclVar(name=constants.PARAM_PHP_THIS, value_reg=param_reg))
    ctx.seed_var_type(constants.PARAM_PHP_THIS, class_type)


def _has_static_modifier(node) -> bool:
    """Return True if *node* has a ``static_modifier`` child."""
    return any(c.type == PHPNodeType.STATIC_MODIFIER for c in node.children)


def lower_php_func_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function definition."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        lower_php_params(ctx, params_node)

    if body_node:
        lower_php_compound(ctx, body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=func_reg))


def lower_php_method_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower method declaration inside a class."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    if not _has_static_modifier(node):
        _emit_this_param(ctx)

    if params_node:
        lower_php_params(ctx, params_node)

    if body_node:
        lower_php_compound(ctx, body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=func_reg))


def _lower_php_class_body(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declaration_list body of a PHP class."""
    for child in node.children:
        if child.type == PHPNodeType.METHOD_DECLARATION:
            lower_php_method_decl(ctx, child)
        elif child.type == PHPNodeType.PROPERTY_DECLARATION:
            lower_php_property_declaration(ctx, child)
        elif child.is_named and child.type not in (
            PHPNodeType.VISIBILITY_MODIFIER,
            PHPNodeType.STATIC_MODIFIER,
            PHPNodeType.ABSTRACT_MODIFIER,
            PHPNodeType.FINAL_MODIFIER,
            PHPNodeType.OPEN_BRACE,
            PHPNodeType.CLOSE_BRACE,
        ):
            ctx.lower_stmt(child)


def _extract_php_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class name from a PHP class declaration."""
    base_clause = next(
        (c for c in node.children if c.type == PHPNodeType.BASE_CLAUSE), None
    )
    if base_clause is None:
        return []
    return [
        ctx.node_text(c) for c in base_clause.children if c.type == PHPNodeType.NAME
    ]


def _is_php_constructor(ctx: TreeSitterEmitContext, child) -> bool:
    """Return True if *child* is a method named __construct."""
    if child.type != PHPNodeType.METHOD_DECLARATION:
        return False
    name_node = child.child_by_field_name(ctx.constants.func_name_field)
    return name_node is not None and ctx.node_text(name_node) == "__construct"


def _emit_php_synthetic_constructor(
    ctx: TreeSitterEmitContext, field_inits: list[FieldInit]
) -> None:
    """Generate a synthetic __construct that sets up $this and initializes fields.

    Unlike the generic ``emit_synthetic_init``, this emits ``_emit_this_param``
    so that ``$this`` is available when ``emit_field_initializers`` runs.
    """
    func_name = "__construct"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    _emit_this_param(ctx)
    emit_field_initializers(ctx, field_inits, this_var=constants.PARAM_PHP_THIS)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=func_reg))


def lower_php_class(ctx: TreeSitterEmitContext, node) -> None:
    """Lower class declaration."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_php_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    # Collect field initializers from non-static property declarations
    field_inits: list[FieldInit] = []
    if body_node:
        field_inits = [
            init
            for child in body_node.children
            if child.type == PHPNodeType.PROPERTY_DECLARATION
            and not _has_static_modifier(child)
            for init in _collect_php_field_inits(ctx, child)
        ]

    has_constructor = body_node is not None and any(
        _is_php_constructor(ctx, child) for child in body_node.children
    )

    if body_node:
        saved_class = ctx._current_class_name
        ctx._current_class_name = class_name
        for child in body_node.children:
            if child.type == PHPNodeType.METHOD_DECLARATION:
                if _is_php_constructor(ctx, child):
                    _lower_php_constructor_with_field_inits(ctx, child, field_inits)
                else:
                    lower_php_method_decl(ctx, child)
            elif (
                child.type == PHPNodeType.PROPERTY_DECLARATION
                and not _has_static_modifier(child)
                and _collect_php_field_inits(ctx, child)
            ):
                continue  # Instance field with init — handled via constructor
            elif child.type == PHPNodeType.PROPERTY_DECLARATION:
                lower_php_property_declaration(ctx, child)
            elif child.is_named and child.type not in (
                PHPNodeType.VISIBILITY_MODIFIER,
                PHPNodeType.STATIC_MODIFIER,
                PHPNodeType.ABSTRACT_MODIFIER,
                PHPNodeType.FINAL_MODIFIER,
                PHPNodeType.OPEN_BRACE,
                PHPNodeType.CLOSE_BRACE,
            ):
                ctx.lower_stmt(child)
        ctx._current_class_name = saved_class

    if not has_constructor and field_inits:
        _emit_php_synthetic_constructor(ctx, field_inits)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=class_name, value_reg=cls_reg))


def lower_php_interface(ctx: TreeSitterEmitContext, node) -> None:
    """Lower interface_declaration like a class: BRANCH, LABEL, body, end."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    iface_name = ctx.node_text(name_node) if name_node else "__anon_interface"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{iface_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{iface_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    if body_node:
        _lower_php_class_body(ctx, body_node)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(iface_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=iface_name, value_reg=cls_reg))


def lower_php_trait(ctx: TreeSitterEmitContext, node) -> None:
    """Lower trait_declaration like a class: BRANCH, LABEL, body, end."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    trait_name = ctx.node_text(name_node) if name_node else "__anon_trait"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    if body_node:
        _lower_php_class_body(ctx, body_node)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(trait_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=trait_name, value_reg=cls_reg))


def lower_php_function_static(ctx: TreeSitterEmitContext, node) -> None:
    """Lower static $x = val; declarations inside functions."""
    for child in node.children:
        if child.type == PHPNodeType.STATIC_VARIABLE_DECLARATION:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                val_reg = ctx.lower_expr(value_node)
                ctx.emit_inst(
                    DeclVar(name=ctx.node_text(name_node), value_reg=val_reg),
                    node=child,
                )
            elif name_node:
                val_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Const(result_reg=val_reg, value=ctx.constants.none_literal)
                )
                ctx.emit_inst(
                    DeclVar(name=ctx.node_text(name_node), value_reg=val_reg),
                    node=child,
                )


def lower_php_enum(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_declaration like a class: BRANCH, LABEL, body, end."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    enum_name = ctx.node_text(name_node) if name_node else "__anon_enum"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{enum_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{enum_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    if body_node:
        _lower_php_class_body(ctx, body_node)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(enum_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=enum_name, value_reg=cls_reg))


def _lower_php_constructor_with_field_inits(
    ctx: TreeSitterEmitContext, node, field_inits: list[FieldInit] = []
) -> None:
    """Lower __construct method, prepending field initializers before body."""
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = "__construct"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if not _has_static_modifier(node):
        _emit_this_param(ctx)

    if params_node:
        lower_php_params(ctx, params_node)

    # Prepend field initializers before the constructor body
    emit_field_initializers(ctx, field_inits, this_var=constants.PARAM_PHP_THIS)

    if body_node:
        lower_php_compound(ctx, body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=func_reg))


def _collect_php_field_inits(ctx: TreeSitterEmitContext, node) -> list[FieldInit]:
    """Collect (field_name, value_node) pairs from a PHP property_declaration.

    Does NOT emit any IR — callers pass the result to
    ``emit_field_initializers`` or ``emit_synthetic_init``.
    """
    inits: list[FieldInit] = []
    for child in node.children:
        if child.type == PHPNodeType.PROPERTY_ELEMENT:
            name_node = next(
                (c for c in child.children if c.type == PHPNodeType.VARIABLE_NAME),
                None,
            )
            value_node = next(
                (
                    c
                    for c in child.children
                    if c.is_named and c.type != PHPNodeType.VARIABLE_NAME
                ),
                None,
            )
            if name_node and value_node:
                # Strip leading $ from PHP variable names to match field access syntax
                field_name = ctx.node_text(name_node).lstrip("$")
                inits.append((field_name, value_node))
    return inits


def lower_php_property_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower property declarations inside classes, e.g. public $x = 10;

    Emits LOAD_VAR $this + STORE_FIELD for each property element.
    Used for properties lowered inline (e.g. static properties).
    Instance properties with initializers should use _collect_php_field_inits instead.
    """
    for child in node.children:
        if child.type == PHPNodeType.PROPERTY_ELEMENT:
            name_node = next(
                (c for c in child.children if c.type == PHPNodeType.VARIABLE_NAME), None
            )
            value_node = next(
                (
                    c
                    for c in child.children
                    if c.is_named and c.type != PHPNodeType.VARIABLE_NAME
                ),
                None,
            )
            if name_node:
                this_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    LoadVar(result_reg=this_reg, name=constants.PARAM_PHP_THIS)
                )
                if value_node:
                    val_reg = ctx.lower_expr(value_node)
                else:
                    val_reg = ctx.fresh_reg()
                    ctx.emit_inst(
                        Const(result_reg=val_reg, value=ctx.constants.none_literal)
                    )
                field_name = ctx.node_text(name_node).lstrip("$")
                ctx.emit_inst(
                    StoreField(
                        obj_reg=this_reg, field_name=field_name, value_reg=val_reg
                    ),
                    node=node,
                )


def lower_php_use_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``use SomeTrait;`` inside classes -- no-op / SYMBOLIC."""
    named = [c for c in node.children if c.is_named]
    trait_names = [ctx.node_text(c) for c in named]
    for trait_name in trait_names:
        ctx.emit_inst(
            Symbolic(result_reg=ctx.fresh_reg(), hint=f"use_trait:{trait_name}"),
            node=node,
        )


def lower_php_namespace_use_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``use Some\\Namespace;`` -- no-op."""
    pass


def lower_php_enum_case(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum case inside an enum_declaration as STORE_FIELD."""
    name_node = node.child_by_field_name("name")
    value_node = next(
        (c for c in node.children if c.is_named and c.type not in (PHPNodeType.NAME,)),
        None,
    )
    if name_node:
        case_name = ctx.node_text(name_node)
        self_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=self_reg, name=constants.PARAM_SELF))
        if value_node:
            val_reg = ctx.lower_expr(value_node)
        else:
            val_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=val_reg, value=case_name))
        ctx.emit_inst(
            StoreField(obj_reg=self_reg, field_name=case_name, value_reg=val_reg),
            node=node,
        )


def lower_php_const_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``const FOO = 1, BAR = 2;`` -- STORE_VAR for each const_element."""
    for child in node.children:
        if child.type == PHPNodeType.CONST_ELEMENT:
            named = [c for c in child.children if c.is_named]
            if len(named) >= 2:
                name_node, value_node = named[0], named[1]
                val_reg = ctx.lower_expr(value_node)
                ctx.emit_inst(
                    DeclVar(name=ctx.node_text(name_node), value_reg=val_reg),
                    node=child,
                )


def lower_php_global_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``global $config;`` -- STORE_VAR for each variable."""
    for child in node.children:
        if child.type == PHPNodeType.VARIABLE_NAME:
            var_name = ctx.node_text(child)
            reg = ctx.fresh_reg()
            ctx.emit_inst(LoadVar(result_reg=reg, name=var_name), node=child)
            ctx.emit_inst(DeclVar(name=var_name, value_reg=reg), node=node)


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_php_method(node) -> "tuple[str, FunctionInfo] | None":
    """Extract a FunctionInfo from a PHP method_declaration node."""
    from interpreter.frontends.symbol_table import FunctionInfo

    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = name_node.text.decode()
    params_node = node.child_by_field_name("parameters")
    params = (
        tuple(
            p.child_by_field_name("name").text.decode().lstrip("$")
            for p in params_node.children
            if p.type in (PHPNodeType.SIMPLE_PARAMETER, PHPNodeType.VARIADIC_PARAMETER)
            and p.child_by_field_name("name") is not None
        )
        if params_node is not None
        else ()
    )
    return name, FunctionInfo(name=name, params=params, return_type="")


def _extract_php_class(node) -> "tuple[str, ClassInfo] | None":
    """Extract a ClassInfo from a PHP class_declaration node."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo

    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    class_name = name_node.text.decode()

    base_clause = next(
        (c for c in node.children if c.type == PHPNodeType.BASE_CLAUSE), None
    )
    parents: tuple[str, ...] = ()
    if base_clause is not None:
        parent_node = next(
            (c for c in base_clause.children if c.type == PHPNodeType.NAME),
            None,
        )
        if parent_node is not None:
            parents = (parent_node.text.decode(),)

    body = node.child_by_field_name("body")
    if body is None:
        return class_name, ClassInfo(
            name=class_name, fields={}, methods={}, constants={}, parents=parents
        )

    fields: dict[str, FieldInfo] = {}
    methods: dict[str, FunctionInfo] = {}
    constants_map: dict[str, str] = {}

    for child in body.children:
        if child.type == PHPNodeType.PROPERTY_DECLARATION:
            is_static = any(
                c.type == "static_modifier"
                or (c.type == "visibility_modifier" and False)
                or c.text == b"static"
                for c in child.children
                if c.type == "static_modifier"
            )
            for sub in child.children:
                if sub.type == PHPNodeType.PROPERTY_ELEMENT:
                    var_node = sub.child_by_field_name("name")
                    if var_node is None:
                        var_node = next(
                            (
                                c
                                for c in sub.children
                                if c.type == PHPNodeType.VARIABLE_NAME
                            ),
                            None,
                        )
                    if var_node is not None:
                        fname = var_node.text.decode().lstrip("$")
                        if is_static:
                            has_init = sub.child_by_field_name("default") is not None
                            val = ""
                            if has_init:
                                default_node = sub.child_by_field_name("default")
                                val = default_node.text.decode() if default_node else ""
                            constants_map[fname] = val
                        else:
                            has_init = sub.child_by_field_name("default") is not None
                            fields[fname] = FieldInfo(
                                name=fname, type_hint="", has_initializer=has_init
                            )
        elif child.type == PHPNodeType.METHOD_DECLARATION:
            result = _extract_php_method(child)
            if result is not None:
                mname, minfo = result
                methods[mname] = minfo
        elif child.type == PHPNodeType.CONST_DECLARATION:
            for sub in child.children:
                if sub.type == PHPNodeType.CONST_ELEMENT:
                    cname_node = sub.child_by_field_name("name")
                    if cname_node is not None:
                        constants_map[cname_node.text.decode()] = ""

    return class_name, ClassInfo(
        name=class_name,
        fields=fields,
        methods=methods,
        constants=constants_map,
        parents=parents,
    )


def _collect_php_classes(node, accumulator: "dict[str, ClassInfo]") -> None:
    """Recursively walk the AST and collect all class_declaration nodes."""
    from interpreter.frontends.symbol_table import ClassInfo

    if node.type == PHPNodeType.CLASS_DECLARATION:
        result = _extract_php_class(node)
        if result is not None:
            class_name, class_info = result
            accumulator[class_name] = class_info
    for child in node.children:
        _collect_php_classes(child, accumulator)


def extract_php_symbols(root) -> "SymbolTable":
    """Walk the PHP AST and return a SymbolTable of all class definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, SymbolTable

    classes: dict[str, ClassInfo] = {}
    _collect_php_classes(root, classes)
    return SymbolTable(classes=classes)
