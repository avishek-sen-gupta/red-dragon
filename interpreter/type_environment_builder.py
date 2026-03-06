"""TypeEnvironmentBuilder — mutable accumulator for type seeds from frontends.

Frontends populate this during lowering; ``infer_types()`` receives it
as pre-seeded state, continues adding inferred types, and calls
``.build()`` to produce the frozen ``TypeEnvironment``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import MappingProxyType

from interpreter.function_signature import FunctionSignature
from interpreter.type_environment import TypeEnvironment

logger = logging.getLogger(__name__)


@dataclass
class TypeEnvironmentBuilder:
    """Mutable accumulator that frontends populate during lowering."""

    register_types: dict[str, str] = field(default_factory=dict)
    var_types: dict[str, str] = field(default_factory=dict)
    func_return_types: dict[str, str] = field(default_factory=dict)
    func_param_types: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def build(self) -> TypeEnvironment:
        """Freeze accumulated type info into an immutable TypeEnvironment."""
        func_signatures = _build_func_signatures(self)
        return TypeEnvironment(
            register_types=MappingProxyType(dict(self.register_types)),
            var_types=MappingProxyType(dict(self.var_types)),
            func_signatures=MappingProxyType(func_signatures),
        )


def _build_func_signatures(
    builder: TypeEnvironmentBuilder,
) -> dict[str, FunctionSignature]:
    """Build signatures keyed only by user-facing function names.

    Internal labels (func_add_0) are excluded — only names that came
    through a <function:name@label> CONST mapping are included.
    """
    user_facing_names = {
        name
        for name in set(builder.func_return_types) | set(builder.func_param_types)
        if not name.startswith("func_")
    }

    return {
        name: FunctionSignature(
            params=tuple(builder.func_param_types.get(name, [])),
            return_type=builder.func_return_types.get(name, ""),
        )
        for name in user_facing_names
    }
