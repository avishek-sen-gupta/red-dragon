# pyright: standard
"""TypeScript type alias extractor — extracts simple scalar type aliases from TS ASTs."""

from __future__ import annotations

from typing import Any

from interpreter.frontends.type_extraction import normalize_type_hint
from interpreter.type_name import TypeName
from interpreter.types.type_expr import TypeExpr

_TYPE_ALIAS_DECLARATION = "type_alias_declaration"
_SCALAR_VALUE_NODES = frozenset({"predefined_type", "type_identifier"})


class TypeScriptTypeAliasExtractor:
    """Matches ``type_alias_declaration`` nodes for simple scalar type aliases.

    TS uses the ``value`` field (not ``type``) for the RHS of a type alias.
    Only matches ``predefined_type`` and ``type_identifier`` — ignores generics,
    union types, intersection types, etc.
    """

    def matches(self, node: Any) -> bool:
        if node.type != _TYPE_ALIAS_DECLARATION:
            return False
        value_node = node.child_by_field_name("value")
        return value_node is not None and value_node.type in _SCALAR_VALUE_NODES

    def extract(self, node: Any, type_map: dict[str, str]) -> tuple[TypeName, TypeExpr]:
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        alias_name = name_node.text.decode()
        raw_type = value_node.text.decode()
        return TypeName(alias_name), normalize_type_hint(raw_type, type_map)
