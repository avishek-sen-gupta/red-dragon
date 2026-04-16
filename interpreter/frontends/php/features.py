# pyright: standard
"""Semantic feature enumeration for the PHP language frontend."""

from __future__ import annotations

from enum import Enum, auto


class PhpFeature(Enum):
    """Semantic features of the PHP language."""

    # Declarations
    VARIABLE_ASSIGNMENT = auto()
    FUNCTION_DECLARATION = auto()
    CLASS = auto()
    INTERFACE = auto()
    TRAIT = auto()
    ENUM = auto()
    NAMESPACE = auto()
    USE_DECLARATION = auto()

    # Expressions
    ARITHMETIC = auto()
    ASSIGNMENT_EXPRESSION = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    MEMBER_ACCESS = auto()
    NULLSAFE_MEMBER_ACCESS = auto()
    SCOPED_CALL = auto()
    SCOPED_PROPERTY_ACCESS = auto()
    CLASS_CONSTANT_ACCESS = auto()
    ARROW_FUNCTION = auto()
    ANONYMOUS_FUNCTION = auto()
    ARRAY_CREATION = auto()
    STRING_INTERPOLATION = auto()
    HEREDOC = auto()
    YIELD = auto()
    VARIADIC_UNPACKING = auto()
    DYNAMIC_VARIABLE = auto()
    REFERENCE_ASSIGNMENT = auto()
    RELATIVE_SCOPE = auto()
    TYPE_CAST = auto()
    TERNARY = auto()
    OBJECT_CREATION = auto()
    CLONE = auto()
    ERROR_SUPPRESSION = auto()
    SEQUENCE_EXPRESSION = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    FOREACH = auto()
    SWITCH_STATEMENT = auto()
    DO_WHILE = auto()
    MATCH_EXPRESSION = auto()
    RETURN = auto()
    THROW = auto()
    GOTO = auto()
    LABELED_STATEMENT = auto()
    TRY_CATCH_FINALLY = auto()

    # OOP
    PROPERTY_DECLARATION = auto()

    # Misc
    ECHO = auto()
    STATIC_DECLARATION = auto()
    GLOBAL_DECLARATION = auto()
    INCLUDE_REQUIRE = auto()
    ENUM_CASE = auto()
    PRINT = auto()
    FALLBACK = auto()
    CONST_DECLARATION = auto()
    NAMESPACE_USE = auto()
