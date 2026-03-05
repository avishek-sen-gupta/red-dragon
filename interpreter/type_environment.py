"""TypeEnvironment — immutable result of the static type inference pass."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class TypeEnvironment:
    """Maps register and variable names to their inferred canonical types.

    Computed once by ``infer_types()`` before execution.  Read-only during
    execution — the executor looks up operand types from here.

    register_types: "%0" → "Int", "%4" → "Float", etc.
    var_types:      "x"  → "Int", "name" → "String", etc.
    """

    register_types: MappingProxyType[str, str]
    var_types: MappingProxyType[str, str]
