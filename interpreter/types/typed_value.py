"""TypedValue — wraps raw Python values with TypeExpr type metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interpreter.constants import TypeName
from interpreter.types.type_expr import UNKNOWN, TypeExpr, scalar

_PYTHON_TYPE_TO_TYPE_NAME: dict[type, str] = {
    bool: TypeName.BOOL,
    int: TypeName.INT,
    float: TypeName.FLOAT,
    str: TypeName.STRING,
}


def runtime_type_name(val: Any) -> str:
    """Map a Python runtime value to its canonical TypeName.

    bool must be checked before int because ``isinstance(True, int)`` is True.
    Exact type lookup avoids isinstance chains and the bool/int subclass trap.
    Returns empty string for unrecognised types (no coercion will be applied).
    """
    return _PYTHON_TYPE_TO_TYPE_NAME.get(type(val), "")


@dataclass(frozen=True)
class TypedValue:
    """Immutable wrapper pairing a raw value with its declared/inferred type."""

    value: Any
    type: TypeExpr


def typed(value: Any, type_expr: TypeExpr = UNKNOWN) -> TypedValue:
    """Wrap a raw value with type info."""
    return TypedValue(value=value, type=type_expr)


def unwrap(val: Any) -> Any:
    """Unwrap a TypedValue to its raw value; pass-through for non-TypedValue."""
    if isinstance(val, TypedValue):
        return val.value
    return val


def unwrap_locals(local_vars: dict[str, Any]) -> dict[str, Any]:
    """Unwrap all TypedValue entries in a local_vars dict to raw values."""
    return {k: unwrap(v) for k, v in local_vars.items()}


def typed_from_runtime(value: Any) -> TypedValue:
    """Wrap a raw value, inferring type from Python runtime type.

    Uses runtime_type_name to map int->Int, str->String, float->Float, bool->Bool.
    Values with no mapping (list, dict, SymbolicValue, Pointer, None) get UNKNOWN.
    """
    rt = runtime_type_name(value)
    return TypedValue(value=value, type=scalar(rt) if rt else UNKNOWN)
