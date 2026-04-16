# pyright: standard
"""Semantic feature enumeration for the C language frontend.

Each member represents a distinct language-level feature that the C
frontend can lower to IR. Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum, auto


class CFeature(Enum):
    """Semantic features of the C language."""

    # Declarations
    VARIABLE_DECLARATION = auto()
    FUNCTION_DECLARATION = auto()
    STRUCT = auto()
    UNION = auto()
    ENUM = auto()
    TYPEDEF = auto()

    # Expressions
    ARITHMETIC = auto()
    UNARY_OPERATORS = auto()
    BINARY_OPERATORS = auto()
    LOGICAL_OPERATORS = auto()
    FUNCTION_CALL = auto()
    CAST = auto()
    ADDRESS_OF = auto()
    POINTER_DEREFERENCE = auto()
    POINTER_LOAD = auto()
    POINTER_STORE = auto()
    SIZEOF = auto()
    COMPOUND_LITERAL = auto()
    ARRAY_ACCESS = auto()
    CHAR_LITERAL = auto()
    STRING_LITERAL = auto()
    STRING_CONCATENATION = auto()
    TERNARY_OPERATOR = auto()
    COMMA_OPERATOR = auto()
    INCREMENT_DECREMENT = auto()

    # Field access
    FIELD_ACCESS = auto()
    ARROW_OPERATOR = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    DO_WHILE = auto()
    SWITCH = auto()
    DEFAULT_CASE = auto()
    LABELED_STATEMENTS = auto()
    GOTO = auto()
    BREAK_CONTINUE = auto()
    RETURN = auto()

    # Initialization
    INITIALIZER_LIST = auto()
    ARRAY_LITERALS = auto()
    DESIGNATED_INITIALIZER = auto()

    # Assignment
    ASSIGNMENT = auto()

    # Pointers and types
    FUNCTION_POINTER = auto()
    POINTER_TYPE = auto()

    # Preprocessor and linkage
    PREPROCESSOR = auto()
    MACRO = auto()
    MACRO_FUNCTION = auto()
    EXTERN_C = auto()

    # Infrastructure
    ENTRY_LABEL = auto()
