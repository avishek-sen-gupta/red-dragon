# pyright: standard
"""Semantic feature enumeration for the C++ language frontend.

Each member represents a distinct language-level feature that the C++
frontend can lower to IR.  Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum, auto


class CppFeature(Enum):
    """Semantic features of the C++ language."""

    # Basic declarations
    VARIABLE_DECLARATION = auto()
    DECLARATION_WITHOUT_INITIALIZER = auto()

    # Functions
    FUNCTION_DEFINITION = auto()
    FUNCTION_CALL = auto()
    RETURN_STATEMENT = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    IF_ELSEIF_CHAIN = auto()

    # Classes and objects
    CLASS_DEFINITION = auto()
    CLASS_WITH_METHODS = auto()
    CLASS_WITH_CONSTRUCTOR = auto()
    CLASS_WITH_FIELD_INITIALIZERS = auto()
    FIELD_INITIALIZER_LIST = auto()
    FIELD_INITIALIZER_SINGLE = auto()

    # Namespaces
    NAMESPACE = auto()

    # Expressions
    NEW_EXPRESSION = auto()
    DELETE_EXPRESSION = auto()
    DELETE_ARRAY = auto()
    LAMBDA_EXPRESSION = auto()
    LAMBDA_CAPTURE = auto()
    BINARY_EXPRESSION = auto()

    # Templates
    TEMPLATE_DECLARATION = auto()
    TEMPLATE_FUNCTION = auto()

    # Special/Advanced
    EMPTY_PROGRAM = auto()
    UNSUPPORTED_FALLBACK = auto()
    STRING_LITERAL = auto()
    CHAR_LITERAL = auto()

    # Method calls
    METHOD_CALL = auto()

    # Enums
    C_STYLE_ENUM = auto()
    ENUM_CLASS = auto()
    ENUM_CLASS_WITH_VALUES = auto()

    # Exception handling
    TRY_CATCH = auto()

    # Range-based for
    RANGE_FOR = auto()

    # Type casts
    STATIC_CAST = auto()

    # Concepts
    CONCEPT_DEFINITION = auto()

    # Dereferencing
    DEREFERENCE_THIS = auto()
    DEREFERENCE_POINTER = auto()
