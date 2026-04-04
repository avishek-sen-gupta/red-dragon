# interpreter/frontends/java/namespace.py
"""Java-specific namespace resolution: pre-scan, tree builder, resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from interpreter.parser import TreeSitterParserFactory
from interpreter.project.types import ImportRef

if TYPE_CHECKING:
    pass

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
