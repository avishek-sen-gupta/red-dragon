"""TypeEnvironment — immutable result of the static type inference pass."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from interpreter.function_signature import FunctionSignature
from interpreter.type_expr import TypeExpr


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
    func_signatures: "add" → FunctionSignature(params=..., return_type=ScalarType("Int"))
    """

    register_types: MappingProxyType[str, TypeExpr]
    var_types: MappingProxyType[str, TypeExpr]
    func_signatures: MappingProxyType[str, FunctionSignature]
    type_aliases: MappingProxyType[str, TypeExpr] = MappingProxyType({})
