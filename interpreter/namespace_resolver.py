# interpreter/namespace_resolver.py
"""Base namespace resolver and sentinel objects.

Separated from namespace.py to avoid circular imports — this module
has no dependency on project.types or frontends.
"""

from typing import TYPE_CHECKING

from interpreter.register import Register

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext


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


NO_RESOLUTION: "_NoResolution | Register" = _NoResolution()
NO_CHAIN: "_NoChain | list[str]" = _NoChain()


class NamespaceResolver:
    """Base: no-op resolver for languages without namespace resolution."""

    def try_resolve_field_access(
        self, ctx: "TreeSitterEmitContext | None", node: object
    ) -> "Register | _NoResolution":
        return NO_RESOLUTION  # type: ignore[return-value]
