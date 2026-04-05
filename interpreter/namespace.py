# interpreter/namespace.py
"""Namespace tree for resolving qualified references (e.g. java.util.Arrays).

The tree maps dotted package paths to type nodes. The resolution algorithm
is shared across languages; language-specific behavior comes from the seed
(what's in the tree), not the walk (how we traverse it).

Re-exports NamespaceResolver, NO_RESOLUTION, NO_CHAIN from namespace_resolver
so existing consumers can import from this single module.
"""

from dataclasses import dataclass, field

from interpreter.project.types import ModuleUnit, NO_MODULE_UNIT
from interpreter.refs.class_ref import ClassRef, NO_CLASS_REF

# Re-export for convenience — consumers can import from interpreter.namespace
from interpreter.namespace_resolver import (  # noqa: F401
    NamespaceResolver,
    NO_RESOLUTION,
    NO_CHAIN,
    _NoResolution,
    _NoChain,
)


@dataclass
class NamespaceType:
    """A type reachable through namespace resolution."""

    short_name: str  # "Arrays" — used by frontend for LoadVar
    class_ref: ClassRef = NO_CLASS_REF  # sentinel initially; patched post-compile
    module: ModuleUnit = NO_MODULE_UNIT  # stub ModuleUnit, if one exists


@dataclass
class NamespaceNode:
    """A node in the package/namespace hierarchy."""

    children: dict[str, "NamespaceNode"] = field(default_factory=dict)
    types: dict[str, NamespaceType] = field(default_factory=dict)


class NamespaceTree:
    """Package → Type mapping consulted during frontend lowering.

    Resolution algorithm (mirrors JLS §6.5): walk segments from root,
    descending into child namespaces until a type node is found. Returns
    the type, any remaining chain segments, and the qualified name.
    """

    def __init__(self) -> None:
        self.root = NamespaceNode()

    def resolve(
        self, chain: list[str]
    ) -> tuple["NamespaceType | None", list[str], str]:
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
