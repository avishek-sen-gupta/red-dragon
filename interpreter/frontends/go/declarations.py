"""Go-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.go.expressions import (
    extract_expression_list,
    get_expression_list_children,
    lower_expression_list,
    lower_go_store_target,
)
from interpreter.frontends.go.node_types import GoNodeType
from interpreter.var_name import VarName
from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.register import Register
from interpreter.instructions import (
    Const,
    DeclVar,
    Symbolic,
    Branch,
    Label_,
    Return_,
)

logger = logging.getLogger(__name__)


# -- Go: short variable declaration (:=) -----------------------------------


def lower_short_var_decl(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    left_names = extract_expression_list(ctx, left)
    right_regs = lower_expression_list(ctx, right)

    for name, val_reg in zip(left_names, right_regs):
        var_name = ctx.declare_block_var(name)
        ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=val_reg), node=node)


# -- Go: assignment statement (=) ------------------------------------------


def lower_go_assignment(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    left_nodes = get_expression_list_children(left)
    right_regs = lower_expression_list(ctx, right)

    for target, val_reg in zip(left_nodes, right_regs):
        lower_go_store_target(ctx, target, val_reg, node)


# -- Go: function declaration ----------------------------------------------

_GO_MAIN_FUNC_NAME = "main"


def lower_go_func_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"

    if func_name == _GO_MAIN_FUNC_NAME:
        _lower_go_main_hoisted(ctx, body_node)
        return

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "result")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        lower_go_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def _lower_go_main_hoisted(ctx: TreeSitterEmitContext, body_node) -> None:
    """Hoist func main() body to top level so its locals land in frame 0.

    Go's ``func main()`` is the program entry point.  Rather than
    wrapping it in a function definition (which the VM would skip),
    we emit its statements directly on the top-level path.
    """
    if body_node:
        ctx.lower_block(body_node)


# -- Go: method declaration ------------------------------------------------


def lower_go_method_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    receiver_node = node.child_by_field_name("receiver")

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "result")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    # Lower receiver as parameter
    if receiver_node:
        lower_go_params(ctx, receiver_node)

    if params_node:
        lower_go_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_go_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        if child.type == GoNodeType.PARAMETER_DECLARATION:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                param_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Symbolic(
                        result_reg=param_reg,
                        hint=f"{constants.PARAM_PREFIX}{pname}",
                    ),
                    node=child,
                )
                ctx.seed_register_type(param_reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit_inst(
                    DeclVar(
                        name=VarName(pname),
                        value_reg=Register(f"%{ctx.reg_counter - 1}"),
                    )
                )
                ctx.seed_var_type(pname, type_hint)
        elif child.type == GoNodeType.IDENTIFIER:
            pname = ctx.node_text(child)
            ctx.emit_inst(
                Symbolic(
                    result_reg=ctx.fresh_reg(),
                    hint=f"{constants.PARAM_PREFIX}{pname}",
                ),
                node=child,
            )
            ctx.emit_inst(
                DeclVar(
                    name=VarName(pname), value_reg=Register(f"%{ctx.reg_counter - 1}")
                )
            )


# -- Go: type declaration (struct) -----------------------------------------


def lower_go_type_decl(ctx: TreeSitterEmitContext, node) -> None:
    for child in node.children:
        if child.type == GoNodeType.TYPE_SPEC:
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            if name_node:
                type_name = ctx.node_text(name_node)
                if type_node and type_node.type == GoNodeType.STRUCT_TYPE:
                    _lower_go_struct_type(ctx, type_name, type_node, node)
                elif type_node and type_node.type == GoNodeType.INTERFACE_TYPE:
                    _lower_go_interface_type(ctx, type_name, type_node, node)
                else:
                    reg = ctx.fresh_reg()
                    ctx.emit_inst(
                        Symbolic(result_reg=reg, hint=f"type:{type_name}"),
                        node=node,
                    )
                    ctx.emit_inst(DeclVar(name=VarName(type_name), value_reg=reg))


def _lower_go_struct_type(
    ctx: TreeSitterEmitContext, type_name: str, type_node, parent_node
) -> None:
    """Emit a CLASS block for a Go struct type declaration."""
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit_inst(Branch(label=end_label), node=parent_node)
    ctx.emit_inst(Label_(label=class_label))
    # Struct fields are handled at instantiation time (composite_literal)
    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(type_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(type_name), value_reg=cls_reg))


def _lower_go_interface_type(
    ctx: TreeSitterEmitContext, type_name: str, type_node, parent_node
) -> None:
    """Emit a CLASS block for a Go interface type, with method stubs seeding return types."""
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit_inst(Branch(label=end_label), node=parent_node)
    ctx.emit_inst(Label_(label=class_label))

    method_elems = [c for c in type_node.children if c.type == GoNodeType.METHOD_ELEM]
    for method in method_elems:
        _lower_go_interface_method(ctx, method)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(type_name, class_label, [], result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=VarName(type_name), value_reg=cls_reg))


def _lower_go_interface_method(ctx: TreeSitterEmitContext, method_node) -> None:
    """Emit a function stub for a single Go interface method_elem."""
    name_node = next(
        (c for c in method_node.children if c.type == GoNodeType.FIELD_IDENTIFIER),
        None,
    )
    method_name = ctx.node_text(name_node) if name_node else "__anon"

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{method_name}")
    end_label = ctx.fresh_label(f"end_{method_name}")

    # Return type: look for type_identifier or other type node after parameter_list(s)
    raw_return = _extract_go_method_elem_return_type(ctx, method_node)
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=method_node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(method_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(method_name), value_reg=func_reg))


def _extract_go_method_elem_return_type(ctx: TreeSitterEmitContext, method_node) -> str:
    """Extract return type from a Go interface method_elem.

    In Go's tree-sitter grammar, the return type appears as a sibling of
    parameter_list nodes — it can be a type_identifier, pointer_type,
    slice_type, etc., or a second parameter_list for multiple returns.
    """
    param_list_seen = False
    for child in method_node.children:
        if child.type == "parameter_list":
            param_list_seen = True
            continue
        if param_list_seen and child.is_named:
            return ctx.node_text(child)
    return ""


# -- Go: var declaration ---------------------------------------------------


def lower_go_var_decl(ctx: TreeSitterEmitContext, node) -> None:
    specs = [c for c in node.children if c.type == GoNodeType.VAR_SPEC]
    # Handle var (...) block form: var_spec_list contains var_spec children
    spec_list = next(
        (c for c in node.children if c.type == GoNodeType.VAR_SPEC_LIST),
        None,
    )
    if spec_list is not None:
        specs = [c for c in spec_list.children if c.type == GoNodeType.VAR_SPEC]
    for spec in specs:
        _lower_var_spec(ctx, spec, node)


def _lower_var_spec(ctx: TreeSitterEmitContext, spec, parent_node) -> None:
    """Lower a single var_spec, supporting multiple names: `var a, b = 1, 2`."""
    names = [c for c in spec.children if c.type == GoNodeType.IDENTIFIER]
    value_node = spec.child_by_field_name("value")
    raw_type = extract_type_from_field(ctx, spec, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)

    if value_node:
        val_regs = lower_expression_list(ctx, value_node)
        for name_node, val_reg in zip(names, val_regs):
            name_str = ctx.declare_block_var(ctx.node_text(name_node))
            ctx.emit_inst(
                DeclVar(name=VarName(name_str), value_reg=val_reg), node=parent_node
            )
            ctx.seed_var_type(name_str, type_hint)
        # If more names than values (e.g. `var a, b int`), store None for remainder
        for name_node in names[len(val_regs) :]:
            name_str = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
            ctx.emit_inst(
                DeclVar(name=VarName(name_str), value_reg=val_reg), node=parent_node
            )
            ctx.seed_var_type(name_str, type_hint)
    else:
        for name_node in names:
            name_str = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
            ctx.emit_inst(
                DeclVar(name=VarName(name_str), value_reg=val_reg), node=parent_node
            )
            ctx.seed_var_type(name_str, type_hint)


# -- Go: const declaration -------------------------------------------------


def lower_go_const_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower const_declaration: iterate const_spec children with iota tracking.

    In Go, `iota` starts at 0 and increments per const_spec in a block.
    Value-less specs replay the previous expression with the new iota value.
    """
    iota_counter = 0
    prev_value_node = None
    old_iota = getattr(ctx, "_go_iota_value", 0)
    for child in node.children:
        if child.type == GoNodeType.CONST_SPEC:
            ctx._go_iota_value = iota_counter
            _lower_const_spec(ctx, child, prev_value_node)
            raw_value = child.child_by_field_name("value")
            if raw_value is not None:
                prev_value_node = _unwrap_expression_list(raw_value)
            iota_counter += 1
    ctx._go_iota_value = old_iota


def _unwrap_expression_list(node):
    """Unwrap a single-element expression_list to its inner expression."""
    if node.type == GoNodeType.EXPRESSION_LIST:
        named = [c for c in node.children if c.is_named]
        if len(named) == 1:
            return named[0]
    return node


def _lower_const_spec(ctx: TreeSitterEmitContext, node, prev_value_node=None) -> None:
    """Lower a single const_spec: lower value, DECL_VAR.

    If the spec has no value but a previous expression exists (iota pattern),
    re-lower the previous expression with the current iota counter.
    """
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    if value_node:
        value_node = _unwrap_expression_list(value_node)
    if name_node and value_node:
        val_reg = ctx.lower_expr(value_node)
        ctx.emit_inst(
            DeclVar(name=VarName(ctx.node_text(name_node)), value_reg=val_reg),
            node=node,
        )
    elif name_node and prev_value_node is not None:
        val_reg = ctx.lower_expr(prev_value_node)
        ctx.emit_inst(
            DeclVar(name=VarName(ctx.node_text(name_node)), value_reg=val_reg),
            node=node,
        )
    elif name_node:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
        ctx.emit_inst(
            DeclVar(name=VarName(ctx.node_text(name_node)), value_reg=val_reg),
            node=node,
        )


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_go_struct_fields(field_declaration_list) -> "dict[str, FieldInfo]":
    """Extract fields from a Go struct field_declaration_list node."""
    from interpreter.frontends.symbol_table import FieldInfo

    fields: dict[FieldName, FieldInfo] = {}
    for child in field_declaration_list.children:
        if child.type != "field_declaration":
            continue
        # A field_declaration can have multiple names before the type
        type_node = child.child_by_field_name("type")
        type_hint = type_node.text.decode() if type_node is not None else ""
        for subchild in child.children:
            if subchild.type == GoNodeType.FIELD_IDENTIFIER:
                fname = subchild.text.decode()
                fields[FieldName(fname)] = FieldInfo(
                    name=FieldName(fname), type_hint=type_hint, has_initializer=False
                )
    return fields


def _extract_go_method_params(params_node) -> "tuple[str, ...]":
    """Extract parameter names from a Go parameter_list node (skip receiver)."""
    return tuple(
        subchild.text.decode()
        for child in params_node.children
        if child.type == GoNodeType.PARAMETER_DECLARATION
        for subchild in child.children
        if subchild.type == GoNodeType.IDENTIFIER
    )


def _collect_go_structs(
    node, classes: "dict[ClassName, ClassInfo]", methods: "dict[FuncName, FunctionInfo]"
) -> None:
    """Walk AST to collect structs (as ClassInfo) and top-level/method functions."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo

    if node.type == GoNodeType.TYPE_DECLARATION:
        for child in node.children:
            if child.type == GoNodeType.TYPE_SPEC:
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if (
                    name_node is not None
                    and type_node is not None
                    and type_node.type == GoNodeType.STRUCT_TYPE
                ):
                    struct_name = name_node.text.decode()
                    field_list = next(
                        (
                            c
                            for c in type_node.children
                            if c.type == "field_declaration_list"
                        ),
                        None,
                    )
                    fields: dict[str, FieldInfo] = (
                        _extract_go_struct_fields(field_list)
                        if field_list is not None
                        else {}
                    )
                    classes[ClassName(struct_name)] = ClassInfo(
                        name=ClassName(struct_name),
                        fields=fields,
                        methods={},
                        constants={},
                        parents=(),
                    )
    elif node.type == GoNodeType.FUNCTION_DECLARATION:
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        if name_node is not None:
            fname = name_node.text.decode()
            params = (
                _extract_go_method_params(params_node)
                if params_node is not None
                else ()
            )
            methods[FuncName(fname)] = FunctionInfo(
                name=FuncName(fname), params=params, return_type=""
            )
    elif node.type == GoNodeType.METHOD_DECLARATION:
        # Attach method to its receiver type
        name_node = node.child_by_field_name("name")
        receiver = node.child_by_field_name("receiver")
        params_node = node.child_by_field_name("parameters")
        if name_node is not None and receiver is not None:
            mname = name_node.text.decode()
            params = (
                _extract_go_method_params(params_node)
                if params_node is not None
                else ()
            )
            minfo = FunctionInfo(name=FuncName(mname), params=params, return_type="")
            # Find receiver type name from parameter_declaration > type_identifier
            receiver_type = next(
                (
                    sub.text.decode().lstrip("*")
                    for rchild in receiver.children
                    if rchild.type == GoNodeType.PARAMETER_DECLARATION
                    for sub in rchild.children
                    if sub.type == GoNodeType.TYPE_IDENTIFIER
                ),
                None,
            )
            if receiver_type is not None and ClassName(receiver_type) in classes:
                classes[ClassName(receiver_type)].methods[FuncName(mname)] = minfo
    for child in node.children:
        _collect_go_structs(child, classes, methods)


def extract_go_symbols(root) -> "SymbolTable":
    """Walk the Go AST and return a SymbolTable of all struct and function definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, FunctionInfo, SymbolTable

    classes: dict[ClassName, ClassInfo] = {}
    top_level_functions: dict[FuncName, FunctionInfo] = {}
    _collect_go_structs(root, classes, top_level_functions)
    return SymbolTable(classes=classes, functions=top_level_functions)
