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
    GENERIC_TYPES = auto()

    # Type narrowing
    TYPE_ASSERTION = auto()
    NON_NULL_ASSERTION = auto()
    SATISFIES_EXPRESSION = auto()

    # Declarations
    VARIABLE_DECLARATION = auto()
    FUNCTION_DECLARATION = auto()
    CLASS = auto()

    # Expressions
    ARITHMETIC = auto()
    OPTIONAL_CHAIN = auto()
    INSTANCEOF = auto()

    # Functions
    FUNCTION_OVERLOAD = auto()
    AMBIENT_DECLARATION = auto()
    INSTANTIATION_EXPRESSION = auto()

    # Control flow
    IF_ELSE = auto()
    FOR_LOOP = auto()
    WHILE_LOOP = auto()

    # Classes & OOP
    INHERITANCE = auto()
    INTERFACE_IMPLEMENTATION = auto()
    ABSTRACT_CLASS = auto()
    ABSTRACT_METHOD = auto()
    CLASS_STATIC_BLOCK = auto()
    PUBLIC_FIELD = auto()

    # Access modifiers
    PUBLIC_MODIFIER = auto()
    PRIVATE_MODIFIER = auto()
    PROTECTED_MODIFIER = auto()
    READONLY_MODIFIER = auto()
    STATIC_MODIFIER = auto()

    # Modules & Namespaces
    NAMESPACE = auto()
    IMPORT = auto()
    EXPORT = auto()
    IMPORT_ALIAS = auto()
    REQUIRE_IMPORT = auto()
