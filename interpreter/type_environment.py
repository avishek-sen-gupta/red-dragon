"""TypeEnvironment — immutable result of the static type inference pass."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from interpreter.function_signature import FunctionSignature
from interpreter.type_expr import TypeExpr, UNKNOWN
from interpreter.var_scope_info import VarScopeInfo

_NULL_SIGNATURE = FunctionSignature(params=(), return_type=UNKNOWN)


@dataclass(frozen=True)
class TypeEnvironment:
    """Maps register and variable names to their inferred canonical types.

    Computed once by ``infer_types()`` before execution.  Read-only during
    execution — the executor looks up operand types from here.

    Types are stored as ``TypeExpr`` objects (``ScalarType`` or
    ``ParameterizedType``).  ``TypeExpr`` compares equal to its string
    representation, so ``env.register_types["%0"] == "Int"`` still works.

    register_types: "%0" → ScalarType("Int"), "%4" → ScalarType("Float"), etc.
    var_types:      "x"  → ScalarType("Int"), "ptr" → ParameterizedType("Pointer", ...), etc.
    func_signatures: "add" → [FunctionSignature(...), ...] (list supports overloads)
    """

    register_types: MappingProxyType[str, TypeExpr]
    var_types: MappingProxyType[str, TypeExpr]
    func_signatures: MappingProxyType[str, list[FunctionSignature]]
    type_aliases: MappingProxyType[str, TypeExpr] = MappingProxyType({})
    interface_implementations: MappingProxyType[str, tuple[str, ...]] = (
        MappingProxyType({})
    )
    scoped_var_types: MappingProxyType[str, MappingProxyType[str, TypeExpr]] = (
        MappingProxyType({})
    )
    var_scope_metadata: MappingProxyType[str, VarScopeInfo] = MappingProxyType({})

    def get_func_signature(self, name: str, index: int = 0) -> FunctionSignature:
        """Return the function signature for *name* at overload *index*.

        Defaults to the first (or only) overload.  Returns a null signature
        with ``UNKNOWN`` return type if *name* is absent or *index* is out
        of range.
        """
        sigs = self.func_signatures.get(name, [])
        return sigs[index] if index < len(sigs) else _NULL_SIGNATURE
