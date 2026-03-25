"""Pascal-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter import constants
from interpreter.frontends.pascal.pascal_constants import KEYWORD_NOISE
from interpreter.frontends.pascal.control_flow import lower_pascal_block
from interpreter.frontends.type_extraction import (
    normalize_type_hint,
)
from interpreter.frontends.pascal.type_helpers import extract_pascal_return_type
from interpreter.frontends.pascal.node_types import PascalNodeType
from interpreter.frontends.common.property_accessors import (
    register_property_accessor,
    emit_field_store_or_setter,
)
from interpreter.types.type_expr import EnumType, scalar
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    StoreField,
    StoreIndex,
    CallCtorFunction,
    CallFunction,
    CallMethod,
    LoadField,
    NewArray,
    NewObject,
    Symbolic,
    Branch,
    Label_,
    Return_,
)

logger = logging.getLogger(__name__)


def _resolve_object_class(ctx: TreeSitterEmitContext, obj_node) -> str:
    """Resolve the class name of an object node, if known."""
    if obj_node.type == PascalNodeType.IDENTIFIER:
        obj_name = ctx.node_text(obj_node)
        if obj_name == "self":
            return getattr(ctx, "_current_class_name", "")
        pascal_var_types: dict = getattr(ctx, "_pascal_var_types", {})
        return pascal_var_types.get(obj_name, "")
    return ""


def lower_pascal_assignment(ctx: TreeSitterEmitContext, node) -> None:
    """Lower assignment -- children: target, kAssign, expression."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) < 2:
        logger.warning(
            "Pascal assignment with fewer than 2 named children at %s",
            ctx.source_loc(node),
        )
        return
    target = named_children[0]
    value = named_children[-1]
    val_reg = ctx.lower_expr(value)
    if target.type == PascalNodeType.EXPR_SUBSCRIPT:
        target_named = [
            c for c in target.children if c.is_named and c.type not in KEYWORD_NOISE
        ]
        if target_named:
            obj_reg = ctx.lower_expr(target_named[0])
            args_node = next(
                (c for c in target.children if c.type == PascalNodeType.EXPR_ARGS), None
            )
            if args_node:
                idx_children = [
                    c
                    for c in args_node.children
                    if c.is_named and c.type not in KEYWORD_NOISE
                ]
                idx_reg = (
                    ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
                )
            else:
                idx_reg = ctx.fresh_reg()
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=node,
            )
        else:
            ctx.emit_inst(
                StoreVar(name=ctx.node_text(target), value_reg=val_reg),
                node=node,
            )
    elif target.type == PascalNodeType.EXPR_DOT:
        dot_named = [
            c for c in target.children if c.is_named and c.type not in KEYWORD_NOISE
        ]
        obj_node = dot_named[0]
        obj_reg = ctx.lower_expr(obj_node)
        field_name = ctx.node_text(dot_named[-1])

        obj_class = _resolve_object_class(ctx, obj_node)
        if obj_class:
            emit_field_store_or_setter(
                ctx, obj_reg, obj_class, field_name, val_reg, node
            )
        else:
            ctx.emit_inst(
                StoreField(obj_reg=obj_reg, field_name=field_name, value_reg=val_reg),
                node=node,
            )
    else:
        target_name = ctx.node_text(target)
        current_function_name = getattr(ctx, "_pascal_current_function_name", "")
        if current_function_name and target_name == current_function_name:
            ctx.emit_inst(Return_(value_reg=val_reg), node=node)
        else:
            ctx.emit_inst(StoreVar(name=target_name, value_reg=val_reg), node=node)


def lower_pascal_decl_vars(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declVars -- contains multiple declVar children."""
    for child in node.children:
        if child.type == PascalNodeType.DECL_VAR:
            lower_pascal_decl_var(ctx, child)


def lower_pascal_decl_var(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declVar -- identifier : type."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    if id_node is None:
        return
    var_name = ctx.node_text(id_node)
    type_node = next((c for c in node.children if c.type == PascalNodeType.TYPE), None)
    array_size, elem_type = _pascal_array_info(ctx, type_node) if type_node else (0, "")
    if array_size > 0:
        size_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=size_reg, value=str(array_size)))
        arr_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewArray(result_reg=arr_reg, type_hint=scalar("array"), size_reg=size_reg),
            node=node,
        )
        record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
        if elem_type in record_types:
            _populate_array_with_records(ctx, arr_reg, array_size, elem_type, node)
        ctx.emit_inst(DeclVar(name=var_name, value_reg=arr_reg), node=node)
    else:
        type_name = _pascal_var_type_name(ctx, type_node) if type_node else ""
        type_hint = normalize_type_hint(type_name.lower(), ctx.type_map)
        val_reg = ctx.fresh_reg()
        record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
        if type_name in record_types:
            ctx.emit_inst(
                CallCtorFunction(
                    result_reg=val_reg,
                    func_name=type_name,
                    type_hint=scalar(type_name),
                    args=(),
                ),
                node=node,
            )
        else:
            ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
        ctx.emit_inst(DeclVar(name=var_name, value_reg=val_reg), node=node)
        ctx.seed_var_type(var_name, type_hint)
        pascal_var_types: dict = getattr(ctx, "_pascal_var_types", {})
        if type_name in record_types:
            pascal_var_types[var_name] = type_name
            ctx._pascal_var_types = pascal_var_types


def _populate_array_with_records(
    ctx: TreeSitterEmitContext,
    arr_reg: str,
    size: int,
    record_type: str,
    node,
) -> None:
    """Pre-populate each slot of *arr_reg* with a fresh record instance."""
    for i in range(size):
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        obj_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(result_reg=obj_reg, func_name=record_type, args=()),
            node=node,
        )
        ctx.emit_inst(
            StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=obj_reg),
            node=node,
        )


def _pascal_array_info(ctx: TreeSitterEmitContext, type_node) -> tuple[int, str]:
    """Extract (size, element_type_name) from a Pascal array type node.

    Returns (0, "") if *type_node* does not contain a ``declArray``.
    """
    decl_array = next(
        (c for c in type_node.children if c.type == PascalNodeType.DECL_ARRAY), None
    )
    if decl_array is None:
        return 0, ""
    range_node = next(
        (c for c in decl_array.children if c.type == PascalNodeType.RANGE), None
    )
    if range_node is None:
        return 0, ""
    nums = [c for c in range_node.children if c.type == PascalNodeType.LITERAL_NUMBER]
    if len(nums) < 2:
        return 0, ""
    try:
        lo = int(ctx.node_text(nums[0]))
        hi = int(ctx.node_text(nums[1]))
        size = hi - lo + 1
    except ValueError:
        return 0, ""
    elem_type_node = next(
        (c for c in decl_array.children if c.type == PascalNodeType.TYPE), None
    )
    elem_type_name = (
        _pascal_var_type_name(ctx, elem_type_node) if elem_type_node else ""
    )
    return size, elem_type_name


def _pascal_var_type_name(ctx: TreeSitterEmitContext, type_node) -> str:
    """Extract the type name from a Pascal type node (type > typeref > identifier)."""
    typeref = next(
        (c for c in type_node.children if c.type == PascalNodeType.TYPEREF), None
    )
    if typeref is None:
        return ""
    id_node = next(
        (c for c in typeref.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    return ctx.node_text(id_node) if id_node else ""


def lower_pascal_proc(ctx: TreeSitterEmitContext, node) -> None:
    """Lower defProc/declProc -- contains kFunction/kProcedure, identifier, declArgs, type, block."""
    decl_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_PROC), None
    )
    search_node = decl_node if decl_node else node

    # Detect qualified name (genericDot): procedure TFoo.SetName(...)
    generic_dot = next(
        (c for c in search_node.children if c.type == PascalNodeType.GENERIC_DOT), None
    )
    if generic_dot:
        dot_ids = [
            c for c in generic_dot.children if c.type == PascalNodeType.IDENTIFIER
        ]
        class_name = ctx.node_text(dot_ids[0])
        func_name = ctx.node_text(dot_ids[1])
    else:
        class_name = ""
        id_node = next(
            (c for c in search_node.children if c.type == PascalNodeType.IDENTIFIER),
            None,
        )
        func_name = ctx.node_text(id_node) if id_node else "__anon"

    args_node = next(
        (c for c in search_node.children if c.type == PascalNodeType.DECL_ARGS), None
    )
    body_node = next((c for c in node.children if c.type == PascalNodeType.BLOCK), None)

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_pascal_return_type(ctx, search_node)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    # Inject this + self for qualified methods
    if class_name:
        sym_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}this"),
            node=node,
        )
        ctx.emit_inst(DeclVar(name="this", value_reg=f"%{ctx.reg_counter - 1}"))
        ctx.emit_inst(DeclVar(name="self", value_reg=f"%{ctx.reg_counter - 1}"))

    if args_node:
        _lower_pascal_params(ctx, args_node)

    prev_func_name = getattr(ctx, "_pascal_current_function_name", "")
    ctx._pascal_current_function_name = func_name
    prev_class_name = getattr(ctx, "_current_class_name", "")
    if class_name:
        ctx._current_class_name = class_name
    for child in node.children:
        if child.type == PascalNodeType.DEF_PROC:
            lower_pascal_proc(ctx, child)
    if body_node:
        lower_pascal_block(ctx, body_node)
    ctx._pascal_current_function_name = prev_func_name
    ctx._current_class_name = prev_class_name

    # Pascal functions return via the 'Result' variable. Procedures return None.
    is_function = any(c.type == PascalNodeType.K_FUNCTION for c in search_node.children)
    if is_function:
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=result_reg, name="Result"))
        ctx.emit_inst(Return_(value_reg=result_reg))
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=none_reg, value=ctx.constants.default_return_value)
        )
        ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=func_reg))


def _lower_pascal_params(ctx: TreeSitterEmitContext, args_node) -> None:
    """Lower declArgs -- contains declArg children with identifier and typeref."""
    param_index = 0
    for child in args_node.children:
        if child.type in KEYWORD_NOISE:
            continue
        if child.type == PascalNodeType.DECL_ARG:
            param_index = _lower_pascal_single_param(ctx, child, param_index)
        elif child.type == PascalNodeType.IDENTIFIER:
            pname = ctx.node_text(child)
            ctx.emit_inst(
                Symbolic(
                    result_reg=ctx.fresh_reg(),
                    hint=f"{constants.PARAM_PREFIX}{pname}",
                ),
                node=child,
            )
            ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
            param_index += 1


def _lower_pascal_single_param(
    ctx: TreeSitterEmitContext, child, param_index: int
) -> int:
    """Lower a single declArg -- extract all identifier names."""
    type_name = _pascal_var_type_name(
        ctx, next((c for c in child.children if c.type == PascalNodeType.TYPE), None)
    )
    type_hint = normalize_type_hint(type_name.lower(), ctx.type_map)
    # Extract default value if present (defaultValue > kEq, value_expr)
    default_node = next((c for c in child.children if c.type == "defaultValue"), None)
    default_value_node = (
        next((c for c in default_node.children if c.type != "kEq"), None)
        if default_node
        else None
    )
    for id_node in child.children:
        if id_node.type != PascalNodeType.IDENTIFIER:
            continue
        pname = ctx.node_text(id_node)
        _sym_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Symbolic(result_reg=_sym_reg, hint=f"{constants.PARAM_PREFIX}{pname}"),
            node=child,
        )
        ctx.seed_register_type(_sym_reg, type_hint)
        ctx.seed_param_type(pname, type_hint)
        ctx.emit_inst(DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"))
        ctx.seed_var_type(pname, type_hint)
        if default_value_node:
            from interpreter.frontends.common.default_params import (
                emit_default_param_guard,
            )

            emit_default_param_guard(ctx, pname, param_index, default_value_node)
        record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
        pascal_var_types: dict = getattr(ctx, "_pascal_var_types", {})
        if type_name in record_types:
            pascal_var_types[pname] = type_name
            ctx._pascal_var_types = pascal_var_types
        param_index += 1
    return param_index


def lower_pascal_decl_consts(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declConsts -- iterate declConst children."""
    for child in node.children:
        if child.type == PascalNodeType.DECL_CONST:
            lower_pascal_decl_const(ctx, child)


def lower_pascal_decl_const(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declConst -- extract name + defaultValue child, lower value, DECL_VAR."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    if id_node is None:
        return
    var_name = ctx.node_text(id_node)
    value_node = next(
        (c for c in node.children if c.type == PascalNodeType.DEFAULT_VALUE), None
    )
    if value_node:
        # defaultValue wraps the actual expression
        inner = next(
            (
                c
                for c in value_node.children
                if c.is_named and c.type not in KEYWORD_NOISE
            ),
            None,
        )
        val_reg = ctx.lower_expr(inner) if inner else ctx.fresh_reg()
        if inner is None:
            ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
    ctx.emit_inst(DeclVar(name=var_name, value_reg=val_reg), node=node)


def lower_pascal_decl_types(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declTypes -- iterate individual declType children."""
    for child in node.children:
        if child.type == PascalNodeType.DECL_TYPE:
            lower_pascal_decl_type(ctx, child)


def lower_pascal_decl_type(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declType -- emit CLASS_REF for class/record types with body traversal."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    class_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_CLASS), None
    )

    if id_node is None:
        return

    type_name = ctx.node_text(id_node)

    # Enum type: type TColor = (Red, Green, Blue)
    type_wrapper = next((c for c in node.children if c.type == "type"), None)
    enum_node = (
        next(
            (c for c in type_wrapper.children if c.type == PascalNodeType.DECL_ENUM),
            None,
        )
        if type_wrapper
        else None
    )

    if enum_node is not None:
        _lower_pascal_enum(ctx, type_name, enum_node, node)
        return

    if class_node is None:
        return
    record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
    record_types.add(type_name)
    ctx._pascal_record_types = record_types
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    prev_class_name = getattr(ctx, "_current_class_name", "")
    ctx._current_class_name = type_name

    # First pass: collect all field names across all declSection children
    field_names = _collect_class_field_names(ctx, class_node)

    # Second pass: emit synthetic __init__, methods, and properties
    _emit_synthetic_init_for_fields(ctx, field_names)

    for section in class_node.children:
        if section.type == PascalNodeType.DECL_SECTION:
            _lower_pascal_class_section(ctx, section, type_name, field_names)

    ctx._current_class_name = prev_class_name

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(type_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=type_name, value_reg=cls_reg))


def _collect_class_field_names(ctx: TreeSitterEmitContext, class_node) -> list[str]:
    """Collect all field names from declField nodes across all declSection children."""
    return [
        ctx.node_text(id_node)
        for section in class_node.children
        if section.type == PascalNodeType.DECL_SECTION
        for child in section.children
        if child.type == PascalNodeType.DECL_FIELD
        for id_node in child.children
        if id_node.type == PascalNodeType.IDENTIFIER
    ]


def _emit_synthetic_init_for_fields(
    ctx: TreeSitterEmitContext, field_names: list[str]
) -> None:
    """Emit a synthetic __init__ that stores None for each field."""
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}__init__")
    end_label = ctx.fresh_label("end___init__")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    sym_reg = ctx.fresh_reg()
    ctx.emit_inst(Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}this"))
    ctx.emit_inst(DeclVar(name="this", value_reg=f"%{ctx.reg_counter - 1}"))

    for fname in field_names:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
        this_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=this_reg, name="this"))
        ctx.emit_inst(StoreField(obj_reg=this_reg, field_name=fname, value_reg=val_reg))

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref("__init__", func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name="__init__", value_reg=func_reg))


def _lower_pascal_class_section(
    ctx: TreeSitterEmitContext,
    section,
    class_name: str,
    field_names: list[str],
) -> None:
    """Lower children of a declSection (declField, declProc, declProp)."""
    for child in section.children:
        if child.type == PascalNodeType.DECL_PROC:
            _lower_pascal_method(ctx, child)
        elif child.type == PascalNodeType.DECL_PROP:
            _lower_pascal_property(ctx, child, class_name, field_names)


def _lower_pascal_method(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a declProc inside a class -- forward declaration with `this` injected."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    args_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_ARGS), None
    )

    func_name = ctx.node_text(id_node) if id_node else "__anon_method"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_pascal_return_type(ctx, node)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    # Inject `this` as first parameter
    sym_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}this"),
        node=node,
    )
    ctx.emit_inst(DeclVar(name="this", value_reg=f"%{ctx.reg_counter - 1}"))

    if args_node:
        _lower_pascal_params(ctx, args_node)

    # Forward declarations have no body -- emit default return
    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    # Do NOT emit func_ref here — forward declarations are placeholders.


def _lower_pascal_property(
    ctx: TreeSitterEmitContext,
    node,
    class_name: str,
    field_names: list[str],
) -> None:
    """Lower declProp -- emit synthetic __get_<prop>__ and/or __set_<prop>__ methods."""
    children = node.children
    prop_name = ""
    read_target = ""
    write_target = ""

    saw_property = False
    saw_read = False
    saw_write = False
    for child in children:
        if child.type == PascalNodeType.K_PROPERTY:
            saw_property = True
        elif child.type == PascalNodeType.K_READ:
            saw_read = True
        elif child.type == PascalNodeType.K_WRITE:
            saw_write = True
        elif child.type == PascalNodeType.IDENTIFIER:
            text = ctx.node_text(child)
            if saw_write:
                write_target = text
                saw_write = False
            elif saw_read:
                read_target = text
                saw_read = False
            elif saw_property and not prop_name:
                prop_name = text

    if not prop_name:
        return

    field_name_set = set(field_names)

    if read_target:
        _emit_property_getter(ctx, class_name, prop_name, read_target, field_name_set)

    if write_target:
        _emit_property_setter(ctx, class_name, prop_name, write_target, field_name_set)


def _emit_property_getter(
    ctx: TreeSitterEmitContext,
    class_name: str,
    prop_name: str,
    target: str,
    field_names: set[str],
) -> None:
    """Emit synthetic __get_<prop>__ method."""
    getter_name = f"__get_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{getter_name}")
    end_label = ctx.fresh_label(f"end_{getter_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    sym_reg = ctx.fresh_reg()
    ctx.emit_inst(Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}this"))
    ctx.emit_inst(DeclVar(name="this", value_reg=f"%{ctx.reg_counter - 1}"))

    this_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=this_reg, name="this"))

    if target in field_names:
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(result_reg=result_reg, obj_reg=this_reg, field_name=target)
        )
    else:
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallMethod(
                result_reg=result_reg,
                obj_reg=this_reg,
                method_name=target,
                args=(),
            )
        )

    ctx.emit_inst(Return_(value_reg=result_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(getter_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=getter_name, value_reg=func_reg))

    register_property_accessor(ctx, class_name, prop_name, "get")


def _emit_property_setter(
    ctx: TreeSitterEmitContext,
    class_name: str,
    prop_name: str,
    target: str,
    field_names: set[str],
) -> None:
    """Emit synthetic __set_<prop>__ method."""
    setter_name = f"__set_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{setter_name}")
    end_label = ctx.fresh_label(f"end_{setter_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    sym_reg = ctx.fresh_reg()
    ctx.emit_inst(Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}this"))
    ctx.emit_inst(DeclVar(name="this", value_reg=f"%{ctx.reg_counter - 1}"))

    val_sym = ctx.fresh_reg()
    ctx.emit_inst(Symbolic(result_reg=val_sym, hint=f"{constants.PARAM_PREFIX}value"))
    ctx.emit_inst(DeclVar(name="value", value_reg=f"%{ctx.reg_counter - 1}"))

    this_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=this_reg, name="this"))
    val_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=val_reg, name="value"))

    if target in field_names:
        ctx.emit_inst(
            StoreField(obj_reg=this_reg, field_name=target, value_reg=val_reg)
        )
    else:
        ctx.emit_inst(
            CallMethod(
                result_reg=ctx.fresh_reg(),
                obj_reg=this_reg,
                method_name=target,
                args=(val_reg,),
            )
        )

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(setter_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=setter_name, value_reg=func_reg))

    register_property_accessor(ctx, class_name, prop_name, "set")


def _lower_pascal_enum(
    ctx: TreeSitterEmitContext,
    type_name: str,
    enum_node,
    parent_node,
) -> None:
    """Lower Pascal enum: NEW_OBJECT + STORE_INDEX per member + DECL_VAR per member."""
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=EnumType(type_name)),
        node=parent_node,
    )
    members = [
        c for c in enum_node.children if c.type == PascalNodeType.DECL_ENUM_VALUE
    ]
    for i, member in enumerate(members):
        member_id = next(
            (c for c in member.children if c.type == PascalNodeType.IDENTIFIER),
            None,
        )
        member_name = ctx.node_text(member_id) if member_id else ctx.node_text(member)
        key_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=key_reg, value=member_name))
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=i))
        ctx.emit_inst(StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg))
        # Declare each member as a top-level variable with ordinal value
        ord_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=ord_reg, value=i))
        ctx.emit_inst(DeclVar(name=member_name, value_reg=ord_reg))
    ctx.emit_inst(DeclVar(name=type_name, value_reg=obj_reg))


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_pascal_class_from_decl_type(node) -> "tuple[str, ClassInfo] | None":
    """Extract a ClassInfo from a Pascal declType node that contains a declClass."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo

    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    class_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_CLASS), None
    )
    if id_node is None or class_node is None:
        return None

    class_name = id_node.text.decode()

    # Extract parent from class definition (first type identifier after kClass)
    parents: tuple[str, ...] = ()
    found_class_kw = False
    for child in class_node.children:
        if child.type == PascalNodeType.K_CLASS:
            found_class_kw = True
        elif found_class_kw and child.type in (PascalNodeType.IDENTIFIER, "typeref"):
            parents = (child.text.decode(),)
            break

    fields: dict[str, FieldInfo] = {}
    methods: dict[str, FunctionInfo] = {}

    # Collect fields/methods from both direct children and declSection children
    members = list(class_node.children)
    for section in class_node.children:
        if section.type == PascalNodeType.DECL_SECTION:
            members.extend(section.children)
    for child in members:
        if child.type == PascalNodeType.DECL_FIELD:
            type_node = next(
                (c for c in child.children if c.type == PascalNodeType.TYPE),
                None,
            )
            type_hint = type_node.text.decode() if type_node is not None else ""
            for sub in child.children:
                if sub.type == PascalNodeType.IDENTIFIER:
                    fname = sub.text.decode()
                    fields[fname] = FieldInfo(
                        name=fname, type_hint=type_hint, has_initializer=False
                    )
        elif child.type in (PascalNodeType.DECL_PROC, PascalNodeType.DEF_PROC):
            mname_node = next(
                (c for c in child.children if c.type == PascalNodeType.IDENTIFIER),
                None,
            )
            if mname_node is not None:
                mname = mname_node.text.decode()
                methods[mname] = FunctionInfo(name=mname, params=(), return_type="")

    return class_name, ClassInfo(
        name=class_name,
        fields=fields,
        methods=methods,
        constants={},
        parents=parents,
    )


def _collect_pascal_classes(node, accumulator: "dict[str, ClassInfo]") -> None:
    """Recursively walk the AST and collect all declType nodes containing declClass."""
    from interpreter.frontends.symbol_table import ClassInfo

    if node.type == PascalNodeType.DECL_TYPE:
        result = _extract_pascal_class_from_decl_type(node)
        if result is not None:
            class_name, class_info = result
            accumulator[class_name] = class_info
    for child in node.children:
        _collect_pascal_classes(child, accumulator)


def extract_pascal_symbols(root) -> "SymbolTable":
    """Walk the Pascal AST and return a SymbolTable of all class definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, SymbolTable

    classes: dict[str, ClassInfo] = {}
    _collect_pascal_classes(root, classes)
    return SymbolTable(classes=classes)
