"""C-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.c.node_types import CNodeType
from interpreter.type_expr import UNKNOWN, TypeExpr, scalar, pointer

logger = logging.getLogger(__name__)


def extract_declarator_name(ctx: TreeSitterEmitContext, decl_node) -> str:
    """Extract the variable name from a declarator, handling pointer declarators."""
    if decl_node.type == CNodeType.IDENTIFIER:
        return ctx.node_text(decl_node)
    # pointer_declarator, array_declarator, etc.
    inner = decl_node.child_by_field_name("declarator")
    if inner:
        return extract_declarator_name(ctx, inner)
    # parenthesized_declarator: no "declarator" field, recurse into first named child
    if (
        decl_node.type == CNodeType.PARENTHESIZED_DECLARATOR
        and decl_node.named_child_count > 0
    ):
        return extract_declarator_name(ctx, decl_node.named_children[0])
    # Fallback: first identifier child
    id_node = next(
        (c for c in decl_node.children if c.type == CNodeType.IDENTIFIER), None
    )
    if id_node:
        return ctx.node_text(id_node)
    return ctx.node_text(decl_node)


def _count_pointer_depth(decl_node) -> int:
    """Count how many pointer_declarator wrappers surround the identifier."""
    depth = 0
    current = decl_node
    while current and current.type == CNodeType.POINTER_DECLARATOR:
        depth += 1
        current = current.child_by_field_name("declarator")
    return depth


def _wrap_pointer_type(base_type: TypeExpr, depth: int) -> TypeExpr:
    """Wrap *base_type* in *depth* layers of ``Pointer[...]``.

    Returns a ``TypeExpr`` (e.g. ``Pointer[Int]``, ``Pointer[Pointer[Int]]``).
    """
    from functools import reduce

    return reduce(lambda inner, _: pointer(inner), range(depth), base_type)


def _extract_struct_type(ctx: TreeSitterEmitContext, node) -> str:
    """Return the struct type name if *node* has a struct_specifier, else ''."""
    for child in node.children:
        if child.type == CNodeType.STRUCT_SPECIFIER:
            type_node = child.child_by_field_name("name")
            if type_node is None:
                type_node = next(
                    (c for c in child.children if c.type == CNodeType.TYPE_IDENTIFIER),
                    None,
                )
            if type_node:
                return ctx.node_text(type_node)
    return ""


def lower_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a C declaration: type declarator(s) with optional initializers."""
    struct_type = _extract_struct_type(ctx, node)
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)
    for child in node.children:
        if child.type == CNodeType.INIT_DECLARATOR:
            _lower_init_declarator(
                ctx, child, struct_type=struct_type, type_hint=type_hint
            )
        elif child.type in (CNodeType.IDENTIFIER, CNodeType.POINTER_DECLARATOR):
            raw_name = extract_declarator_name(ctx, child)
            var_name = ctx.declare_block_var(raw_name)
            ptr_depth = _count_pointer_depth(child)
            effective_type = (
                _wrap_pointer_type(type_hint, ptr_depth) if ptr_depth else type_hint
            )
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
                Opcode.DECL_VAR,
                operands=[var_name, val_reg],
                node=node,
            )
            ctx.seed_var_type(var_name, effective_type)


def _lower_init_declarator(
    ctx: TreeSitterEmitContext,
    node,
    struct_type: str = "",
    type_hint: TypeExpr = UNKNOWN,
) -> None:
    """Lower init_declarator (fields: declarator, value)."""
    decl_node = node.child_by_field_name("declarator")
    value_node = node.child_by_field_name("value")

    raw_name = extract_declarator_name(ctx, decl_node) if decl_node else "__anon"
    var_name = ctx.declare_block_var(raw_name)
    ptr_depth = _count_pointer_depth(decl_node) if decl_node else 0
    effective_type = (
        _wrap_pointer_type(type_hint, ptr_depth) if ptr_depth else type_hint
    )

    if value_node and struct_type and value_node.type == CNodeType.INITIALIZER_LIST:
        val_reg = _lower_struct_initializer_list(
            ctx, value_node, struct_type, var_name, node
        )
    elif value_node:
        val_reg = ctx.lower_expr(value_node)
    elif struct_type:
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
        Opcode.DECL_VAR,
        operands=[var_name, val_reg],
        node=node,
    )
    ctx.seed_var_type(var_name, effective_type)


def _extract_struct_field_names(
    ctx: TreeSitterEmitContext, struct_name: str
) -> list[str]:
    """Scan emitted IR for STORE_FIELD instructions in the struct's class body.

    Returns field names in declaration order.  The class body is bounded by
    LABEL class_<name>_N ... LABEL end_class_<name>_N.
    """
    class_prefix = f"{constants.CLASS_LABEL_PREFIX}{struct_name}"
    end_prefix = f"{constants.END_CLASS_LABEL_PREFIX}{struct_name}"
    in_body = False
    field_names: list[str] = []
    for inst in ctx.instructions:
        if (
            inst.opcode == Opcode.LABEL
            and inst.label
            and inst.label.startswith(class_prefix)
        ):
            in_body = True
            continue
        if (
            inst.opcode == Opcode.LABEL
            and inst.label
            and inst.label.startswith(end_prefix)
        ):
            break
        if in_body and inst.opcode == Opcode.STORE_FIELD:
            field_names.append(inst.operands[1])
    return field_names


def _lower_struct_initializer_list(
    ctx: TreeSitterEmitContext,
    init_node,
    struct_type: str,
    var_name: str,
    decl_node,
) -> str:
    """Lower {val, ...} or {.field = val, ...} as CALL_FUNCTION + STORE_FIELD.

    For positional elements, field names come from scanning the struct's
    class body IR.  For designated elements (.field = val), field names
    come from the field_designator AST node.
    """
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=obj_reg,
        operands=[struct_type],
        node=decl_node,
    )
    ctx.emit(Opcode.DECL_VAR, operands=[var_name, obj_reg], node=decl_node)

    field_names = _extract_struct_field_names(ctx, struct_type)
    elements = [c for c in init_node.children if c.is_named]

    for i, elem in enumerate(elements):
        if elem.type == CNodeType.INITIALIZER_PAIR:
            designator = next(
                (c for c in elem.children if c.type == CNodeType.FIELD_DESIGNATOR),
                None,
            )
            fname = ctx.node_text(designator).lstrip(".") if designator else ""
            value_node = next(
                (
                    c
                    for c in elem.children
                    if c.is_named and c.type != CNodeType.FIELD_DESIGNATOR
                ),
                None,
            )
            val_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
        elif i < len(field_names):
            fname = field_names[i]
            val_reg = ctx.lower_expr(elem)
        else:
            logger.warning(
                "struct %s initializer: more elements than fields (%d >= %d)",
                struct_type,
                i,
                len(field_names),
            )
            continue

        if fname:
            obj_load = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_VAR, result_reg=obj_load, operands=[var_name])
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_load, fname, val_reg],
                node=elem,
            )

    return obj_reg


def _find_function_declarator(node) -> object | None:
    """Recursively find function_declarator inside pointer/other declarators."""
    if node.type == CNodeType.FUNCTION_DECLARATOR:
        return node
    for child in node.children:
        result = _find_function_declarator(child)
        if result:
            return result
    return None


def _find_innermost_function_declarator(node) -> object | None:
    """Find the innermost function_declarator by following the declarator chain.

    For complex C declarations like ``int (*get_op(int choice))(int, int)``,
    the outermost function_declarator holds the pointer's parameter types,
    while the innermost holds the real function name and parameters.
    """
    if node.type == CNodeType.FUNCTION_DECLARATOR:
        inner = _find_function_declarator_in_declarator_child(node)
        return inner if inner else node
    return _find_function_declarator(node)


def _find_function_declarator_in_declarator_child(func_decl) -> object | None:
    """Search the declarator subtree of a function_declarator for a nested one."""
    decl_child = func_decl.child_by_field_name("declarator")
    if decl_child:
        return _find_function_declarator(decl_child)
    return None


def lower_c_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower C function parameters (parameter_declaration nodes)."""
    for child in params_node.children:
        if child.type == CNodeType.PARAMETER_DECLARATION:
            decl_node = child.child_by_field_name("declarator")
            if decl_node:
                pname = extract_declarator_name(ctx, decl_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                ptr_depth = _count_pointer_depth(decl_node)
                effective_type = (
                    _wrap_pointer_type(type_hint, ptr_depth) if ptr_depth else type_hint
                )
                sym_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=sym_reg,
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(sym_reg, effective_type)
                ctx.seed_param_type(pname, effective_type)
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, effective_type)


def lower_function_def_c(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_definition with nested function_declarator."""
    declarator_node = node.child_by_field_name("declarator")
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = "__anon"
    params_node = None

    if declarator_node:
        if declarator_node.type == CNodeType.FUNCTION_DECLARATOR:
            # Check for nested function_declarator (e.g. function-pointer return types)
            inner_decl = _find_innermost_function_declarator(declarator_node)
            target_decl = inner_decl if inner_decl else declarator_node
            name_node = target_decl.child_by_field_name("declarator")
            params_node = target_decl.child_by_field_name(
                ctx.constants.func_params_field
            )
            func_name = (
                extract_declarator_name(ctx, name_node) if name_node else "__anon"
            )
        else:
            func_decl = _find_innermost_function_declarator(declarator_node)
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
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_struct_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower struct_specifier as class."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)

    if name_node is None and body_node is None:
        return

    struct_name = ctx.node_text(name_node) if name_node else "__anon_struct"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{struct_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{struct_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        lower_struct_body(ctx, body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=struct_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[struct_name, cls_reg])


def lower_struct_body(ctx: TreeSitterEmitContext, node) -> None:
    """Lower struct field_declaration_list."""
    for child in node.children:
        if child.type == CNodeType.FIELD_DECLARATION:
            lower_struct_field(ctx, child)
        elif child.is_named and child.type not in ("{", "}"):
            ctx.lower_stmt(child)


def _collect_field_identifiers(node) -> list:
    """Recursively collect field_identifier/identifier nodes from a field_declaration.

    Handles pointer fields like ``struct Node* next_node`` where the
    field_identifier is nested inside a pointer_declarator.
    """
    results = []
    for c in node.children:
        if c.type in (CNodeType.FIELD_IDENTIFIER, CNodeType.IDENTIFIER):
            results.append(c)
        elif c.type == CNodeType.POINTER_DECLARATOR:
            results.extend(_collect_field_identifiers(c))
    return results


def lower_struct_field(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a struct field declaration as STORE_FIELD on this."""
    declarators = _collect_field_identifiers(node)
    for decl in declarators:
        fname = ctx.node_text(decl)
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        default_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=default_reg,
            operands=["0"],
            node=node,
        )
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=[this_reg, fname, default_reg],
            node=node,
        )


def lower_enum_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_specifier as NEW_OBJECT + STORE_FIELD per enumerator."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)

    if name_node is None and body_node is None:
        return

    enum_name = ctx.node_text(name_node) if name_node else "__anon_enum"

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"enum:{enum_name}"],
        node=node,
    )

    if body_node:
        enumerators = [c for c in body_node.children if c.type == CNodeType.ENUMERATOR]
        for i, enumerator in enumerate(enumerators):
            name_child = enumerator.child_by_field_name("name")
            value_child = enumerator.child_by_field_name("value")
            member_name = ctx.node_text(name_child) if name_child else f"__enum_{i}"
            if value_child:
                val_reg = ctx.lower_expr(value_child)
            else:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[str(i)],
                )
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, member_name, val_reg],
                node=enumerator,
            )

    ctx.emit(
        Opcode.DECL_VAR,
        operands=[enum_name, obj_reg],
        node=node,
    )


def lower_union_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower union_specifier like struct_specifier."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)

    if name_node is None and body_node is None:
        return

    union_name = ctx.node_text(name_node) if name_node else "__anon_union"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{union_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{union_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        lower_struct_body(ctx, body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=union_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[union_name, cls_reg])


def lower_typedef(ctx: TreeSitterEmitContext, node) -> None:
    """Lower typedef as a type alias seed.

    Examples: ``typedef int UserId;`` → alias UserId = Int
              ``typedef int* IntPtr;`` → alias IntPtr = Pointer[Int]
    """
    named_children = [c for c in node.children if c.is_named]
    # Extract base type from the first primitive/type specifier
    raw_type = extract_type_from_field(ctx, node, "type")
    base_type = normalize_type_hint(raw_type, ctx.type_map)

    # Find alias name: last type_identifier, or from pointer_declarator
    alias_name = ""
    ptr_depth = 0
    for child in reversed(named_children):
        if child.type == CNodeType.TYPE_IDENTIFIER:
            alias_name = ctx.node_text(child)
            break
        if child.type == CNodeType.POINTER_DECLARATOR:
            alias_name = extract_declarator_name(ctx, child)
            ptr_depth = _count_pointer_depth(child)
            break

    if not alias_name:
        return

    effective_type = (
        _wrap_pointer_type(base_type, ptr_depth) if ptr_depth else base_type
    )
    ctx.seed_type_alias(alias_name, effective_type)
    logger.debug("Typedef alias: %s → %s", alias_name, effective_type)


def lower_preproc_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `#define FUNC(args) body` as function stub."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    func_name = ctx.node_text(name_node) if name_node else "__macro"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        lower_c_params(ctx, params_node)

    if value_node:
        val_reg = ctx.lower_expr(value_node)
        ctx.emit(Opcode.RETURN, operands=[val_reg])
    else:
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
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])
