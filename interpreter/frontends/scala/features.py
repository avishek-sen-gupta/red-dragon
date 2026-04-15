# pyright: standard
"""Semantic feature enumeration for the Scala language frontend.

Each member represents a distinct language-level feature that the Scala
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum, auto


class ScalaFeature(Enum):
    """Semantic features of the Scala language."""

    # Declarations
    VAL_DECLARATION = auto()
    VAR_DECLARATION = auto()
    VAR_ASSIGNMENT = auto()
    LAZY_VAL = auto()
    FUNCTION_DECLARATION = auto()
    CLASS = auto()
    OBJECT = auto()
    TRAIT = auto()
    CASE_CLASS = auto()
    TYPE_ALIAS = auto()

    # Expressions
    BINARY_OPERATION = auto()
    INFIX_EXPRESSION = auto()
    BLOCK_EXPRESSION = auto()
    FIELD_ACCESS = auto()
    METHOD_CALL = auto()
    FUNCTION_CALL = auto()
    STRING_LITERAL = auto()
    BOOLEAN_LITERAL = auto()
    NULL_LITERAL = auto()
    STRING_INTERPOLATION = auto()
    GENERIC_FUNCTION = auto()
    POSTFIX_EXPRESSION = auto()
    NEW_EXPRESSION = auto()
    IMPLICIT_RETURN = auto()

    # Control flow
    IF_EXPRESSION = auto()
    IF_ELSEIF_ELSE = auto()
    WHILE_LOOP = auto()
    DO_WHILE_LOOP = auto()
    FOR_COMPREHENSION = auto()
    MATCH_EXPRESSION = auto()
    THROW_EXPRESSION = auto()

    # Patterns and destructuring
    LITERAL_PATTERN = auto()
    WILDCARD_PATTERN = auto()
    CAPTURE_PATTERN = auto()
    ALTERNATIVE_PATTERN = auto()
    TUPLE_PATTERN = auto()
    CASE_CLASS_PATTERN = auto()
    TYPED_PATTERN = auto()
    VALUE_PATTERN = auto()
    TUPLE_DESTRUCTURING = auto()

    # Generics and advanced features
    STABLE_TYPE_IDENTIFIER = auto()
    PRIMARY_CONSTRUCTOR = auto()

    # Infrastructure
    SOURCE_LOCATION = auto()
