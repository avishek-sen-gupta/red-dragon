# pyright: standard
"""Semantic feature enumeration for the Kotlin language frontend."""

from __future__ import annotations

from enum import Enum, auto


class KotlinFeature(Enum):
    """Semantic features of the Kotlin language."""

    # Declarations
    VAL_DECLARATION = auto()
    VAR_DECLARATION = auto()
    FUNCTION_DECLARATION = auto()
    CLASS = auto()
    INTERFACE = auto()
    OBJECT_DECLARATION = auto()
    OBJECT_LITERAL = auto()
    COMPANION_OBJECT = auto()
    ENUM_CLASS = auto()
    TYPE_ALIAS = auto()

    # Constructors and properties
    PRIMARY_CONSTRUCTOR = auto()
    SECONDARY_CONSTRUCTOR = auto()
    PROPERTY_ACCESSOR = auto()
    SETTER = auto()

    # Expressions
    ARITHMETIC = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    NAVIGATION_EXPRESSION = auto()
    LAMBDA = auto()
    ANONYMOUS_FUNCTION = auto()
    STRING_INTERPOLATION = auto()
    TEMPLATE_STRING = auto()
    CALLABLE_REFERENCE = auto()
    RANGE_EXPRESSION = auto()
    INFIX_EXPRESSION = auto()
    INDEXING = auto()
    SPREAD = auto()
    CHECK_EXPRESSION = auto()  # is/!is type checks
    TYPE_TEST = auto()
    AS_EXPRESSION = auto()
    ELVIS_EXPRESSION = auto()
    NOT_NULL_ASSERTION = auto()
    THROW_EXPRESSION = auto()
    BITWISE = auto()
    CHAR_LITERAL = auto()
    HEX_LITERAL = auto()
    UNSIGNED_LITERAL = auto()
    NULL_LITERAL = auto()

    # Control flow
    IF_EXPRESSION = auto()
    WHEN_EXPRESSION = auto()
    WHEN_STATEMENT = auto()
    WHILE_LOOP = auto()
    DO_WHILE_LOOP = auto()
    FOR_LOOP = auto()
    RETURN = auto()
    LABELED_STATEMENT = auto()

    # Type system
    GENERIC_TYPES = auto()
    DESTRUCTURING = auto()

    # Misc
    WILDCARD_IMPORT = auto()
    LINE_COMMENT = auto()
    OVERLOAD_RESOLUTION = auto()
