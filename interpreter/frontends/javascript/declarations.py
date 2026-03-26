"""JavaScript-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter import constants
from interpreter.frontends.javascript.expressions import lower_js_params
from interpreter.frontends.javascript.node_types import JavaScriptNodeType as JSN
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.types.type_expr import ScalarType, metatype
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.instructions import (
    Const,
    DeclVar,
    LoadField,
    LoadIndex,
    CallFunction,
    Symbolic,
    Branch,
    Label_,
    Return_,
)


def lower_js_var_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower lexical_declaration / variable_declaration, handling destructuring."""
    for child in node.children:
        if child.type != JSN.VARIABLE_DECLARATOR:
            continue
        name_node = child.child_by_field_name(ctx.constants.func_name_field)
        value_node = child.child_by_field_name("value")
        if name_node is None:
            continue

        if name_node.type == JSN.OBJECT_PATTERN and value_node:
            val_reg = ctx.lower_expr(value_node)
            _lower_object_destructure(ctx, name_node, val_reg, node)
        elif name_node.type == JSN.ARRAY_PATTERN and value_node:
            val_reg = ctx.lower_expr(value_node)
            _lower_array_destructure(ctx, name_node, val_reg, node)
        elif value_node:
            var_name = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.lower_expr(value_node)
            ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=val_reg), node=node)
        else:
            var_name = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=val_reg, value=ctx.constants.none_literal))
            ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=val_reg), node=node)


def _lower_object_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower { a, b } = obj or { x: localX } = obj, including ...rest."""
    extracted_keys: list[str] = []
    rest_child = None

    for child in pattern_node.children:
        if child.type == JSN.SHORTHAND_PROPERTY_IDENTIFIER_PATTERN:
            prop_name = ctx.node_text(child)
            extracted_keys.append(prop_name)
            field_reg = ctx.fresh_reg()
            ctx.emit_inst(
                LoadField(result_reg=field_reg, obj_reg=val_reg, field_name=prop_name),
                node=child,
            )
            ctx.emit_inst(
                DeclVar(name=VarName(prop_name), value_reg=field_reg), node=parent_node
            )
        elif child.type == JSN.PAIR_PATTERN:
            key_node = child.child_by_field_name("key")
            value_child = child.child_by_field_name("value")
            if key_node and value_child:
                key_name = ctx.node_text(key_node)
                local_name = ctx.node_text(value_child)
                extracted_keys.append(key_name)
                field_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    LoadField(
                        result_reg=field_reg, obj_reg=val_reg, field_name=key_name
                    ),
                    node=child,
                )
                ctx.emit_inst(
                    DeclVar(name=VarName(local_name), value_reg=field_reg),
                    node=parent_node,
                )
        elif child.type == JSN.REST_PATTERN:
            rest_child = child

    if rest_child is not None:
        rest_name = _extract_rest_name(rest_child)
        if rest_name:
            key_regs = [_const_reg(ctx, key) for key in extracted_keys]
            rest_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=rest_reg,
                    func_name="object_rest",
                    args=(val_reg, *key_regs),
                ),
                node=rest_child,
            )
            ctx.emit_inst(
                DeclVar(name=VarName(rest_name), value_reg=rest_reg), node=parent_node
            )


def _const_reg(ctx: TreeSitterEmitContext, value: str) -> str:
    """Emit a CONST and return the register holding the value."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=value))
    return reg


def _extract_rest_name(child) -> str | None:
    """Extract the identifier name from a rest_pattern node, or None if not rest."""
    if child.type != JSN.REST_PATTERN:
        return None
    id_child = next((c for c in child.children if c.type == JSN.IDENTIFIER), None)
    return id_child.text.decode("utf-8") if id_child else None


def _lower_array_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower [a, b] = arr, including rest patterns like [a, ...rest] = arr."""
    named_children = [c for c in pattern_node.children if c.is_named]
    for i, child in enumerate(named_children):
        rest_name = _extract_rest_name(child)
        if rest_name is not None:
            # ...rest — slice from index i onward
            start_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=start_reg, value=str(i)))
            rest_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=rest_reg,
                    func_name="slice",
                    args=(val_reg, start_reg),
                ),
                node=child,
            )
            ctx.emit_inst(
                DeclVar(name=VarName(rest_name), value_reg=rest_reg), node=parent_node
            )
        else:
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
            elem_reg = ctx.fresh_reg()
            ctx.emit_inst(
                LoadIndex(result_reg=elem_reg, arr_reg=val_reg, index_reg=idx_reg),
                node=child,
            )
            ctx.emit_inst(
                DeclVar(name=VarName(ctx.node_text(child)), value_reg=elem_reg),
                node=parent_node,
            )


def _extract_js_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class name from a JS class declaration (single inheritance)."""
    heritage = next((c for c in node.children if c.type == JSN.CLASS_HERITAGE), None)
    if heritage is None:
        return []
    parent_id = next((c for c in heritage.children if c.type == JSN.IDENTIFIER), None)
    return [ctx.node_text(parent_id)] if parent_id else []


def lower_js_class_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower anonymous class expression: `class { ... }` or `class Name { ... }`.

    Like lower_js_class_def but returns a register (expression position)
    and handles missing name by generating a synthetic one.
    """
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = (
        ctx.node_text(name_node) if name_node else f"__anon_class_{ctx.label_counter}"
    )
    parents = _extract_js_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    if body_node:
        for child in body_node.children:
            if child.type == JSN.METHOD_DEFINITION:
                _lower_method_def(ctx, child)
            elif child.type == JSN.CLASS_STATIC_BLOCK:
                lower_class_static_block(ctx, child)
            elif child.type == JSN.FIELD_DEFINITION:
                from interpreter.frontends.javascript.expressions import (
                    lower_js_field_definition,
                )

                lower_js_field_definition(ctx, child)
            elif child.is_named:
                ctx.lower_stmt(child)

    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.seed_register_type(cls_reg, metatype(ScalarType(class_name)))
    return cls_reg


def lower_js_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node)
    parents = _extract_js_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))

    if body_node:
        for child in body_node.children:
            if child.type == JSN.METHOD_DEFINITION:
                _lower_method_def(ctx, child)
            elif child.type == JSN.CLASS_STATIC_BLOCK:
                lower_class_static_block(ctx, child)
            elif child.type == JSN.FIELD_DEFINITION:
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
    """Return True if *node* has a ``static`` child token."""
    return any(c.type == JSN.STATIC for c in node.children)


def _lower_method_def(ctx: TreeSitterEmitContext, node) -> None:
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
        lower_js_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_js_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_declaration using JS-specific param handling."""
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
        lower_js_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))

    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=VarName(func_name), value_reg=func_reg))


def lower_export_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `export ...` by unwrapping and lowering the inner declaration."""
    for child in node.children:
        if child.is_named and child.type not in (JSN.EXPORT, JSN.DEFAULT):
            ctx.lower_stmt(child)


def lower_class_static_block(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `static { ... }` inside a class body."""
    body_node = node.child_by_field_name("body")
    if body_node:
        ctx.lower_block(body_node)
        return
    # Fallback: lower all named children as statements
    for child in node.children:
        if child.is_named and child.type not in (JSN.STATIC,):
            ctx.lower_stmt(child)


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_js_method(node) -> tuple[str, "FunctionInfo"] | None:
    """Extract a FunctionInfo from a JS method_definition node."""
    from interpreter.frontends.symbol_table import FunctionInfo

    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = name_node.text.decode()
    params_node = node.child_by_field_name("parameters")
    params = _extract_param_names(params_node) if params_node is not None else ()
    return name, FunctionInfo(name=name, params=params, return_type="")


def _extract_param_names(params_node) -> tuple[str, ...]:
    """Extract parameter names from formal_parameters — handles JS and TS param styles."""
    names: list[str] = []
    for p in params_node.children:
        if p.type == JSN.IDENTIFIER:
            names.append(p.text.decode())
        elif p.type in ("required_parameter", "optional_parameter"):
            id_node = next((c for c in p.children if c.type == "identifier"), p)
            names.append(id_node.text.decode())
    return tuple(names)
    return name, FunctionInfo(name=name, params=params, return_type="")


def _extract_js_self_fields(body) -> "dict[str, FieldInfo]":
    """Walk a constructor body and collect this.x = ... assignments."""
    from interpreter.frontends.symbol_table import FieldInfo

    fields: dict[str, FieldInfo] = {}
    for stmt in body.children:
        # expression_statement > assignment_expression
        if stmt.type != JSN.EXPRESSION_STATEMENT:
            continue
        assign = next(
            (c for c in stmt.children if c.type == JSN.ASSIGNMENT_EXPRESSION), None
        )
        if assign is None:
            continue
        lhs = assign.child_by_field_name("left")
        if lhs is None or lhs.type != JSN.MEMBER_EXPRESSION:
            continue
        obj_node = lhs.child_by_field_name("object")
        prop_node = lhs.child_by_field_name("property")
        if obj_node is None or prop_node is None:
            continue
        if obj_node.text != b"this":
            continue
        field_name = prop_node.text.decode()
        fields[field_name] = FieldInfo(
            name=field_name, type_hint="", has_initializer=True
        )
    return fields


def _extract_js_class(node) -> "tuple[str, ClassInfo] | None":
    """Extract a ClassInfo from a JS class_declaration or class node."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo, FunctionInfo

    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    class_name = name_node.text.decode()

    heritage = next((c for c in node.children if c.type == JSN.CLASS_HERITAGE), None)
    parents: tuple[str, ...] = ()
    if heritage is not None:
        # JS: identifier directly in class_heritage
        # TS: extends_clause > identifier
        direct_ids = [c for c in heritage.children if c.type == JSN.IDENTIFIER]
        nested_ids = [
            sub
            for c in heritage.children
            if c.type == "extends_clause"
            for sub in c.children
            if sub.type == JSN.IDENTIFIER
        ]
        parents = tuple(c.text.decode() for c in (direct_ids or nested_ids))

    body = node.child_by_field_name("body")
    if body is None:
        return class_name, ClassInfo(
            name=class_name, fields={}, methods={}, constants={}, parents=parents
        )

    fields: dict[str, FieldInfo] = {}
    methods: dict[str, FunctionInfo] = {}

    for child in body.children:
        if child.type == JSN.METHOD_DEFINITION:
            result = _extract_js_method(child)
            if result is None:
                continue
            mname, minfo = result
            methods[mname] = minfo
            if mname == "constructor":
                ctor_body = child.child_by_field_name("body")
                if ctor_body is not None:
                    fields.update(_extract_js_self_fields(ctor_body))
        elif child.type == JSN.FIELD_DEFINITION:
            prop_node = child.child_by_field_name("property")
            if prop_node is not None:
                fname = prop_node.text.decode()
                has_init = child.child_by_field_name("value") is not None
                fields[fname] = FieldInfo(
                    name=fname, type_hint="", has_initializer=has_init
                )

    return class_name, ClassInfo(
        name=class_name, fields=fields, methods=methods, constants={}, parents=parents
    )


def _collect_js_classes(node, accumulator: "dict[str, ClassInfo]") -> None:
    """Recursively walk the AST and collect all class nodes."""
    from interpreter.frontends.symbol_table import ClassInfo

    if node.type in (JSN.CLASS_DECLARATION, JSN.CLASS):
        result = _extract_js_class(node)
        if result is not None:
            class_name, class_info = result
            accumulator[class_name] = class_info
    for child in node.children:
        _collect_js_classes(child, accumulator)


def extract_javascript_symbols(root) -> "SymbolTable":
    """Walk the JS AST and return a SymbolTable of all class definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, SymbolTable

    classes: dict[str, ClassInfo] = {}
    _collect_js_classes(root, classes)
    return SymbolTable(classes=classes)
