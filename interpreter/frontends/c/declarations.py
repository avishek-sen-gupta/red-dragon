"""C-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter.var_name import VarName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.class_name import ClassName
from interpreter.register import Register
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    StoreField,
    Symbolic,
    CallFunction,
    NewObject,
    Label_,
    Branch,
    Return_,
)
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.c.node_types import CNodeType
from interpreter.types.type_expr import UNKNOWN, EnumType, TypeExpr, scalar, pointer

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
                ctx.emit_inst(
                    NewObject(result_reg=val_reg, type_hint=scalar(struct_type)),
                    node=node,
                )
            else:
                val_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Const(result_reg=val_reg, value=ctx.constants.none_literal)
                )
            ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=val_reg), node=node)
            ctx.seed_var_type(var_name, effective_type)


def _lower_init_declarator(
    ctx: TreeSitterEmitContext,
    node,
    struct_type: str = "",
    type_hint: TypeExpr = UNKNOWN,
) -> None:
    """Lower init_declarator (fields: declarator, value)."""
    from interpreter.frontends.cpp.node_types import CppNodeType

    decl_node = node.child_by_field_name("declarator")
    value_node = node.child_by_field_name("value")

    # C++17 structured bindings: auto [a, b] = expr;
    if (
        decl_node is not None
        and decl_node.type == CppNodeType.STRUCTURED_BINDING_DECLARATOR
    ):
        from interpreter.frontends.cpp.control_flow import _lower_structured_binding

        rhs_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
        _lower_structured_binding(ctx, decl_node, rhs_reg)
        return

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
    elif value_node and struct_type and value_node.type == "argument_list":
        # C++ constructor call: Circle c(5) → CALL_FUNCTION Circle(args)
        # Let the VM's constructor dispatch handle NEW_OBJECT + this injection
        arg_regs = [ctx.lower_expr(a) for a in value_node.children if a.is_named]
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=val_reg,
                func_name=FuncName(struct_type),
                args=tuple(arg_regs),
            ),
            node=node,
        )
    elif value_node:
        val_reg = ctx.lower_expr(value_node)
    elif struct_type:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewObject(result_reg=val_reg, type_hint=scalar(struct_type)), node=node
        )
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
    ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=val_reg), node=node)
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
            and inst.label.is_present()
            and inst.label.starts_with(class_prefix)
        ):
            in_body = True
            continue
        if (
            inst.opcode == Opcode.LABEL
            and inst.label.is_present()
            and inst.label.starts_with(end_prefix)
        ):
            break
        if in_body and inst.opcode == Opcode.STORE_FIELD:
            t = inst
            assert isinstance(t, StoreField)
            field_names.append(t.field_name)
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
    ctx.emit_inst(
        CallFunction(result_reg=obj_reg, func_name=FuncName(struct_type), args=()),
        node=decl_node,
    )
    ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=obj_reg), node=decl_node)

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
            ctx.emit_inst(LoadVar(result_reg=obj_load, name=VarName(var_name)))
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_load,
                    field_name=FieldName(str(fname)),
                    value_reg=val_reg,
                ),
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


def _lower_c_single_param(ctx: TreeSitterEmitContext, child, param_index: int) -> None:
    """Lower a single C/C++ parameter_declaration or optional_parameter_declaration."""
    decl_node = child.child_by_field_name("declarator")
    if not decl_node:
        return
    pname = extract_declarator_name(ctx, decl_node)
    raw_type = extract_type_from_field(ctx, child, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)
    ptr_depth = _count_pointer_depth(decl_node)
    effective_type = (
        _wrap_pointer_type(type_hint, ptr_depth) if ptr_depth else type_hint
    )
    sym_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}{pname}"),
        node=child,
    )
    ctx.seed_register_type(sym_reg, effective_type)
    ctx.seed_param_type(pname, effective_type)
    ctx.emit_inst(
        DeclVar(name=VarName(pname), value_reg=Register(f"%{ctx.reg_counter - 1}"))
    )
    ctx.seed_var_type(pname, effective_type)
    # C++ optional_parameter_declaration has a default_value field
    default_value_node = child.child_by_field_name("default_value")
    if default_value_node:
        from interpreter.frontends.common.default_params import (
            emit_default_param_guard,
        )

        emit_default_param_guard(ctx, pname, param_index, default_value_node)


def lower_c_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower C/C++ function parameters."""
    param_index = 0
    for child in params_node.children:
        if child.type in (
            CNodeType.PARAMETER_DECLARATION,
            "optional_parameter_declaration",
        ):
            _lower_c_single_param(ctx, child, param_index)
            param_index += 1


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

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        lower_c_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_struct_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower struct_specifier as class."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)

    if name_node is None and body_node is None:
        return

    struct_name = ctx.node_text(name_node) if name_node else "__anon_struct"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{struct_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{struct_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))
    if body_node:
        lower_struct_body(ctx, body_node)
    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(struct_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(struct_name), value_reg=cls_reg))


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
        ctx.emit_inst(LoadVar(result_reg=this_reg, name=VarName("this")))
        default_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=default_reg, value="0"), node=node)
        ctx.emit_inst(
            StoreField(
                obj_reg=this_reg, field_name=FieldName(fname), value_reg=default_reg
            ),
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
    ctx.emit_inst(
        NewObject(result_reg=obj_reg, type_hint=EnumType(enum_name)), node=node
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
                ctx.emit_inst(Const(result_reg=val_reg, value=str(i)))
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=FieldName(member_name),
                    value_reg=val_reg,
                ),
                node=enumerator,
            )

    ctx.emit_inst(DeclVar(name=VarName(enum_name), value_reg=obj_reg), node=node)


def lower_union_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower union_specifier like struct_specifier."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)

    if name_node is None and body_node is None:
        return

    union_name = ctx.node_text(name_node) if name_node else "__anon_union"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{union_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{union_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))
    if body_node:
        lower_struct_body(ctx, body_node)
    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(union_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(union_name), value_reg=cls_reg))


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

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    if params_node:
        lower_c_params(ctx, params_node)

    if value_node:
        val_reg = ctx.lower_expr(value_node)
        ctx.emit_inst(Return_(value_reg=val_reg))
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=none_reg, value=ctx.constants.default_return_value)
        )
        ctx.emit_inst(Return_(value_reg=none_reg))

    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_c_declarator_name_no_ctx(decl_node) -> "str | None":
    """Extract variable/function name from a C declarator without a ctx object."""
    if decl_node.type == CNodeType.IDENTIFIER:
        return decl_node.text.decode()
    inner = decl_node.child_by_field_name("declarator")
    if inner is not None:
        return _extract_c_declarator_name_no_ctx(inner)
    if (
        decl_node.type == CNodeType.PARENTHESIZED_DECLARATOR
        and decl_node.named_child_count > 0
    ):
        return _extract_c_declarator_name_no_ctx(decl_node.named_children[0])
    id_node = next(
        (c for c in decl_node.children if c.type == CNodeType.IDENTIFIER), None
    )
    return id_node.text.decode() if id_node is not None else None


def _extract_c_struct_fields(field_decl_list) -> "dict[str, FieldInfo]":
    """Extract fields from a C struct field_declaration_list node."""
    from interpreter.frontends.symbol_table import FieldInfo

    fields: dict[FieldName, FieldInfo] = {}
    for child in field_decl_list.children:
        if child.type != CNodeType.FIELD_DECLARATION:
            continue
        type_node = child.child_by_field_name("type")
        type_hint = type_node.text.decode() if type_node is not None else ""
        for sub in child.children:
            if sub.type == CNodeType.FIELD_IDENTIFIER:
                fname = sub.text.decode()
                fields[FieldName(fname)] = FieldInfo(
                    name=FieldName(fname), type_hint=type_hint, has_initializer=False
                )
    return fields


def _collect_c_structs_and_functions(
    node,
    classes: "dict[ClassName, ClassInfo]",
    functions: "dict[FuncName, FunctionInfo]",
) -> None:
    """Walk AST to collect struct_specifier nodes as ClassInfo and top-level function_definition nodes."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo

    if node.type == CNodeType.STRUCT_SPECIFIER:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            struct_name = name_node.text.decode()
            body = node.child_by_field_name("body")
            fields: dict[str, FieldInfo] = (
                _extract_c_struct_fields(body) if body is not None else {}
            )
            classes[ClassName(struct_name)] = ClassInfo(
                name=ClassName(struct_name),
                fields=fields,
                methods={},
                constants={},
                parents=(),
            )
    elif node.type == CNodeType.FUNCTION_DEFINITION:
        declarator = node.child_by_field_name("declarator")
        if declarator is not None:
            fname = _extract_c_declarator_name_no_ctx(declarator)
            if fname is not None:
                ret_node = node.child_by_field_name("type")
                return_type = ret_node.text.decode() if ret_node is not None else ""
                params_node = declarator.child_by_field_name("parameters")
                params: tuple[str, ...] = ()
                if params_node is not None:
                    params = tuple(
                        sub.text.decode()
                        for p in params_node.children
                        if p.type == CNodeType.PARAMETER_DECLARATION
                        for sub in p.children
                        if sub.type == CNodeType.IDENTIFIER
                    )
                functions[FuncName(fname)] = FunctionInfo(
                    name=FuncName(fname), params=params, return_type=return_type
                )
    for child in node.children:
        _collect_c_structs_and_functions(child, classes, functions)


def extract_c_symbols(root) -> "SymbolTable":
    """Walk the C AST and return a SymbolTable of all struct and function definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, FunctionInfo, SymbolTable

    classes: dict[ClassName, ClassInfo] = {}
    functions: dict[FuncName, FunctionInfo] = {}
    _collect_c_structs_and_functions(root, classes, functions)
    return SymbolTable(classes=classes, functions=functions)
