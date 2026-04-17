# pyright: standard
"""Go type alias extractor — extracts simple scalar type aliases from Go ASTs."""

from __future__ import annotations

from typing import Any

from interpreter.frontends.go.node_types import GoNodeType
from interpreter.frontends.type_extraction import normalize_type_hint
from interpreter.type_name import TypeName
from interpreter.types.type_expr import TypeExpr


class GoTypeAliasExtractor:
    """Matches ``type_spec`` nodes that define simple scalar type aliases.

    Ignores struct and interface type specs — those are class definitions,
    not aliases.
    """

    def matches(self, node: Any) -> bool:
        if node.type != GoNodeType.TYPE_SPEC:
            return False
        type_node = node.child_by_field_name("type")
        return type_node is not None and type_node.type == GoNodeType.TYPE_IDENTIFIER

    def extract(self, node: Any, type_map: dict[str, str]) -> tuple[TypeName, TypeExpr]:
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")
        alias_name = name_node.text.decode()
        raw_type = type_node.text.decode()
        return TypeName(alias_name), normalize_type_hint(raw_type, type_map)
