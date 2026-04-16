# pyright: standard
"""Semantic feature enumeration for the Lua language frontend."""

from __future__ import annotations

from enum import Enum, auto


class LuaFeature(Enum):
    """Semantic features of the Lua language."""

    # Declarations
    LOCAL_VARIABLE_DECLARATION = auto()
    ASSIGNMENT = auto()
    FUNCTION_DECLARATION = auto()
    DOTTED_FUNCTION_DECLARATION = auto()
    ANONYMOUS_FUNCTION = auto()

    # Expressions
    ARITHMETIC = auto()
    OPERATORS = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    METHOD_INDEX_EXPRESSION = auto()
    DOTTED_FUNCTION_CALL = auto()
    VARARG = auto()
    BITWISE_XOR = auto()

    # Tables
    TABLE_CONSTRUCTOR = auto()
    TABLE_ACCESS = auto()

    # Control flow
    IF_ELSE = auto()
    WHILE_LOOP = auto()
    FOR_LOOP = auto()
    REPEAT_UNTIL = auto()
    GENERIC_FOR = auto()
    BREAK = auto()
    GOTO = auto()
    LABEL = auto()
    DO_BLOCK = auto()

    # Strings
    STRING_ESCAPE = auto()
