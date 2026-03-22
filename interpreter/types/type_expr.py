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


UNBOUND = ScalarType("__unbound__")
"""Sentinel key for standalone/top-level function signatures in method_signatures."""


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


@dataclass(frozen=True, eq=False)
class FunctionType(TypeExpr):
    """A function type: ``Fn(Int, String) -> Bool``.

    Params are stored as a tuple of TypeExpr for the parameter types.
    Return type is a single TypeExpr.
    """

    params: tuple[TypeExpr, ...]
    return_type: TypeExpr

    def __str__(self) -> str:
        params_str = ", ".join(str(p) for p in self.params)
        return f"Fn({params_str}) -> {self.return_type}"


@dataclass(frozen=True, eq=False)
class UnionType(TypeExpr):
    """A union of two or more types: ``Union[Int, String]``.

    Members are stored as a frozenset for order-independent equality.
    The canonical string uses alphabetically sorted member names.
    Use ``union_of()`` to construct — it handles flattening, dedup,
    and singleton elimination.
    """

    members: frozenset[TypeExpr]

    def __str__(self) -> str:
        sorted_members = sorted(str(m) for m in self.members)
        return f"Union[{', '.join(sorted_members)}]"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UnionType):
            return self.members == other.members
        if isinstance(other, str):
            return str(self) == other
        if isinstance(other, TypeExpr):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash(str(self))


@dataclass(frozen=True, eq=False)
class TypeVar(TypeExpr):
    """A type variable with an optional upper bound: ``T``, ``T: Number``.

    Represents generic type parameters like Java's ``<T extends Number>``.
    The bound defaults to ``UNKNOWN`` (unbounded, effectively ``Any``).
    """

    name: str
    bound: TypeExpr = UNKNOWN

    def __str__(self) -> str:
        if self.bound:
            return f"{self.name}: {self.bound}"
        return self.name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TypeVar):
            return self.name == other.name and self.bound == other.bound
        if isinstance(other, str):
            return str(self) == other
        if isinstance(other, TypeExpr):
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


def typevar(name: str, bound: TypeExpr = UNKNOWN) -> TypeVar:
    """Create a type variable, optionally with an upper bound."""
    return TypeVar(name=name, bound=bound)


def fn_type(params: list[TypeExpr], ret: TypeExpr) -> FunctionType:
    """Create a ``Fn(params...) -> ret`` function type."""
    return FunctionType(params=tuple(params), return_type=ret)


def tuple_of(*elements: TypeExpr) -> ParameterizedType:
    """Create a ``Tuple[elements...]`` type."""
    return ParameterizedType("Tuple", tuple(elements))


def metatype(class_type: TypeExpr) -> ParameterizedType:
    """Create a ``Type[ClassName]`` metatype — the type of a class constructor."""
    return ParameterizedType("Type", (class_type,))


def union_of(*types: TypeExpr) -> TypeExpr:
    """Create a union type, with flattening, dedup, and singleton elimination.

    - Nested unions are flattened: ``union_of(Union[A, B], C)`` → ``Union[A, B, C]``
    - Duplicates removed: ``union_of(Int, Int)`` → ``Int``
    - Singleton: ``union_of(Int)`` → ``ScalarType("Int")``
    - Empty: ``union_of()`` → ``UNKNOWN``
    - UNKNOWN members are filtered out
    """
    members: set[TypeExpr] = set()
    for t in types:
        if isinstance(t, UnionType):
            members.update(t.members)
        elif t and not isinstance(t, UnknownType):
            members.add(t)
    if not members:
        return UNKNOWN
    if len(members) == 1:
        return next(iter(members))
    return UnionType(frozenset(members))


_NULL = ScalarType("Null")


def optional(inner: TypeExpr) -> TypeExpr:
    """Create ``Optional[inner]`` = ``Union[inner, Null]``."""
    return union_of(inner, _NULL)


def is_optional(t: TypeExpr) -> bool:
    """Return True if *t* is a union containing Null."""
    return isinstance(t, UnionType) and _NULL in t.members


def unwrap_optional(t: TypeExpr) -> TypeExpr:
    """Remove Null from a union type. Non-optional types returned as-is."""
    if not isinstance(t, UnionType):
        return t
    remaining = t.members - {_NULL}
    if not remaining:
        return UNKNOWN
    if len(remaining) == 1:
        return next(iter(remaining))
    return UnionType(frozenset(remaining))


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
    if name == "Fn" and pos < len(s) and s[pos] == "(":
        return _parse_function_type(s, pos)
    if pos < len(s) and s[pos] == "[":
        args, pos = _parse_args(s, pos + 1)
        if name == "Union":
            return union_of(*args), pos
        if name == "Optional":
            return (optional(args[0]), pos) if args else (UNKNOWN, pos)
        return ParameterizedType(name, tuple(args)), pos
    return ScalarType(name), pos


def _parse_name(s: str, pos: int) -> tuple[str, int]:
    """Consume an identifier (everything up to ``[``, ``]``, ``,``, ``(``, ``)``, or end)."""
    start = pos
    while pos < len(s) and s[pos] not in ("[", "]", ",", "(", ")"):
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


def _parse_function_type(s: str, pos: int) -> tuple[FunctionType, int]:
    """Parse ``Fn(param_types...) -> return_type`` starting after 'Fn' at the '('."""
    # pos points to '('
    pos += 1  # skip '('
    params: list[TypeExpr] = []
    while pos < len(s):
        # skip whitespace
        while pos < len(s) and s[pos] == " ":
            pos += 1
        if s[pos] == ")":
            pos += 1  # skip ')'
            break
        if s[pos] == ",":
            pos += 1
            while pos < len(s) and s[pos] == " ":
                pos += 1
            continue
        expr, pos = _parse_expr(s, pos)
        params.append(expr)
    # skip " -> "
    while pos < len(s) and s[pos] == " ":
        pos += 1
    if pos + 1 < len(s) and s[pos : pos + 2] == "->":
        pos += 2
    while pos < len(s) and s[pos] == " ":
        pos += 1
    ret_type, pos = _parse_expr(s, pos)
    return FunctionType(params=tuple(params), return_type=ret_type), pos
