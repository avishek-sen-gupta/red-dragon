"""TypeEnvironmentBuilder — mutable accumulator for type seeds from frontends.

Frontends populate this during lowering; ``infer_types()`` receives it
as pre-seeded state, continues adding inferred types, and calls
``.build()`` to produce the frozen ``TypeEnvironment``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import MappingProxyType

from interpreter.func_name import FuncName
from interpreter.register import Register
from interpreter.types.function_signature import FunctionSignature
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import TypeExpr, UNBOUND, UNKNOWN
from interpreter.types.var_scope_info import VarScopeInfo
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


@dataclass
class TypeEnvironmentBuilder:
    """Mutable accumulator that frontends populate during lowering.

    Stores type information as ``TypeExpr`` objects.  Frontends call
    ``parse_type()`` at the seeding boundary (in ``TreeSitterEmitContext``)
    so that all stored values are already structured ``TypeExpr``.
    """

    register_types: dict[Register, TypeExpr] = field(default_factory=dict)
    var_types: dict[str, TypeExpr] = field(default_factory=dict)
    func_return_types: dict[str, TypeExpr] = field(default_factory=dict)
    func_param_types: dict[str, list[tuple[str, TypeExpr]]] = field(
        default_factory=dict
    )
    type_aliases: dict[str, TypeExpr] = field(default_factory=dict)
    interface_implementations: dict[str, list[str]] = field(default_factory=dict)
    var_scope_metadata: dict[str, VarScopeInfo] = field(default_factory=dict)

    def build(self) -> TypeEnvironment:
        """Freeze accumulated type info into an immutable TypeEnvironment."""
        standalone_sigs = _build_func_signatures(self)
        unified: dict[TypeExpr, MappingProxyType[FuncName, list[FunctionSignature]]] = (
            {}
        )
        if standalone_sigs:
            unified[UNBOUND] = MappingProxyType(standalone_sigs)
        return TypeEnvironment(
            register_types=MappingProxyType(dict(self.register_types)),
            var_types=MappingProxyType(
                {VarName(k): v for k, v in self.var_types.items()}
            ),
            method_signatures=MappingProxyType(unified),
        )


def _build_func_signatures(
    builder: TypeEnvironmentBuilder,
) -> dict[FuncName, list[FunctionSignature]]:
    """Build signatures keyed only by user-facing function names.

    Internal labels (func_add_0) are excluded — only names that came
    through a <function:name@label> CONST mapping are included.

    Each name maps to a list of signatures to support overloads.
    """
    user_facing_names = {
        name
        for name in set(builder.func_return_types) | set(builder.func_param_types)
        if not name.startswith("func_")
    }

    return {
        FuncName(name): [
            FunctionSignature(
                params=tuple(builder.func_param_types.get(name, [])),
                return_type=builder.func_return_types.get(name, UNKNOWN),
            )
        ]
        for name in user_facing_names
    }
