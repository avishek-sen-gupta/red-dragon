# interpreter/namespace.py
"""Namespace tree for resolving qualified references (e.g. java.util.Arrays).

The tree maps dotted package paths to type nodes. The resolution algorithm
is shared across languages; language-specific behavior comes from the seed
(what's in the tree), not the walk (how we traverse it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from interpreter.refs.class_ref import ClassRef, NO_CLASS_REF
from interpreter.register import Register

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext
    from interpreter.project.types import ModuleUnit


@dataclass
class NamespaceType:
    """A type reachable through namespace resolution."""

    short_name: str  # "Arrays" — used by frontend for LoadVar
    class_ref: ClassRef = NO_CLASS_REF  # sentinel initially; patched post-compile
    module: ModuleUnit | None = None  # stub ModuleUnit, if one exists


@dataclass
class NamespaceNode:
    """A node in the package/namespace hierarchy."""

    children: dict[str, NamespaceNode] = field(default_factory=dict)
    types: dict[str, NamespaceType] = field(default_factory=dict)


class NamespaceTree:
    """Package → Type mapping consulted during frontend lowering.

    Resolution algorithm (mirrors JLS §6.5): walk segments from root,
    descending into child namespaces until a type node is found. Returns
    the type, any remaining chain segments, and the qualified name.
    """

    def __init__(self) -> None:
        self.root = NamespaceNode()

    def resolve(self, chain: list[str]) -> tuple[NamespaceType | None, list[str], str]:
        """Walk the tree to find the type join point.

        Returns:
            (resolved_type, remaining_chain, qualified_name)
            or (None, original_chain, "") if no match.
        """
        if not chain:
            return None, chain, ""
        node = self.root
        for i, segment in enumerate(chain):
            if segment in node.types:
                qualified = ".".join(chain[: i + 1])
                return node.types[segment], chain[i + 1 :], qualified
            if segment in node.children:
                node = node.children[segment]
                continue
            break
        return None, chain, ""

    def register_type(self, dotted_path: str, ns_type: NamespaceType) -> None:
        """Register a type at the given dotted path.

        E.g. register_type("java.util.Arrays", ...) creates java → util
        namespace nodes and registers Arrays as a type under util.
        """
        parts = dotted_path.split(".")
        node = self.root
        for part in parts[:-1]:
            if part not in node.children:
                node.children[part] = NamespaceNode()
            node = node.children[part]
        node.types[parts[-1]] = ns_type


class _NoResolution:
    """Sentinel: resolver did not handle this field_access."""

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NO_RESOLUTION"


class _NoChain:
    """Sentinel: node isn't a pure identifier chain."""

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NO_CHAIN"


NO_RESOLUTION: _NoResolution | Register = _NoResolution()
NO_CHAIN: _NoChain | list[str] = _NoChain()


class NamespaceResolver:
    """Base: no-op resolver for languages without namespace resolution."""

    def try_resolve_field_access(
        self, ctx: TreeSitterEmitContext | None, node: object
    ) -> Register | _NoResolution:
        return NO_RESOLUTION  # type: ignore[return-value]
