"""TypeEnvironment — immutable result of the static type inference pass."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

from interpreter.func_name import FuncName
from interpreter.register import Register
from interpreter.types.function_signature import FunctionSignature
from interpreter.types.type_expr import TypeExpr, UNBOUND, UNKNOWN
from interpreter.types.var_scope_info import VarScopeInfo
from interpreter.var_name import VarName

_NULL_SIGNATURE = FunctionSignature(params=(), return_type=UNKNOWN)


@dataclass(frozen=True)
class TypeEnvironment:
    """Maps register and variable names to their inferred canonical types.

    Computed once by ``infer_types()`` before execution.  Read-only during
    execution — the executor looks up operand types from here.

    Types are stored as ``TypeExpr`` objects (``ScalarType`` or
    ``ParameterizedType``).  ``TypeExpr`` compares equal to its string
    representation, so ``env.register_types[Register("%0")] == "Int"`` works.

    register_types: Register("%0") → ScalarType("Int"), Register("%4") → ScalarType("Float"), etc.
    var_types:      "x"  → ScalarType("Int"), "ptr" → ParameterizedType("Pointer", ...), etc.
    method_signatures: TypeExpr → {"name" → [FunctionSignature(...), ...]}
        Unified container for all signatures. Class methods keyed by class
        TypeExpr (e.g. ScalarType("Dog")), standalone functions keyed by UNKNOWN.
    """

    register_types: MappingProxyType[Register, TypeExpr]
    var_types: MappingProxyType[VarName, TypeExpr]
    method_signatures: MappingProxyType[
        TypeExpr, MappingProxyType[FuncName, list[FunctionSignature]]
    ] = MappingProxyType({})
    type_aliases: MappingProxyType[str, TypeExpr] = MappingProxyType({})
    interface_implementations: MappingProxyType[str, tuple[str, ...]] = (
        MappingProxyType({})
    )
    scoped_var_types: MappingProxyType[str, MappingProxyType[VarName, TypeExpr]] = (
        MappingProxyType({})
    )
    var_scope_metadata: MappingProxyType[str, VarScopeInfo] = MappingProxyType({})

    def get_func_signature(
        self,
        name: FuncName,
        index: int = 0,
        class_name: TypeExpr = UNBOUND,
    ) -> FunctionSignature:
        """Return the function signature for *name* at overload *index*.

        Looks up in ``method_signatures`` under *class_name*.  For standalone
        functions, *class_name* defaults to ``UNBOUND``.

        Defaults to the first (or only) overload.  Returns a null signature
        with ``UNKNOWN`` return type if *name* is absent or *index* is out
        of range.
        """
        class_methods = self.method_signatures.get(class_name, {})
        sigs = class_methods.get(name, [])
        return sigs[index] if index < len(sigs) else _NULL_SIGNATURE
