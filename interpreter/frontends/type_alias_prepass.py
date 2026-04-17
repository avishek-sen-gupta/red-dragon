# pyright: standard
"""Type alias prepass infrastructure — Protocol-based, language-agnostic walker.

Frontends that support type aliases (Go, Rust, TypeScript, C, …) inject a
language-specific ``TypeAliasExtractor`` into ``BaseFrontend`` before lowering.
The prepass walks the raw tree-sitter AST once, collects alias mappings, and
seeds them into the ``TypeEnvironmentBuilder`` so that ``_resolve_alias`` in
``type_inference.py`` can expand them transitively.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from interpreter.type_name import TypeName
from interpreter.types.type_expr import TypeExpr


@runtime_checkable
class TypeAliasExtractor(Protocol):
    """Protocol for language-specific type alias extraction from an AST node."""

    def matches(self, node: Any) -> bool:
        """Return True if *node* declares a type alias in this language."""
        ...

    def extract(
        self,
        node: Any,
        type_map: dict[str, str],
    ) -> tuple[TypeName, TypeExpr]:
        """Extract the alias name and target type from *node*.

        Called only when ``matches(node)`` returned True.
        ``type_map`` maps language type names to canonical IR type names.
        """
        ...


class NullTypeAliasExtractor:
    """Null-object implementation — never matches, extract() must never be called."""

    def matches(self, node: Any) -> bool:
        return False

    def extract(
        self,
        node: Any,
        type_map: dict[str, str],
    ) -> tuple[TypeName, TypeExpr]:
        raise AssertionError(
            "extract() called on NullTypeAliasExtractor — "
            "matches() should have prevented this"
        )


def collect_type_aliases(
    root: Any,
    extractor: TypeAliasExtractor,
    type_map: dict[str, str],
) -> dict[TypeName, TypeExpr]:
    """Walk *root* tree-sitter AST and collect all type alias declarations.

    Returns a mapping from alias name (``TypeName``) to resolved target
    ``TypeExpr``.  Order is depth-first, left-to-right — later aliases
    overwrite earlier ones for the same name.
    """
    result: dict[TypeName, TypeExpr] = {}
    _walk(root, extractor, type_map, result)
    return result


def _walk(
    node: Any,
    extractor: TypeAliasExtractor,
    type_map: dict[str, str],
    result: dict[TypeName, TypeExpr],
) -> None:
    if extractor.matches(node):
        name, expr = extractor.extract(node, type_map)
        result[name] = expr
    for child in node.children:
        _walk(child, extractor, type_map, result)
