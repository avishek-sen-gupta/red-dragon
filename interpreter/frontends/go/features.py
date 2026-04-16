# pyright: standard
"""Semantic feature enumeration for the Go language frontend."""

from __future__ import annotations

from enum import Enum, auto


class GoFeature(Enum):
    """Semantic features of the Go language."""

    # Declarations
    SHORT_VAR_DECL = auto()
    VAR_DECLARATION = auto()
    CONST_DECLARATION = auto()
    STRUCT = auto()
    INTERFACE = auto()
    TYPE_ALIAS = auto()

    # Functions
    FUNCTION_DECLARATION = auto()
    METHOD_DECLARATION = auto()
    MULTIPLE_RETURN = auto()
    VARIADIC = auto()

    # Expressions
    ASSIGNMENT = auto()
    ARITHMETIC = auto()
    INC_DEC = auto()
    FUNCTION_CALL = auto()
    METHOD_CALL = auto()
    FIELD_ACCESS = auto()
    INDEXING = auto()
    COMPOSITE_LITERAL = auto()
    TYPE_ASSERTION = auto()
    TYPE_CONVERSION = auto()
    SLICE_EXPRESSION = auto()
    FUNC_LITERAL = auto()
    MAKE = auto()
    RUNE_LITERAL = auto()
    BLANK_IDENTIFIER = auto()
    IOTA = auto()
    CHANNEL_TYPE = auto()
    SLICE_TYPE = auto()
    GENERIC_TYPE = auto()

    # Control flow
    IF_ELSE = auto()
    FOR_LOOP = auto()
    FOR_RANGE = auto()
    SWITCH_STATEMENT = auto()
    TYPE_SWITCH = auto()
    SELECT_STATEMENT = auto()
    LABELED_STATEMENT = auto()
    GOTO = auto()
    FALLTHROUGH = auto()
    BREAK_CONTINUE = auto()
    RETURN = auto()

    # Concurrency
    DEFER = auto()
    GO_STATEMENT = auto()
    SEND_STATEMENT = auto()
    RECEIVE_STATEMENT = auto()
