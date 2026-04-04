# interpreter/frontends/java/namespace.py
"""Java-specific namespace resolution: pre-scan, tree builder, resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.instructions import LoadField, LoadVar
from interpreter.namespace import (
    NO_CHAIN,
    NO_RESOLUTION,
    NamespaceResolver,
    NamespaceTree,
    NamespaceType,
    _NoChain,
    _NoResolution,
)
from interpreter.parser import TreeSitterParserFactory
from interpreter.project.types import ImportRef, ModuleUnit
from interpreter.refs.class_ref import NO_CLASS_REF, ClassRef
from interpreter.register import Register
from interpreter.var_name import VarName

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext

# Node types that declare types at the top level
_TYPE_DECLARATION_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    }
)

_PARSER_FACTORY = TreeSitterParserFactory()

_DUMMY_PATH = Path("<pre-scan>")


@dataclass
class JavaPreScanResult:
    """Pre-scan output for a single Java source file."""

    package: str | None = None
    class_names: list[str] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)


def java_pre_scan(source: bytes) -> JavaPreScanResult:
    """Fast tree-sitter extraction of package + class names + imports.

    Walks only top-level nodes — no expression lowering, no control flow.
    """
    parser = _PARSER_FACTORY.get_parser("java")
    tree = parser.parse(source)
    root = tree.root_node

    result = JavaPreScanResult()

    for child in root.children:
        if child.type == "package_declaration":
            # package com.example;  →  scoped_identifier or identifier
            name_node = child.child_by_field_name("name") or _first_named_child(child)
            if name_node is not None:
                result.package = source[name_node.start_byte : name_node.end_byte].decode()

        elif child.type in _TYPE_DECLARATION_TYPES:
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                result.class_names.append(
                    source[name_node.start_byte : name_node.end_byte].decode()
                )

        elif child.type == "import_declaration":
            _extract_import(child, source, result)

    return result


def _first_named_child(node: object) -> object | None:
    """Return the first named child of a tree-sitter node."""
    for child in node.children:  # type: ignore[attr-defined]
        if child.is_named:
            return child
    return None


def _extract_import(node: object, source: bytes, result: JavaPreScanResult) -> None:
    """Extract an ImportRef from an import_declaration node."""
    text = source[node.start_byte : node.end_byte].decode().strip()  # type: ignore[attr-defined]
    # import java.util.Arrays;  or  import java.io.*;
    text = text.removeprefix("import").strip().rstrip(";").strip()
    is_static = text.startswith("static ")
    if is_static:
        text = text.removeprefix("static").strip()

    if text.endswith(".*"):
        module_path = text[:-2]
        names = ("*",)
    else:
        parts = text.rsplit(".", 1)
        if len(parts) == 2:
            module_path, name = parts
            names = (name,)
        else:
            module_path = text
            names = ()

    result.imports.append(
        ImportRef(source_file=_DUMMY_PATH, module_path=module_path, names=names, is_system=True)
    )


def build_java_namespace_tree(
    scan_results: dict[Path, JavaPreScanResult],
    stdlib_registry: dict[Path, ModuleUnit],
) -> NamespaceTree:
    """Build namespace tree from stub registry + pre-scanned project classes.

    Stubs are registered first. Project classes override stubs at the
    same path (local wins).
    """
    tree = NamespaceTree()

    # Source 1: Stub registry — types with real ModuleUnits
    for stub_path, module in stdlib_registry.items():
        dotted = _path_to_dotted(stub_path)
        short_name = dotted.rsplit(".", 1)[-1]

        # Extract ClassRef from stub's exports if available
        class_ref = NO_CLASS_REF
        for cls_name, cls_label in module.exports.classes.items():
            if cls_name.value == short_name:
                class_ref = ClassRef(
                    name=cls_name, label=cls_label, parents=()
                )
                break

        tree.register_type(
            dotted,
            NamespaceType(short_name=short_name, class_ref=class_ref, module=module),
        )

    # Source 2: Project classes — short_name only, ClassRef = NO_CLASS_REF
    for file_path, scan in scan_results.items():
        if scan.package is None:
            continue  # no package → not addressable via qualified name
        for class_name in scan.class_names:
            dotted = f"{scan.package}.{class_name}"
            tree.register_type(
                dotted,
                NamespaceType(short_name=class_name, class_ref=NO_CLASS_REF),
            )

    return tree


def _path_to_dotted(path: Path) -> str:
    """Convert stub path to dotted name: java/util/Arrays.java → java.util.Arrays."""
    return ".".join(path.with_suffix("").parts)


def _collect_field_access_chain(
    ctx: TreeSitterEmitContext, node: object
) -> list[str] | _NoChain:
    """Walk nested field_access to collect ['java', 'util', 'Arrays'].

    Returns NO_CHAIN if root isn't a plain identifier.
    """
    segments: list[str] = []
    while node.type == "field_access":  # type: ignore[attr-defined]
        field_node = node.child_by_field_name("field")  # type: ignore[attr-defined]
        segments.append(ctx.node_text(field_node))
        node = node.child_by_field_name(ctx.constants.attr_object_field)  # type: ignore[attr-defined]
    if node.type == "identifier":  # type: ignore[attr-defined]
        segments.append(ctx.node_text(node))
        segments.reverse()
        return segments
    return NO_CHAIN  # type: ignore[return-value]


def _lower_remaining_chain(
    ctx: TreeSitterEmitContext,
    base_reg: Register,
    remaining: list[str],
    node: object,
) -> Register:
    """Emit LoadField for each segment after the type join point."""
    reg = base_reg
    for segment in remaining:
        next_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=next_reg,
                obj_reg=reg,
                field_name=FieldName(segment),
            ),
            node=node,
        )
        reg = next_reg
    return reg


class JavaNamespaceResolver(NamespaceResolver):
    """Java-specific: resolves field_access chains through namespace tree."""

    def __init__(self, tree: NamespaceTree) -> None:
        self.tree = tree

    def try_resolve_field_access(
        self, ctx: TreeSitterEmitContext, node: object
    ) -> Register | _NoResolution:
        chain = _collect_field_access_chain(ctx, node)
        if chain is NO_CHAIN:
            return NO_RESOLUTION  # type: ignore[return-value]

        root = chain[0]  # type: ignore[index]
        if root in ctx._method_declared_names:
            return NO_RESOLUTION  # type: ignore[return-value]

        ns_type, remaining, qualified_name = self.tree.resolve(chain)  # type: ignore[arg-type]
        if ns_type is None:
            return NO_RESOLUTION  # type: ignore[return-value]

        # Emit LoadVar for the resolved type's short name
        type_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadVar(result_reg=type_reg, name=VarName(ns_type.short_name)),
            node=node,
        )
        return _lower_remaining_chain(ctx, type_reg, remaining, node)
