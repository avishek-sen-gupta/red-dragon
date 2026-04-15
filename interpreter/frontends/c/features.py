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
    FUNCTION_CALL = auto()
    CAST = auto()
    ADDRESS_OF = auto()
    POINTER_DEREFERENCE = auto()
    POINTER_STORE = auto()
    SIZEOF = auto()
    COMPOUND_LITERAL = auto()
    ARRAY_ACCESS = auto()
    CHAR_LITERAL = auto()

    # Field access
    FIELD_ACCESS = auto()
    ARROW_OPERATOR = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    DO_WHILE = auto()
    SWITCH = auto()
    GOTO = auto()
    RETURN = auto()

    # Initialization
    INITIALIZER_LIST = auto()
    DESIGNATED_INITIALIZER = auto()

    # Assignment
    ASSIGNMENT = auto()

    # Pointers and types
    FUNCTION_POINTER = auto()
    POINTER_TYPE = auto()

    # Preprocessor
    PREPROCESSOR = auto()
    MACRO = auto()

    # Infrastructure
    ENTRY_LABEL = auto()
