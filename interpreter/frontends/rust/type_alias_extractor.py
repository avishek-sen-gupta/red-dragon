# pyright: standard
"""Rust type alias extractor — extracts simple scalar type aliases from Rust ASTs."""

from __future__ import annotations

from typing import Any

from interpreter.frontends.rust.node_types import RustNodeType
from interpreter.frontends.type_extraction import normalize_type_hint
from interpreter.type_name import TypeName
from interpreter.types.type_expr import TypeExpr


class RustTypeAliasExtractor:
    """Matches ``type_item`` nodes that define simple scalar type aliases.

    Ignores generic type aliases (e.g. ``type Pair<T> = (T, T)``) — only
    handles plain scalar aliases like ``type UserId = i32``.
    """

    _SCALAR_TYPE_NODES = frozenset({"primitive_type", RustNodeType.TYPE_IDENTIFIER})

    def matches(self, node: Any) -> bool:
        if node.type != RustNodeType.TYPE_ITEM:
            return False
        type_node = node.child_by_field_name("type")
        return type_node is not None and type_node.type in self._SCALAR_TYPE_NODES

    def extract(self, node: Any, type_map: dict[str, str]) -> tuple[TypeName, TypeExpr]:
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")
        alias_name = name_node.text.decode()
        raw_type = type_node.text.decode()
        return TypeName(alias_name), normalize_type_hint(raw_type, type_map)
