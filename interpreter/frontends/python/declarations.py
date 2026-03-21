"""Python-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.declarations import lower_class_def
from interpreter.frontends.python.node_types import PythonNodeType


def _extract_python_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class names from a Python class_definition node.

    In tree-sitter Python, superclasses are inside an ``argument_list``
    child containing ``identifier`` children.
    """
    arg_list = next(
        (c for c in node.children if c.type == PythonNodeType.ARGUMENT_LIST),
        None,
    )
    if arg_list is None:
        return []
    return [
        ctx.node_text(c)
        for c in arg_list.children
        if c.type == PythonNodeType.IDENTIFIER
    ]


def lower_python_class_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Python class_definition, extracting parents for inheritance."""
    parents = _extract_python_parents(ctx, node)
    lower_class_def(ctx, node, parents=parents)


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------
from interpreter.frontends.symbol_table import (
    ClassInfo,
    FieldInfo,
    FunctionInfo,
    SymbolTable,
)


def _extract_python_class_parents(node) -> tuple[str, ...]:
    """Extract parent class names from a Python class_definition node."""
    arg_list = next(
        (c for c in node.children if c.type == PythonNodeType.ARGUMENT_LIST),
        None,
    )
    if arg_list is None:
        return ()
    return tuple(
        c.text.decode()
        for c in arg_list.children
        if c.type == PythonNodeType.IDENTIFIER
    )


def _extract_python_match_args(node) -> tuple[str, ...]:
    """Extract __match_args__ tuple from a class body assignment node.

    Expects the right side to be a tuple containing string nodes.
    """
    rhs = next(
        (c for c in node.children if c.type == PythonNodeType.TUPLE),
        None,
    )
    if rhs is None:
        return ()
    return tuple(
        c.text.decode()
        for c in rhs.children
        if c.type == PythonNodeType.STRING
        for sc in c.children
        if sc.type == PythonNodeType.STRING_CONTENT
        for _ in [None]
    ) or tuple(
        sc.text.decode()
        for c in rhs.children
        if c.type == PythonNodeType.STRING
        for sc in c.children
        if sc.type == PythonNodeType.STRING_CONTENT
    )


def _extract_python_self_fields(init_body) -> dict[str, FieldInfo]:
    """Walk an __init__ body block and collect self.x = ... assignments."""
    fields: dict[str, FieldInfo] = {}
    for stmt in init_body.children:
        if stmt.type != PythonNodeType.ASSIGNMENT:
            continue
        lhs = next((c for c in stmt.children if c.is_named), None)
        if lhs is None or lhs.type != PythonNodeType.ATTRIBUTE:
            continue
        obj_node = lhs.child_by_field_name("object")
        attr_node = lhs.child_by_field_name("attribute")
        if obj_node is None or attr_node is None:
            continue
        if obj_node.text != b"self":
            continue
        field_name = attr_node.text.decode()
        fields[field_name] = FieldInfo(
            name=field_name, type_hint="", has_initializer=True
        )
    return fields


def _extract_python_class(node) -> tuple[str, ClassInfo] | None:
    """Extract a ClassInfo from a Python class_definition node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    class_name = name_node.text.decode()
    parents = _extract_python_class_parents(node)

    body = next((c for c in node.children if c.type == PythonNodeType.BLOCK), None)
    if body is None:
        return class_name, ClassInfo(
            name=class_name, fields={}, methods={}, constants={}, parents=parents
        )

    fields: dict[str, FieldInfo] = {}
    constants_map: dict[str, str] = {}
    methods: dict[str, FunctionInfo] = {}
    match_args: tuple[str, ...] = ()

    for child in body.children:
        if child.type == PythonNodeType.ASSIGNMENT:
            lhs = child.children[0] if child.children else None
            if lhs is None or lhs.type != PythonNodeType.IDENTIFIER:
                continue
            lhs_name = lhs.text.decode()
            if lhs_name == "__match_args__":
                match_args = _extract_match_args_from_assignment(child)
            else:
                constants_map[lhs_name] = ""
        elif child.type == PythonNodeType.FUNCTION_DEFINITION:
            mname_node = child.child_by_field_name("name")
            if mname_node is None:
                continue
            mname = mname_node.text.decode()
            params_node = child.child_by_field_name("parameters")
            params = (
                tuple(
                    _python_param_name(p)
                    for p in params_node.children
                    if p.type == PythonNodeType.IDENTIFIER and p.text != b"self"
                )
                if params_node is not None
                else ()
            )
            ret_node = child.child_by_field_name("return_type")
            return_type = ret_node.text.decode() if ret_node else ""
            methods[mname] = FunctionInfo(
                name=mname, params=params, return_type=return_type
            )
            # Walk __init__ body to collect self.x fields
            if mname == "__init__":
                init_body = child.child_by_field_name("body")
                if init_body is not None:
                    fields.update(_extract_python_self_fields(init_body))

    return class_name, ClassInfo(
        name=class_name,
        fields=fields,
        methods=methods,
        constants=constants_map,
        parents=parents,
        match_args=match_args,
    )


def _extract_match_args_from_assignment(node) -> tuple[str, ...]:
    """Extract __match_args__ tuple values from an assignment node."""
    rhs = next(
        (c for c in node.children if c.type == PythonNodeType.TUPLE),
        None,
    )
    if rhs is None:
        return ()
    return tuple(
        sc.text.decode()
        for c in rhs.children
        if c.type == PythonNodeType.STRING
        for sc in c.children
        if sc.type == PythonNodeType.STRING_CONTENT
    )


def _python_param_name(node) -> str:
    """Return the parameter name text."""
    return node.text.decode()


def _collect_python_classes(node, accumulator: dict[str, ClassInfo]) -> None:
    """Recursively walk the AST and collect all class_definition nodes."""
    if node.type == PythonNodeType.CLASS_DEFINITION:
        result = _extract_python_class(node)
        if result is not None:
            class_name, class_info = result
            accumulator[class_name] = class_info
    for child in node.children:
        _collect_python_classes(child, accumulator)


def extract_python_symbols(root) -> SymbolTable:
    """Walk the Python AST and return a SymbolTable of all class definitions."""
    classes: dict[str, ClassInfo] = {}
    _collect_python_classes(root, classes)
    return SymbolTable(classes=classes)
