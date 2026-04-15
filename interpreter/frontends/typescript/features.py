# pyright: standard
"""Semantic feature enumeration for the TypeScript language frontend."""

from __future__ import annotations

from enum import Enum, auto


class TypeScriptFeature(Enum):
    """Semantic features of the TypeScript language (beyond JavaScript)."""

    # Type system
    TYPE_ANNOTATION = auto()
    TYPE_ALIAS = auto()
    INTERFACE = auto()
    ENUM = auto()

    # Type narrowing
    TYPE_ASSERTION = auto()
    NON_NULL_ASSERTION = auto()

    # Declarations
    VARIABLE_DECLARATION = auto()
    FUNCTION_DECLARATION = auto()
    CLASS = auto()

    # Expressions
    OPTIONAL_CHAIN = auto()

    # Functions
    FUNCTION_OVERLOAD = auto()
    AMBIENT_DECLARATION = auto()
    INSTANTIATION_EXPRESSION = auto()

    # Control flow
    IF_ELSE = auto()
    FOR_LOOP = auto()
    WHILE_LOOP = auto()
