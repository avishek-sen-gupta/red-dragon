"""TypeExpr — algebraic data type for structured type representations.

Supports scalar types (``Int``, ``String``), parameterized types
(``Pointer[Int]``, ``Array[String]``, ``Map[String, Int]``), and
arbitrary nesting (``Pointer[Array[Int]]``).

Every TypeExpr has a canonical string representation via ``__str__``
that round-trips through ``parse_type``.

**String compatibility:** TypeExpr values compare equal to their
string representations (``ScalarType("Int") == "Int"`` is True),
enabling gradual migration from string-based type storage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, eq=False)
class TypeExpr:
    """Base class for all type expressions.

    Subclasses must implement ``__str__``, ``__eq__``, and ``__hash__``.
    All TypeExpr values compare equal to their ``str()`` representation,
    so ``ScalarType("Int") == "Int"`` holds.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TypeExpr):
            return str(self) == str(other)
        if isinstance(other, str):
            return str(self) == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(str(self))

    def __bool__(self) -> bool:
        return bool(str(self))


class UnknownType(TypeExpr):
    """Sentinel for 'type not yet known'.

    Falsy, compares equal to ``""``, and is a singleton via ``UNKNOWN``.
    Use ``unknown()`` as the constructor — it always returns the singleton.
    """

    def __str__(self) -> str:
        return ""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UnknownType):
            return True
        if isinstance(other, str):
            return other == ""
        if isinstance(other, TypeExpr):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash("")

    def __bool__(self) -> bool:
        return False


UNKNOWN = UnknownType()
"""Singleton sentinel for 'type not yet known'."""


@dataclass(frozen=True, eq=False)
class ScalarType(TypeExpr):
    """A simple, non-parameterized type like ``Int`` or ``String``."""

    name: str

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ScalarType):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        if isinstance(other, ParameterizedType):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass(frozen=True, eq=False)
class ParameterizedType(TypeExpr):
    """A type constructor applied to one or more type arguments.

    Examples: ``Pointer[Int]``, ``Map[String, Int]``, ``Array[Pointer[Int]]``.
    """

    constructor: str
    arguments: tuple[TypeExpr, ...]

    def __str__(self) -> str:
        args_str = ", ".join(str(a) for a in self.arguments)
        return f"{self.constructor}[{args_str}]"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ParameterizedType):
            return (
                self.constructor == other.constructor
                and self.arguments == other.arguments
            )
        if isinstance(other, str):
            return str(self) == other
        if isinstance(other, ScalarType):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash(str(self))


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------


def unknown() -> UnknownType:
    """Return the UNKNOWN singleton."""
    return UNKNOWN


def scalar(name: str) -> ScalarType:
    """Create a scalar type."""
    return ScalarType(name)


def pointer(inner: TypeExpr) -> ParameterizedType:
    """Create a ``Pointer[inner]`` type."""
    return ParameterizedType("Pointer", (inner,))


def array_of(element: TypeExpr) -> ParameterizedType:
    """Create an ``Array[element]`` type."""
    return ParameterizedType("Array", (element,))


def map_of(key: TypeExpr, value: TypeExpr) -> ParameterizedType:
    """Create a ``Map[key, value]`` type."""
    return ParameterizedType("Map", (key, value))


# ---------------------------------------------------------------------------
# Parser: string → TypeExpr
# ---------------------------------------------------------------------------


def parse_type(s: str) -> TypeExpr:
    """Parse a canonical type string into a TypeExpr.

    Returns ``UNKNOWN`` for empty strings.  Handles scalar names (``"Int"``),
    single-parameter types (``"Pointer[Int]"``), multi-parameter types
    (``"Map[String, Int]"``), and arbitrary nesting (``"Pointer[Array[Int]]"``).
    """
    if not s:
        return UNKNOWN
    expr, _rest = _parse_expr(s, 0)
    return expr


def _parse_expr(s: str, pos: int) -> tuple[TypeExpr, int]:
    """Parse a single TypeExpr starting at *pos*, returning (expr, next_pos)."""
    name, pos = _parse_name(s, pos)
    if pos < len(s) and s[pos] == "[":
        args, pos = _parse_args(s, pos + 1)
        return ParameterizedType(name, tuple(args)), pos
    return ScalarType(name), pos


def _parse_name(s: str, pos: int) -> tuple[str, int]:
    """Consume an identifier (everything up to ``[``, ``]``, ``,``, or end)."""
    start = pos
    while pos < len(s) and s[pos] not in ("[", "]", ","):
        pos += 1
    return s[start:pos].strip(), pos


def _parse_args(s: str, pos: int) -> tuple[list[TypeExpr], int]:
    """Parse comma-separated type arguments until the closing ``]``."""
    args: list[TypeExpr] = []
    while pos < len(s):
        if s[pos] == "]":
            return args, pos + 1
        if s[pos] == ",":
            pos += 1
            # skip whitespace after comma
            while pos < len(s) and s[pos] == " ":
                pos += 1
            continue
        expr, pos = _parse_expr(s, pos)
        args.append(expr)
    return args, pos
