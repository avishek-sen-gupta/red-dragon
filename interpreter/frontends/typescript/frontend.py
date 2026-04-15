"""TypeScriptFrontend — tree-sitter TypeScript AST -> IR lowering.

Extends JavaScriptFrontend, adding TS-specific node handlers and
skipping type annotations.
"""

from __future__ import annotations

from typing import Any, Callable

from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.ir import Opcode
from interpreter import constants
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Symbolic,
    CallFunction,
    CallMethod,
    LoadField,
    StoreField,
    StoreIndex,
    NewObject,
    Label_,
    Branch,
    BranchIf,
    Return_,
    ImportModule,
)
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.typescript_node_types import TypeScriptNodeType
from interpreter.path_name import NO_PATH_NAME
from interpreter.types.type_expr import (
    UNKNOWN,
    EnumType,
    ScalarType,
    TypeExpr,
    metatype,
    scalar,
)
from interpreter.register import Register
from interpreter.frontends.symbol_table import SymbolTable


class TypeScriptFrontend(JavaScriptFrontend):
    """Lowers TypeScript AST to IR. Extends JavaScriptFrontend, skipping type annotations."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        js_constants = super()._build_constants()
        return GrammarConstants(
            attr_object_field=js_constants.attr_object_field,
            attr_attribute_field=js_constants.attr_attribute_field,
            attribute_node_type=js_constants.attribute_node_type,
            subscript_value_field=js_constants.subscript_value_field,
            subscript_index_field=js_constants.subscript_index_field,
            comment_types=frozenset({TypeScriptNodeType.COMMENT}),
            noise_types=frozenset({TypeScriptNodeType.NEWLINE_CHAR}),
            block_node_types=js_constants.block_node_types,
            for_update_field=js_constants.for_update_field,
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "number": "Float",
            "string": "String",
            "boolean": "Bool",
            "void": "Any",
            "any": "Any",
            "undefined": "Any",
            "null": "Any",
            "never": "Any",
            "object": "Object",
        }

    def _build_expr_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], Register]]:
        dispatch = super()._build_expr_dispatch()
        dispatch.update(
            {
                TypeScriptNodeType.TYPE_IDENTIFIER: common_expr.lower_identifier,
                TypeScriptNodeType.PREDEFINED_TYPE: common_expr.lower_const_literal,
                TypeScriptNodeType.AS_EXPRESSION: lower_as_expression,
                TypeScriptNodeType.NON_NULL_EXPRESSION: lower_non_null_expr,
                TypeScriptNodeType.SATISFIES_EXPRESSION: lower_satisfies_expr,
                TypeScriptNodeType.TYPE_ASSERTION: lower_type_assertion,
                TypeScriptNodeType.ARROW_FUNCTION: lower_ts_arrow_function,
                TypeScriptNodeType.FUNCTION: lower_ts_function_expression,
                TypeScriptNodeType.FUNCTION_EXPRESSION: lower_ts_function_expression,
                TypeScriptNodeType.GENERATOR_FUNCTION: lower_ts_function_expression,
                TypeScriptNodeType.GENERATOR_FUNCTION_DECLARATION: lower_ts_function_def,
                TypeScriptNodeType.INSTANTIATION_EXPRESSION: lower_instantiation_expr,
            }
        )
        return dispatch

    def _build_stmt_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], None]]:
        dispatch = super()._build_stmt_dispatch()
        dispatch[TypeScriptNodeType.FUNCTION_DECLARATION] = lower_ts_function_def
        dispatch[TypeScriptNodeType.CLASS_DECLARATION] = lower_ts_class_def
        dispatch.update(
            {
                TypeScriptNodeType.INTERFACE_DECLARATION: lower_interface_decl,
                TypeScriptNodeType.ENUM_DECLARATION: lower_enum_decl,
                TypeScriptNodeType.TYPE_ALIAS_DECLARATION: lambda ctx, node: None,
                TypeScriptNodeType.EXPORT_STATEMENT: lower_ts_export_statement,
                TypeScriptNodeType.IMPORT_STATEMENT: lower_ts_import_statement,
                TypeScriptNodeType.ABSTRACT_CLASS_DECLARATION: lower_ts_class_def,
                TypeScriptNodeType.PUBLIC_FIELD_DEFINITION: lower_ts_field_definition,
                TypeScriptNodeType.ABSTRACT_METHOD_SIGNATURE: lower_ts_abstract_method,
                TypeScriptNodeType.INTERNAL_MODULE: lower_ts_internal_module,
                TypeScriptNodeType.FUNCTION_SIGNATURE: lambda ctx, node: None,
                TypeScriptNodeType.AMBIENT_DECLARATION: lambda ctx, node: None,
                TypeScriptNodeType.IMPORT_ALIAS: lower_import_alias,
            }
        )
        return dispatch

    def _extract_symbols(self, root) -> SymbolTable:
        from interpreter.frontends.javascript.declarations import (
            extract_javascript_symbols,
        )

        return extract_javascript_symbols(root)


# ── TS-specific expression lowerers (pure functions) ─────────────


def lower_as_expression(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    # x as Type -> just lower x, ignore the type
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return common_expr.lower_const_literal(ctx, node)


def lower_non_null_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    # x! -> just lower x
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return common_expr.lower_const_literal(ctx, node)


def lower_satisfies_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return common_expr.lower_const_literal(ctx, node)


def lower_instantiation_expr(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `fn<Type>` -> lower fn, discard type arguments (type erasure)."""
    func_node = next(
        (c for c in node.children if c.is_named and c.type != "type_arguments"),
        None,
    )
    if func_node:
        return ctx.lower_expr(func_node)
    return common_expr.lower_const_literal(ctx, node)


def lower_type_assertion(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `<Type>expr` -> just lower expr, ignore the type."""
    children = [c for c in node.children if c.is_named]
    # type_assertion: <Type>expr — type is first child, expression is last
    if len(children) >= 2:
        return ctx.lower_expr(children[-1])
    if children:
        return ctx.lower_expr(children[0])
    return common_expr.lower_const_literal(ctx, node)


# ── TS-specific statement lowerers (pure functions) ──────────────


def lower_interface_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower interface_declaration as CLASS block with method stubs.

    Mirrors lower_ts_class_def so that interface method return types are seeded
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

    if body_node:
        for child in body_node.children:
            if child.type in (
                "method_signature",
                "call_signature",
                "construct_signature",
            ):
                _lower_ts_interface_method(ctx, child)
            elif child.type == "property_signature":
                _lower_ts_interface_property(ctx, child)
            elif child.is_named and child.type not in ("index_signature",):
                ctx.lower_stmt(child)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(iface_name, class_label, [], result_reg=cls_reg)
    ctx.seed_var_type(iface_name, metatype(ScalarType(iface_name)))
    ctx.emit_inst(DeclVar(name=VarName(iface_name), value_reg=cls_reg))


def _lower_ts_interface_method(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a method_signature inside an interface as a function stub with return type."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    func_name = ctx.node_text(name_node) if name_node else "__iface_method"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return.lstrip(": "), ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def _lower_ts_interface_property(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a property_signature inside an interface as STORE_VAR with type seeding.

    Seeds type info so ADR-100 chain walk can resolve property types on
    interface-typed variables.
    """
    name_node = node.child_by_field_name("name")
    prop_name = ctx.node_text(name_node) if name_node else "__unknown_prop"
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type.lstrip(": "), ctx.type_map)
    val_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
    ctx.emit_inst(DeclVar(name=VarName(prop_name), value_reg=val_reg), node=node)
    ctx.seed_var_type(prop_name, type_hint)


def lower_enum_decl(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if name_node:
        enum_name = ctx.node_text(name_node)
        obj_reg = ctx.fresh_reg()
        ctx.emit_inst(
            NewObject(result_reg=obj_reg, type_hint=EnumType(enum_name)),
            node=node,
        )
        if body_node:
            for i, child in enumerate(c for c in body_node.children if c.is_named):
                member_name = ctx.node_text(child).split("=")[0].strip()
                key_reg = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=key_reg, value=member_name))
                val_reg = ctx.fresh_reg()
                ctx.emit_inst(Const(result_reg=val_reg, value=str(i)))
                ctx.emit_inst(
                    StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
                )
        ctx.emit_inst(DeclVar(name=VarName(enum_name), value_reg=obj_reg))


def lower_ts_field_definition(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `public name: type` or `public name = expr` as STORE_VAR."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    if name_node is None:
        name_node = next(
            (
                c
                for c in node.children
                if c.type == TypeScriptNodeType.PROPERTY_IDENTIFIER
            ),
            None,
        )
    if name_node is None:
        return
    field_name = ctx.node_text(name_node)
    value_node = node.child_by_field_name("value")
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
    ctx.emit_inst(DeclVar(name=VarName(field_name), value_reg=val_reg), node=node)


def lower_ts_export_statement(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    for child in node.children:
        if child.is_named and child.type != TypeScriptNodeType.EXPORT:
            ctx.lower_stmt(child)


def _extract_ts_parents(
    ctx: TreeSitterEmitContext, node: Any
) -> list[str]:  # Any: tree-sitter node — untyped at Python boundary
    """Extract parent class name from a TS class declaration."""
    heritage = next(
        (c for c in node.children if c.type == TypeScriptNodeType.CLASS_HERITAGE),
        None,
    )
    if heritage is None:
        return []
    id_types = (TypeScriptNodeType.IDENTIFIER, TypeScriptNodeType.TYPE_IDENTIFIER)
    return [
        ctx.node_text(c)
        for clause in heritage.children
        if clause.type == "extends_clause"
        for c in clause.children
        if c.type in id_types
    ]


def _extract_ts_interfaces(
    ctx: TreeSitterEmitContext, node: Any
) -> list[str]:  # Any: tree-sitter node — untyped at Python boundary
    """Extract interface names from implements_clause in a TS class declaration."""
    heritage = next(
        (c for c in node.children if c.type == TypeScriptNodeType.CLASS_HERITAGE),
        None,
    )
    if heritage is None:
        return []
    id_types = (TypeScriptNodeType.IDENTIFIER, TypeScriptNodeType.TYPE_IDENTIFIER)
    return [
        ctx.node_text(c)
        for clause in heritage.children
        if clause.type == "implements_clause"
        for c in clause.children
        if c.type in id_types
    ]


def lower_ts_class_def(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower class_declaration using TS-specific param handling for methods."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node)
    parents = _extract_ts_parents(ctx, node)
    for iface in _extract_ts_interfaces(ctx, node):
        ctx.seed_interface_impl(class_name, iface)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    if body_node:
        for child in body_node.children:
            if child.type == TypeScriptNodeType.METHOD_DEFINITION:
                _lower_ts_method_def(ctx, child)
            elif child.type == TypeScriptNodeType.CLASS_STATIC_BLOCK:
                from interpreter.frontends.javascript.declarations import (
                    lower_class_static_block,
                )

                lower_class_static_block(ctx, child)
            elif child.type == TypeScriptNodeType.FIELD_DEFINITION:
                from interpreter.frontends.javascript.expressions import (
                    lower_js_field_definition,
                )

                lower_js_field_definition(ctx, child)
            elif child.is_named:
                ctx.lower_stmt(child)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.seed_var_type(class_name, metatype(ScalarType(class_name)))
    ctx.emit_inst(DeclVar(name=VarName(class_name), value_reg=cls_reg))


def _lower_ts_method_def(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower method_definition using TS-specific param handling."""
    from interpreter.frontends.javascript.declarations import (
        _emit_this_param,
        _has_static_modifier,
    )

    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return.lstrip(": "), ctx.type_map)

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    if not _has_static_modifier(node):
        _emit_this_param(ctx)

    if params_node:
        lower_ts_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_ts_abstract_method(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `abstract speak(): string` as a function stub."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    func_name = ctx.node_text(name_node) if name_node else "__abstract"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_ts_internal_module(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `namespace Geometry { ... }` -- descend into body."""
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if body_node:
        ctx.lower_block(body_node)


# ── TS-specific param handling ───────────────────────────────────


def _extract_ts_type_hint(ctx: TreeSitterEmitContext, param_node) -> TypeExpr:
    """Extract type hint from a TS parameter's type_annotation field."""
    type_ann = param_node.child_by_field_name("type")
    if type_ann is None:
        return UNKNOWN
    # type_annotation contains `: <type>` — find the first named non-colon child
    type_child = next(
        (c for c in type_ann.children if c.is_named),
        None,
    )
    raw = ctx.node_text(type_child) if type_child else ""
    return normalize_type_hint(raw, ctx.type_map)


def lower_ts_param(ctx: TreeSitterEmitContext, child, param_index: int) -> None:
    """Lower a single TS parameter, extracting type annotations."""
    if child.type in (
        TypeScriptNodeType.OPEN_PAREN,
        TypeScriptNodeType.CLOSE_PAREN,
        TypeScriptNodeType.COMMA,
        TypeScriptNodeType.COLON,
        TypeScriptNodeType.TYPE_ANNOTATION,
    ):
        return
    if child.type == TypeScriptNodeType.REQUIRED_PARAMETER:
        pname_node = child.child_by_field_name("pattern")
        if pname_node is None:
            pname_node = next(
                (c for c in child.children if c.type == TypeScriptNodeType.IDENTIFIER),
                None,
            )
        if pname_node:
            pname = ctx.node_text(pname_node)
            type_hint = _extract_ts_type_hint(ctx, child)
            sym_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}{pname}"),
                node=child,
            )
            ctx.seed_register_type(sym_reg, type_hint)
            ctx.seed_param_type(pname, type_hint)
            ctx.emit_inst(
                DeclVar(
                    name=VarName(pname), value_reg=Register(f"%{ctx.reg_counter - 1}")
                )
            )
            ctx.seed_var_type(pname, type_hint)
            default_value_node = child.child_by_field_name("value")
            if default_value_node:
                from interpreter.frontends.common.default_params import (
                    emit_default_param_guard,
                )

                emit_default_param_guard(ctx, pname, param_index, default_value_node)
        return
    if child.type == TypeScriptNodeType.OPTIONAL_PARAMETER:
        pname_node = child.child_by_field_name("pattern")
        if pname_node is None:
            pname_node = next(
                (c for c in child.children if c.type == TypeScriptNodeType.IDENTIFIER),
                None,
            )
        if pname_node:
            pname = ctx.node_text(pname_node)
            type_hint = _extract_ts_type_hint(ctx, child)
            sym_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Symbolic(result_reg=sym_reg, hint=f"{constants.PARAM_PREFIX}{pname}"),
                node=child,
            )
            ctx.seed_register_type(sym_reg, type_hint)
            ctx.seed_param_type(pname, type_hint)
            ctx.emit_inst(
                DeclVar(
                    name=VarName(pname), value_reg=Register(f"%{ctx.reg_counter - 1}")
                )
            )
            ctx.seed_var_type(pname, type_hint)
        return
    # Fall back to JS param handling
    from interpreter.frontends.javascript.expressions import lower_js_param

    lower_js_param(ctx, child, param_index)


def lower_ts_params(ctx: TreeSitterEmitContext, params_node) -> None:
    param_index = 0
    for child in params_node.children:
        if child.type in (
            TypeScriptNodeType.OPEN_PAREN,
            TypeScriptNodeType.CLOSE_PAREN,
            TypeScriptNodeType.COMMA,
        ):
            continue
        lower_ts_param(ctx, child, param_index)
        param_index += 1


def lower_ts_arrow_function(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower arrow function using TS-specific param handling."""
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = f"__arrow_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        if params_node.type == TypeScriptNodeType.IDENTIFIER:
            lower_ts_param(ctx, params_node, 0)
        else:
            lower_ts_params(ctx, params_node)

    if body_node:
        if body_node.type == TypeScriptNodeType.STATEMENT_BLOCK:
            ctx.lower_block(body_node)
        else:
            val_reg = ctx.lower_expr(body_node)
            ctx.emit_inst(Return_(value_reg=val_reg))

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    return func_reg


def lower_ts_function_expression(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower anonymous function expression using TS-specific param handling."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else f"__anon_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        lower_ts_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    return func_reg


def lower_ts_function_def(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower function_declaration using TS-specific param handling."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return.lstrip(": "), ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        lower_ts_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))

    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_import_alias(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower import_alias: import Foo = Bar.Baz → LOAD_VAR/LOAD_FIELD + STORE_VAR.

    TypeScript namespace import. At runtime compiles to var Foo = Bar.Baz.
    """
    named = [c for c in node.children if c.is_named]
    alias_node = named[0] if named else node
    target_node = named[1] if len(named) >= 2 else node

    alias_name = ctx.node_text(alias_node)
    target_reg = _lower_nested_identifier(ctx, target_node)
    ctx.emit_inst(StoreVar(name=VarName(alias_name), value_reg=target_reg), node=node)


def _lower_nested_identifier(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    """Lower a nested_identifier (Bar.Baz) or plain identifier to a register."""
    if node.type == "identifier":
        return ctx.lower_expr(node)
    # nested_identifier: member_expression . property_identifier
    named = [c for c in node.children if c.is_named]
    obj_reg = _lower_nested_identifier(ctx, named[0])
    field_name = ctx.node_text(named[-1])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg


def lower_ts_import_statement(ctx: TreeSitterEmitContext, node: Any) -> None:
    """Lower import_statement: handle both CommonJS require and ESM imports.

    - import x = require('y')       → CALL_FUNCTION require + STORE_VAR x
    - import { a, b } from "./m"   → IMPORT_MODULE + LOAD_FIELD + DECL_VAR
    - import foo from "./m"        → IMPORT_MODULE + DECL_VAR
    - import * as ns from "./m"    → IMPORT_MODULE + DECL_VAR
    """
    # Check for CommonJS require() style: import x = require('y')
    for child in node.children:
        if child.type == TypeScriptNodeType.IMPORT_REQUIRE_CLAUSE:
            _lower_import_require_clause(ctx, child, node)
            return

    # ESM imports: emit IMPORT_MODULE
    # Extract the module path from the import_statement
    module_path = None
    for child in node.children:
        if child.type == "string":
            raw = ctx.node_text(child)
            module_path = raw.strip("'\"")
            break

    if module_path is None:
        # No module path found, skip this import
        return

    # Emit IMPORT_MODULE to load the module
    mod_reg = ctx.fresh_reg()
    resolved = ctx.resolved_imports.get(module_path, NO_PATH_NAME)
    ctx.emit_inst(
        ImportModule(
            result_reg=mod_reg,
            module_path=module_path,
            resolved_path=resolved,
        ),
        node=node,
    )

    # Find the import_clause to determine what to bind
    import_clause = None
    for child in node.children:
        if child.type == "import_clause":
            import_clause = child
            break

    if import_clause is None:
        return

    # Process the import_clause to bind imported names
    _lower_ts_import_clause(ctx, import_clause, mod_reg, node)


def _lower_ts_import_clause(
    ctx: TreeSitterEmitContext,
    clause: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower import_clause: process named_imports, namespace_import, or default_import."""
    for child in clause.children:
        if child.type == "named_imports":
            # import { a, b, c } from "./module"
            _lower_ts_named_imports(ctx, child, mod_reg, parent)
        elif child.type == "namespace_import":
            # import * as ns from "./module"
            _lower_ts_namespace_import(ctx, child, mod_reg, parent)
        elif child.type == "identifier":
            # Default import: import foo from "./module"
            # In an import_clause, a bare identifier is the default import
            import_name = ctx.node_text(child)
            ctx.emit_inst(
                DeclVar(name=VarName(import_name), value_reg=mod_reg), node=parent
            )


def _lower_ts_named_imports(
    ctx: TreeSitterEmitContext,
    named_imports: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower named_imports: { a, b, c } or { a as x, b as y }."""
    for child in named_imports.children:
        if child.type == "import_specifier":
            _lower_ts_import_specifier(ctx, child, mod_reg, parent)


def _lower_ts_import_specifier(
    ctx: TreeSitterEmitContext,
    specifier: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower import_specifier: a or a as b."""
    # import_specifier has children: [name] or [name, 'as', alias]
    named_children = [c for c in specifier.children if c.is_named]
    if len(named_children) == 1:
        # Simple name: import { a } from "./module"
        import_name = ctx.node_text(named_children[0])
        field_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=field_reg,
                obj_reg=mod_reg,
                field_name=FieldName(import_name),
            ),
            node=parent,
        )
        ctx.emit_inst(
            DeclVar(name=VarName(import_name), value_reg=field_reg), node=parent
        )
    elif len(named_children) == 2:
        # Aliased import: import { a as b } from "./module"
        import_name = ctx.node_text(named_children[0])
        alias_name = ctx.node_text(named_children[1])
        field_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=field_reg,
                obj_reg=mod_reg,
                field_name=FieldName(import_name),
            ),
            node=parent,
        )
        ctx.emit_inst(
            DeclVar(name=VarName(alias_name), value_reg=field_reg), node=parent
        )


def _lower_ts_namespace_import(
    ctx: TreeSitterEmitContext,
    namespace_import: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower namespace_import: import * as ns from "./module"."""
    # namespace_import: * as identifier
    for child in namespace_import.children:
        if child.type == "identifier":
            ns_name = ctx.node_text(child)
            ctx.emit_inst(
                DeclVar(name=VarName(ns_name), value_reg=mod_reg), node=parent
            )
            break


def _lower_import_require_clause(
    ctx: TreeSitterEmitContext,
    clause: Any,
    parent: Any,
) -> None:
    """Lower import_require_clause: identifier = require(string)."""
    name_node = None
    string_node = None
    for child in clause.children:
        if child.type == "identifier":
            name_node = child
        if child.type == "string":
            string_node = child
    if name_node is None:
        return
    # Emit CONST for the module path argument
    arg_reg = ctx.fresh_reg()
    if string_node is not None:
        # Extract string content (without quotes)
        raw = ctx.node_text(string_node)
        module_path = raw.strip("'\"")
        ctx.emit_inst(Const(result_reg=arg_reg, value=module_path), node=parent)
    # Emit CALL_FUNCTION require
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName("require"),
            args=(arg_reg,),
        ),
        node=parent,
    )
    # Emit STORE_VAR for the alias name
    var_name = ctx.node_text(name_node)
    ctx.emit_inst(StoreVar(name=VarName(var_name), value_reg=result_reg), node=parent)
